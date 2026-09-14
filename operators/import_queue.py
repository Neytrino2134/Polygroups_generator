"""Sequential import/prepare/remesh state machine, advanced by the UI timer."""

import os

import bpy
import bmesh
from bpy.app.handlers import persistent

from ..core.remesh_defaults import apply_quad_remesher_defaults_once, get_remesh_preset_counts
from ..core.remesh_job import RemeshJob, VoxelRemeshJob, remesh_backend
from ..core.import_timing import ImportTiming
from .apply_weld import apply_weld_to_objects
from .small_islands import plan_merge
from .relax_seams import relax_seams
from .object_seam_cutter import (
    _delete_loose_geometry_for_autofix,
    _fill_open_nonmanifold_boundaries,
    _remove_fin_faces_for_autofix,
    _triangulate_ngons_for_autofix,
)
from .rename_objects import (
    get_next_object_index,
    layer_collection_paths,
    rename_and_move_objects,
)
from .unwrap_angle_based import smart_project_all, smart_uv_unwrap_all
from ..core.remesh_cursor import RemeshCursor
from ..localization import t


ACTIVE_QUEUE = None


@persistent
def stop_import_queue(*_args):
    global ACTIVE_QUEUE
    if ACTIVE_QUEUE is not None:
        ACTIVE_QUEUE.finish(bpy.context, "STOPPED")
        if ACTIVE_QUEUE.timer is not None:
            bpy.context.window_manager.event_timer_remove(ACTIVE_QUEUE.timer)
            ACTIVE_QUEUE.timer = None
        ACTIVE_QUEUE = None


def redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def save_current_blend_file():
    """Save without opening a file browser; Batch Import must remain modal."""
    if not bpy.data.filepath:
        return {"CANCELLED"}
    return bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)


def move_to_collection(objects, collection):
    for obj in objects:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        for previous in list(obj.users_collection):
            if previous != collection:
                previous.objects.unlink(obj)


class ImportQueue:
    def __init__(self, context, files, file_selection, report):
        self.scene = context.scene
        self.view_layer = context.view_layer
        self.settings = self.scene.polygroups_model_preparation_settings
        self.report = report
        self.files = list(files)
        self.index = 0
        self.stage = "NEXT"
        self.job = None
        self.meshes = []
        self.mesh_index = 0
        self.collection = None
        self.completed_collection = None
        self.owned_objects = set()
        self.owned_collections = set()
        self.owned_meshes = set()
        self.owned_gray_materials = set()
        self.owned_bake_materials = set()
        self.owned_bake_images = set()
        self.groups = []
        self.original_selection = list(context.selected_objects)
        self.original_active = context.view_layer.objects.active
        self.rename_index = get_next_object_index()
        settings = self.settings
        prefix = "file_import" if file_selection else "batch"
        self.file_selection = file_selection
        self.prefix = prefix
        self.rename = getattr(settings, prefix + "_auto_rename_objects")
        self.weld = getattr(settings, prefix + "_apply_weld")
        self.auto_remesh = getattr(settings, prefix + "_auto_remesh")
        self.remesh_method = getattr(settings, prefix + "_remesh_method")
        self.voxel_size = getattr(settings, prefix + "_voxel_size")
        self.clear_material = getattr(settings, prefix + "_clear_material")
        self.separate = getattr(settings, prefix + "_separate_collections")
        self.disable_completed_collection = not file_selection and self.separate
        self.disable_view_assist = getattr(settings, prefix + "_disable_view_assist")
        auto_smart_uv_property = prefix + "_auto_smart_uv_project"
        self.auto_smart_uv_project = bool(
            getattr(settings, auto_smart_uv_property)
            and (self.auto_remesh or not file_selection)
        )
        self.auto_unwrap_method = getattr(settings, prefix + "_auto_unwrap_method")
        if file_selection and not self.auto_remesh:
            setattr(settings, auto_smart_uv_property, False)
        self.quad_count = dict(get_remesh_preset_counts(context))[
            getattr(settings, prefix + "_remesh_preset")
        ]
        self.weld_distance = settings.weld_distance
        self.arrange = settings.batch_auto_arrange_objects
        self.arrange_options = (settings.batch_arrange_spacing,
                                settings.batch_arrange_mode, settings.batch_arrange_rows)
        self.auto_save = bool(not file_selection and settings.batch_auto_save)
        self.auto_save_interval = max(1, settings.batch_auto_save_interval)
        self.successful_imports_since_save = 0
        self.auto_save_unsaved_warned = False
        self.pause_after_each = bool(
            not file_selection and settings.batch_import_mode == "PAUSE_EACH"
        )
        self.pause_after_next_file = False
        self.finished = False
        self.timer = None
        self.cursor = None
        self.saved_remesh_settings = None
        self.saved_bake_settings = None
        self.bake_snapshot = None

    def restore_bake_settings(self):
        if self.saved_bake_settings is None:
            return
        use_auto, autogenerate_smart, use_smart, save_textures, selected_to_active = self.saved_bake_settings
        bake = self.scene.polygroups_baking_settings
        bake.autogenerate_smart_cage = False
        bake.use_auto_cage = False
        if autogenerate_smart:
            bake.autogenerate_smart_cage = True
        elif use_auto:
            bake.use_auto_cage = True
        else:
            bake.use_smart_cage = use_smart
        bake.auto_save_textures_after_bake = save_textures
        bake.use_selected_to_active = selected_to_active
        self.saved_bake_settings = None

    def collect_bake_created(self):
        if self.bake_snapshot is None:
            return
        target, objects, meshes, materials, images = self.bake_snapshot
        created_objects = {
            obj for obj in set(bpy.data.objects) - objects
            if obj.get("polygroups_smart_cage")
            and obj.get("smart_cage_target_object") == target
        }
        self.owned_objects.update(created_objects)
        self.file_objects.extend(obj for obj in created_objects if obj not in self.file_objects)
        self.owned_meshes.update(obj.data for obj in created_objects if obj.data not in meshes)
        target_materials = {material for material in target.data.materials if material is not None}
        self.owned_bake_materials.update(target_materials - materials)
        for material in target_materials:
            if material.node_tree is None:
                continue
            self.owned_bake_images.update(
                node.image for node in material.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image is not None and node.image not in images
            )
        self.bake_snapshot = None

    def start_auto_bake(self, context, target):
        self.select_source(context, target)
        if not bpy.data.filepath:
            raise RuntimeError("Save the blend file before Auto Bake so textures have an output folder")
        if target.data.uv_layers.active is None:
            raise RuntimeError(f"Auto Bake needs a UV map on {target.name}")
        bake = self.scene.polygroups_baking_settings
        if self.saved_bake_settings is None:
            self.saved_bake_settings = (
                bake.use_auto_cage, bake.autogenerate_smart_cage, bake.use_smart_cage,
                bake.auto_save_textures_after_bake, bake.use_selected_to_active,
            )
        bake.autogenerate_smart_cage = False
        bake.use_auto_cage = False
        if self.settings.batch_autobake_cage_mode == "SMART":
            bake.autogenerate_smart_cage = True
        else:
            bake.use_auto_cage = True
        bake.auto_save_textures_after_bake = True
        bake.use_selected_to_active = True
        self.bake_snapshot = (
            target, set(bpy.data.objects), set(bpy.data.meshes),
            set(bpy.data.materials), set(bpy.data.images),
        )
        result = bpy.ops.object.polygroups_checked_prepare_and_bake("EXEC_DEFAULT")
        if "CANCELLED" in result:
            raise RuntimeError(f"Auto Bake could not start for {target.name}")

    def restore_remesh_settings(self):
        if self.saved_remesh_settings is None:
            return
        use_materials, prepare, seams = self.saved_remesh_settings
        if hasattr(self.scene, "qremesher"):
            self.scene.qremesher.use_materials = use_materials
        self.settings.remesh_pregenerate_polygroups = prepare
        self.settings.remesh_auto_generate_seams = seams
        self.saved_remesh_settings = None

    def refresh_processing_settings(self, context):
        """Apply settings edited while paused to the next queued file."""
        settings = self.settings
        prefix = self.prefix
        self.rename = getattr(settings, prefix + "_auto_rename_objects")
        self.weld = getattr(settings, prefix + "_apply_weld")
        self.auto_remesh = getattr(settings, prefix + "_auto_remesh")
        self.remesh_method = getattr(settings, prefix + "_remesh_method")
        self.voxel_size = getattr(settings, prefix + "_voxel_size")
        self.clear_material = getattr(settings, prefix + "_clear_material")
        self.separate = getattr(settings, prefix + "_separate_collections")
        self.disable_completed_collection = not self.file_selection and self.separate
        self.auto_smart_uv_project = bool(
            getattr(settings, prefix + "_auto_smart_uv_project")
            and (self.auto_remesh or not self.file_selection)
        )
        self.auto_unwrap_method = getattr(settings, prefix + "_auto_unwrap_method")
        self.quad_count = dict(get_remesh_preset_counts(context))[
            getattr(settings, prefix + "_remesh_preset")
        ]
        self.weld_distance = settings.weld_distance
        self.arrange = settings.batch_auto_arrange_objects
        self.arrange_options = (
            settings.batch_arrange_spacing,
            settings.batch_arrange_mode,
            settings.batch_arrange_rows,
        )
        self.auto_save = bool(not self.file_selection and settings.batch_auto_save)
        self.auto_save_interval = max(1, settings.batch_auto_save_interval)

    def begin(self):
        self.timing = ImportTiming()
        settings = self.settings
        # Import owns its UV workflow. Disable the seam/remesh automatic unwrap
        # and Smart UV Unwrap packing switches on the first import run.
        seam_settings = self.scene.polygroups_seam_finalization_settings
        seam_settings.auto_unwrap_after_seam = False
        seam_settings.smart_uv_unwrap_auto_pack = False
        settings.remesh_auto_unwrap_checker = False
        if self.disable_view_assist:
            self.scene.polygroups_seam_preparation_settings.show_seams_object_mode = False
            self.scene.polygroups_seam_finalization_settings.show_checker_solid_mode = False
        settings.batch_is_running = True
        settings.batch_is_paused = False
        settings.batch_stop_requested = False
        settings.batch_cancel_requested = False
        settings.batch_total_count = len(self.files)
        settings.batch_imported_count = 0
        settings.batch_imported_object_count = 0
        settings.batch_failed_count = 0
        settings.batch_remaining_count = len(self.files)
        settings.batch_import_progress = 0
        settings.batch_current_progress = 0
        settings.batch_remesh_progress = 0
        settings.batch_current_file = ""
        settings.batch_last_error = ""
        settings.batch_stage = "QUEUED"
        if self.auto_save and not bpy.data.filepath:
            self.report(
                {"WARNING"},
                "Batch Auto Save is enabled, but the blend file has not been saved yet",
            )
            self.auto_save_unsaved_warned = True
        self.update_timing()

    def update_timing(self):
        self.settings.batch_elapsed_seconds = self.timing.elapsed()
        self.settings.batch_current_seconds = self.timing.current_elapsed()
        self.settings.batch_average_seconds = self.timing.average()
        self.settings.batch_eta_seconds = self.timing.remaining(len(self.files) - self.index)

    def tracked(self, action):
        """Track only IDs created by our synchronous action, even if it fails."""
        before_objects = set(bpy.data.objects)
        before_collections = set(bpy.data.collections)
        before_meshes = set(bpy.data.meshes)
        try:
            return action()
        finally:
            self.owned_objects.update(set(bpy.data.objects) - before_objects)
            self.owned_collections.update(set(bpy.data.collections) - before_collections)
            self.owned_meshes.update(set(bpy.data.meshes) - before_meshes)

    def select_source(self, context, obj):
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

    def split_narrow_island(self, context, obj, second=False):
        self.select_source(context, obj)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        narrow = (self.settings if second
                  else self.scene.polygroups_seam_finalization_settings)
        prefix = "batch_second_narrow_island_" if second else "narrow_island_"
        source = 'UV' if obj.data.uv_layers.active is not None else 'MESH'
        action = 'SPLIT' if source == 'UV' else 'SEAMS'
        result = bpy.ops.mesh.polygroups_split_narrow_islands(
            source=source, action=action,
            width=getattr(narrow, prefix + "width"),
            max_width_percent=getattr(narrow, prefix + "max_width_percent"),
            min_island_area_percent=getattr(narrow, prefix + "min_area_percent"),
            min_faces=getattr(narrow, prefix + "min_faces"),
            min_length=getattr(narrow, prefix + "min_length"),
            selected_only=False,
            create_edges=getattr(narrow, prefix + "create_edges"),
            smart_relax=getattr(narrow, prefix + "smart_relax"),
        )
        if 'FINISHED' not in result:
            raise RuntimeError(f'Narrow Island Splitter failed for {obj.name}')

    def merge_small_islands(self, context, obj, second=False):
        self.select_source(context, obj)
        settings = self.settings
        prefix = "batch_second_small_island_" if second else "batch_small_island_"
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            removed, _total, _small, _merged = plan_merge(
                bm,
                getattr(settings, prefix + "threshold"),
                protect_sharp=getattr(settings, prefix + "protect_sharp"),
                protect_materials=getattr(settings, prefix + "protect_materials"),
                protect_pinned=getattr(settings, prefix + "protect_pinned"),
            )
            if removed:
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                    self.owned_meshes.add(obj.data)
                bm.edges.ensure_lookup_table()
                for index in removed:
                    bm.edges[index].seam = False
                bm.to_mesh(obj.data)
                obj.data.update()
        finally:
            bm.free()

    def smart_relax_edges(self, context, obj):
        self.select_source(context, obj)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        seam_settings = self.scene.polygroups_seam_preparation_settings
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            relax_seams(
                context, "SMART",
                seam_settings.seam_relax_iterations,
                seam_settings.seam_relax_corner_angle,
                seam_settings.seam_relax_protection_radius,
                use_corner_angle=seam_settings.seam_relax_use_corner_angle,
                select_result=False,
                selected_area_only=False,
            )
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

    def autofix_second_pass(self, context, obj):
        self.select_source(context, obj)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        settings = self.settings
        if settings.batch_stage_3_autofix_fin_loose:
            _remove_fin_faces_for_autofix(context, obj)
            _delete_loose_geometry_for_autofix(context, obj)
        if settings.batch_stage_3_autofix_close_nonmanifold:
            _fill_open_nonmanifold_boundaries(obj)
        if settings.batch_stage_3_autofix_triangulate_ngons:
            _triangulate_ngons_for_autofix(obj)

    def first_cleanup_stage(self):
        if self.file_selection:
            return "PASS_SETUP"
        if self.settings.batch_narrow_island_enabled:
            return "NARROW_SPLIT"
        if self.settings.batch_small_islands_enabled:
            return "SMALL_ISLANDS"
        return "PASS_SETUP"

    def second_cleanup_stage(self):
        if self.file_selection:
            return "PASS_SETUP"
        if self.settings.batch_second_narrow_island_enabled:
            return "SECOND_NARROW_SPLIT"
        if self.settings.batch_second_small_islands_enabled:
            return "SECOND_SMALL_ISLANDS"
        return "PASS_SETUP"

    def step(self, context):
        settings = self.settings
        self.update_timing()
        if settings.batch_cancel_requested and not (
            self.stage == "BAKE_WAIT"
            and self.scene.polygroups_baking_settings.bake_task_is_running
        ):
            self.finish(context, "CANCELLED", rollback=True)
            return
        if self.stage == "NEXT":
            if settings.batch_stop_requested:
                self.finish(context, "STOPPED")
                return
            if self.index == len(self.files):
                self.finish(context, "DONE")
                return
            if settings.batch_is_paused:
                self.timing.pause()
                self.update_timing()
                settings.batch_stage = "PAUSED"
                self.update_cursor()
                return
            self.refresh_processing_settings(context)
            if self.disable_completed_collection and self.completed_collection is not None:
                for path in layer_collection_paths(
                    self.view_layer.layer_collection,
                    self.completed_collection,
                ):
                    path[-1].exclude = True
                self.view_layer.update()
                self.completed_collection = None
            self.file_objects = []
            self.meshes = []
            self.result_meshes = []
            self.pass_sources = []
            self.pass_outputs = []
            self.pass_index = 0
            self.mesh_index = 0
            self.second_cleanup_done = False
            self.bake_snapshot = None
            self.collection = None
            settings.batch_current_file = os.path.basename(self.files[self.index])
            settings.batch_current_progress = 0
            settings.batch_remesh_progress = 0
            self.timing.start_file()
            self.update_timing()
            self.stage = "IMPORT"
            settings.batch_stage = self.stage
            return  # Give the panel a frame to display the next file.
        try:
            self.advance(context)
        except Exception as error:
            if self.job:
                self.job.abort()
                self.job = None
                if self.mesh_index < len(self.pass_sources):
                    self.pass_sources[self.mesh_index].hide_viewport = False
                    self.pass_sources[self.mesh_index].hide_set(False)
            self.restore_remesh_settings()
            self.collect_bake_created()
            self.restore_bake_settings()
            settings.batch_last_error = f"{settings.batch_current_file}: {error}"
            self.report({"WARNING"}, settings.batch_last_error)
            settings.batch_failed_count += 1
            self.complete_file(success=False)
        self.update_progress()
        self.update_timing()

    def advance(self, context):
        from .batch_import import find_import_operator

        settings = self.settings
        if self.stage == "IMPORT":
            filepath = self.files[self.index]
            operator = find_import_operator(os.path.splitext(filepath)[1].lower())
            if operator is None:
                raise RuntimeError("No importer available for this file format")
            if context.object and context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            before = set(self.owned_objects)
            result = self.tracked(lambda: operator(filepath=filepath))
            self.file_objects = list(self.owned_objects - before)
            if "FINISHED" not in result:
                raise RuntimeError("Import did not finish")
            self.meshes = sorted((obj for obj in self.file_objects if obj.type == "MESH"),
                                 key=lambda obj: obj.name)
            if not self.meshes:
                raise RuntimeError("File contains no mesh objects")
            if self.separate:
                number = 1
                while bpy.data.collections.get(f"Generated.{number:03d}"):
                    number += 1
                self.collection = bpy.data.collections.new(f"Generated.{number:03d}")
                self.owned_collections.add(self.collection)
                self.scene.collection.children.link(self.collection)
                move_to_collection(self.file_objects, self.collection)
            self.stage = "RENAME"
        elif self.stage == "RENAME":
            if self.rename:
                self.tracked(lambda: rename_and_move_objects(
                    context, self.meshes,
                    collection_name=self.collection.name if self.collection else "Generated",
                    start_index=self.rename_index,
                ))
                self.rename_index += len(self.meshes)
            self.stage = "WELD"
        elif self.stage == "WELD":
            if self.cursor is None:
                self.cursor = RemeshCursor(context, label="Import")
            if self.weld:
                count = apply_weld_to_objects(context, self.meshes, self.weld_distance, self.report)
                if count != len(self.meshes):
                    raise RuntimeError("Weld failed for one or more meshes")
            self.pass_sources = list(self.meshes)
            self.passes = []
            if self.file_selection:
                if self.auto_remesh:
                    self.passes.append((1, self.remesh_method, self.quad_count,
                                        self.auto_smart_uv_project, self.auto_unwrap_method))
            else:
                if settings.batch_stage_2_enabled:
                    self.passes.append((2, self.remesh_method if self.auto_remesh else None,
                                        self.quad_count, self.auto_smart_uv_project,
                                        self.auto_unwrap_method))
                for number in (3, 4):
                    if getattr(settings, f"batch_stage_{number}_enabled"):
                        preset = getattr(settings, f"batch_stage_{number}_remesh_preset")
                        self.passes.append((
                            number,
                            "QUAD" if getattr(settings, f"batch_stage_{number}_auto_remesh") else None,
                            dict(get_remesh_preset_counts(context))[preset],
                            getattr(settings, f"batch_stage_{number}_auto_unwrap"),
                            "ANGLE",
                        ))
            self.stage = (self.first_cleanup_stage()
                          if not self.file_selection and not settings.batch_stage_2_enabled
                          else "PASS_SETUP")
        elif self.stage == "PASS_SETUP":
            if (not self.file_selection and not self.second_cleanup_done
                    and (self.pass_index >= len(self.passes)
                         or self.passes[self.pass_index][0] == 4)):
                self.second_cleanup_done = True
                self.mesh_index = 0
                self.stage = self.second_cleanup_stage()
            elif self.pass_index >= len(self.passes):
                if not self.file_selection and settings.batch_stage_5_enabled:
                    self.stage = "PACK"
                else:
                    self.mesh_index = 0
                    self.stage = ("BAKE_SETUP" if not self.file_selection and settings.batch_autobake_enabled
                                  else "COMPLETE")
            else:
                self.pass_number, self.pass_method, self.pass_quad_count, self.pass_unwrap, self.pass_unwrap_method = self.passes[self.pass_index]
                self.pass_outputs = []
                self.mesh_index = 0
                if self.pass_number >= 3 and self.pass_method == "QUAD":
                    remesh_backend(context)
                    self.saved_remesh_settings = (
                        self.scene.qremesher.use_materials,
                        settings.remesh_pregenerate_polygroups,
                        settings.remesh_auto_generate_seams,
                    )
                self.stage = ("REMESH" if self.pass_method else
                              "AUTOFIX_SECOND" if not self.file_selection and self.pass_number == 3
                              and settings.batch_stage_3_autofix_enabled else "UNWRAP_PASS")
        elif self.stage == "REMESH":
            settings.batch_remesh_progress = 0
            source = self.pass_sources[self.mesh_index]
            self.select_source(context, source)
            if self.pass_method == "QUAD":
                apply_quad_remesher_defaults_once(self.scene)
                self.scene.qremesher.target_count = self.pass_quad_count
                if self.pass_number >= 3:
                    self.scene.qremesher.use_materials = getattr(
                        settings, f"batch_stage_{self.pass_number}_use_materials"
                    )
                    settings.remesh_pregenerate_polygroups = getattr(
                        settings, f"batch_stage_{self.pass_number}_prepare_polygroups"
                    )
                    settings.remesh_auto_generate_seams = getattr(
                        settings, f"batch_stage_{self.pass_number}_material_seams"
                    )
                self.job = RemeshJob(remesh_backend(context), self.report)
            else:
                self.job = VoxelRemeshJob(self.voxel_size, self.report)
            self.job.start(context)
            if getattr(self.job, "cursor", None) is not None:
                self.job.cursor.close()
                self.job.cursor = None
            self.stage = "WAIT_REMESH"
        elif self.stage == "WAIT_REMESH":
            done, progress = self.job.poll()
            settings.batch_remesh_progress = max(
                settings.batch_remesh_progress,
                100.0 if done else 100.0 * max(0.0, min(1.0, progress or 0.0)),
            )
            self.update_progress(progress)
            if not done:
                return
            source = self.pass_sources[self.mesh_index]
            self.select_source(context, source)
            before = set(self.owned_objects)
            self.tracked(lambda: self.job.finish(context))
            outputs = list(self.owned_objects - before)
            output_meshes = [obj for obj in outputs if obj.type == "MESH"]
            if not output_meshes:
                raise RuntimeError(f"{self.pass_method.title()} Remesh did not create a mesh")
            if (not self.file_selection and self.pass_number in (3, 4)
                    and getattr(settings, f"batch_stage_{self.pass_number}_smart_relax_edges")
                    and self.pass_method == "QUAD"):
                for obj in output_meshes:
                    self.smart_relax_edges(context, obj)
            self.pass_outputs.extend(output_meshes)
            if self.pass_number in (1, 2) and self.clear_material:
                for obj in outputs:
                    if obj.type == "MESH":
                        self.replace_remesh_material(obj)
                        # Clear Material runs after the shared remesh post-process.
                        # Reapply Checker so both enabled options have visible results.
                        if getattr(self.job, "auto_unwrap_checker", False):
                            self.select_source(context, obj)
                            if "FINISHED" not in bpy.ops.object.polygroups_apply_checker_material():
                                raise RuntimeError(f"Applying checker material failed for {obj.name}")
            self.file_objects.extend(outputs)
            if self.collection:
                move_to_collection(outputs, self.collection)
            self.job = None
            self.mesh_index += 1
            if self.mesh_index < len(self.pass_sources):
                self.stage = "REMESH"
            else:
                self.mesh_index = 0
                self.stage = ("AUTOFIX_SECOND" if not self.file_selection and self.pass_number == 3
                              and settings.batch_stage_3_autofix_enabled else "UNWRAP_PASS")
        elif self.stage == "AUTOFIX_SECOND":
            targets = self.pass_outputs or self.pass_sources
            self.autofix_second_pass(context, targets[self.mesh_index])
            self.mesh_index += 1
            self.stage = "AUTOFIX_SECOND" if self.mesh_index < len(targets) else "UNWRAP_PASS"
        elif self.stage == "UNWRAP_PASS":
            self.restore_remesh_settings()
            targets = self.pass_outputs or self.pass_sources
            if self.pass_unwrap:
                for obj in targets:
                    self.select_source(context, obj)
                    if self.pass_unwrap_method == "SMART":
                        success, _packed = smart_uv_unwrap_all(context, obj)
                        if not success:
                            raise RuntimeError(f"Smart UV Unwrap failed for {obj.name}")
                    elif self.pass_unwrap_method == "CLASSIC":
                        if not smart_project_all(context, obj, mark_seams_from_islands=True):
                            raise RuntimeError(f"Smart UV Project failed for {obj.name}")
                    else:
                        if "FINISHED" not in bpy.ops.object.polygroups_unwrap_angle_based():
                            raise RuntimeError(f"Angle Based unwrap failed for {obj.name}")
                        if "FINISHED" not in bpy.ops.object.polygroups_apply_checker_material():
                            raise RuntimeError(f"Applying checker material failed for {obj.name}")
            self.pass_sources = targets
            self.result_meshes = targets
            self.pass_index += 1
            if not self.file_selection and self.pass_number == 2:
                self.mesh_index = 0
                self.stage = self.first_cleanup_stage()
            elif not self.file_selection and self.pass_number == 3:
                self.second_cleanup_done = True
                self.mesh_index = 0
                self.stage = self.second_cleanup_stage()
            else:
                self.stage = "PASS_SETUP"
        elif self.stage == "NARROW_SPLIT":
            obj = self.pass_sources[self.mesh_index]
            self.split_narrow_island(context, obj)
            self.mesh_index += 1
            self.stage = ("NARROW_SPLIT" if self.mesh_index < len(self.pass_sources)
                          else "SMALL_ISLANDS" if settings.batch_small_islands_enabled
                          else "PASS_SETUP")
            if self.stage == "SMALL_ISLANDS":
                self.mesh_index = 0
        elif self.stage == "SMALL_ISLANDS":
            obj = self.pass_sources[self.mesh_index]
            self.merge_small_islands(context, obj)
            self.mesh_index += 1
            self.stage = "SMALL_ISLANDS" if self.mesh_index < len(self.pass_sources) else "PASS_SETUP"
        elif self.stage == "SECOND_NARROW_SPLIT":
            obj = self.pass_sources[self.mesh_index]
            self.split_narrow_island(context, obj, second=True)
            self.mesh_index += 1
            self.stage = ("SECOND_NARROW_SPLIT" if self.mesh_index < len(self.pass_sources)
                          else "SECOND_SMALL_ISLANDS" if settings.batch_second_small_islands_enabled
                          else "PASS_SETUP")
            if self.stage == "SECOND_SMALL_ISLANDS":
                self.mesh_index = 0
        elif self.stage == "SECOND_SMALL_ISLANDS":
            obj = self.pass_sources[self.mesh_index]
            self.merge_small_islands(context, obj, second=True)
            self.mesh_index += 1
            self.stage = ("SECOND_SMALL_ISLANDS" if self.mesh_index < len(self.pass_sources)
                          else "PASS_SETUP")
        elif self.stage == "PACK":
            for obj in self.pass_sources:
                self.select_source(context, obj)
                if obj.data.uv_layers.active is None:
                    raise RuntimeError(f"No UV map to pack on {obj.name}")
                if "FINISHED" not in bpy.ops.object.polygroups_uvpackmaster_pack():
                    raise RuntimeError(f"UVPackmaster Pack failed for {obj.name}")
            self.mesh_index = 0
            self.stage = "BAKE_SETUP" if settings.batch_autobake_enabled else "COMPLETE"
        elif self.stage == "BAKE_SETUP":
            self.start_auto_bake(context, self.pass_sources[self.mesh_index])
            self.stage = "BAKE_WAIT"
        elif self.stage == "BAKE_WAIT":
            bake = self.scene.polygroups_baking_settings
            if bake.bake_task_is_running:
                return
            self.collect_bake_created()
            if bake.bake_task_stage != "DONE":
                raise RuntimeError(f"Auto Bake failed: {bake.bake_task_message}")
            self.mesh_index += 1
            if self.mesh_index < len(self.pass_sources):
                self.stage = "BAKE_SETUP"
            else:
                self.restore_bake_settings()
                self.stage = "COMPLETE"
        elif self.stage == "COMPLETE":
            self.groups.append((self.meshes[0], list(self.file_objects)))
            if self.arrange:
                self.arrange_groups()
            self.complete_file(success=True)
            self.auto_save_successful_meshes()
        settings.batch_stage = self.stage

    def replace_remesh_material(self, obj):
        # Only change the generated result, including when a backend shares data.
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        material = bpy.data.materials.new(name="Remesh Gray")
        self.owned_gray_materials.add(material)
        material.use_nodes = True
        gray = (0.5, 0.5, 0.5, 1.0)
        material.diffuse_color = gray
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = gray
        bsdf.inputs["Roughness"].default_value = 0.5
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj.material_slots[0].link = "DATA"
        obj.active_material_index = 0
        for polygon in obj.data.polygons:
            polygon.material_index = 0

    def arrange_groups(self):
        from .batch_import import arrange_objects_zx

        # Translate each file as a unit so highpoly/retopo pairs stay aligned.
        anchors = [anchor for anchor, objects in self.groups]
        old_positions = {obj: obj.matrix_world.translation.copy() for obj in anchors}
        arrange_objects_zx(anchors, *self.arrange_options)
        self.view_layer.update()
        deltas = {obj: obj.matrix_world.translation - old_positions[obj] for obj in anchors}
        for anchor in anchors:
            anchor.matrix_world.translation = old_positions[anchor]
        self.view_layer.update()
        for anchor, objects in self.groups:
            delta = deltas[anchor]
            matrices = {obj: obj.matrix_world.copy() for obj in objects}
            def parent_depth(obj):
                depth = 0
                while obj.parent:
                    depth += 1
                    obj = obj.parent
                return depth
            for obj in sorted(objects, key=parent_depth):
                matrix = matrices[obj]
                matrix.translation += delta
                obj.matrix_world = matrix
                self.view_layer.update()

    def complete_file(self, success):
        self.timing.complete_file(success)
        if success:
            self.completed_collection = self.collection
            self.settings.batch_current_progress = 100
            self.settings.batch_imported_count += 1
            self.settings.batch_imported_object_count += len(self.meshes)
        self.index += 1
        self.stage = "NEXT"
        self.settings.batch_stage = "NEXT"
        if self.index < len(self.files) and (
            self.pause_after_each or self.pause_after_next_file
        ):
            self.settings.batch_is_paused = True
        self.pause_after_next_file = False

    def auto_save_successful_meshes(self):
        if not self.auto_save:
            return
        self.successful_imports_since_save += 1
        if self.successful_imports_since_save < self.auto_save_interval:
            return
        if not bpy.data.filepath:
            if not self.auto_save_unsaved_warned:
                self.report(
                    {"WARNING"},
                    "Batch Auto Save skipped: save the blend file first",
                )
                self.auto_save_unsaved_warned = True
            return
        try:
            result = save_current_blend_file()
        except Exception as error:
            self.report({"WARNING"}, f"Batch Auto Save failed: {error}")
            return
        if "FINISHED" not in result:
            self.report({"WARNING"}, "Batch Auto Save did not finish")
            return
        self.successful_imports_since_save %= self.auto_save_interval
        self.auto_save_unsaved_warned = False
        self.report({"INFO"}, "Batch Import progress saved")

    def update_progress(self, remesh_progress=None):
        fraction = {"NEXT": 0.0, "IMPORT": 0.0, "RENAME": 0.05,
                    "WELD": 0.10, "PACK": 0.93, "BAKE_SETUP": 0.94,
                    "COMPLETE": 0.99}.get(self.stage, 0.15)
        if self.stage == "BAKE_WAIT":
            bake = self.scene.polygroups_baking_settings
            fraction = 0.94 + 0.045 * (
                self.mesh_index + bake.bake_task_progress / 100.0
            ) / max(1, len(self.pass_sources))
        if self.stage in {"PASS_SETUP", "REMESH", "WAIT_REMESH", "AUTOFIX_SECOND", "UNWRAP_PASS"}:
            count = max(1, len(getattr(self, "passes", ())))
            completed = min(self.pass_index, count)
            within = 0.0
            if self.stage in {"REMESH", "WAIT_REMESH"} and self.pass_sources:
                within = 0.85 * (self.mesh_index + (remesh_progress or 0)) / len(self.pass_sources)
            elif self.stage == "UNWRAP_PASS":
                within = 0.9
            elif self.stage == "AUTOFIX_SECOND":
                within = 0.85 + 0.05 * self.mesh_index / max(1, len(self.pass_outputs or self.pass_sources))
            fraction = 0.15 + 0.77 * (completed + within) / count
        if self.stage != "NEXT":
            self.settings.batch_current_progress = max(
                self.settings.batch_current_progress, 100 * fraction,
            )
            fraction = self.settings.batch_current_progress / 100
        value = 100 * (self.index + fraction) / len(self.files)
        self.settings.batch_import_progress = max(self.settings.batch_import_progress, value)
        self.settings.batch_remaining_count = len(self.files) - self.index
        self.update_cursor()

    def update_cursor(self):
        if self.cursor is not None:
            self.cursor.percent = self.settings.batch_import_progress
            self.cursor.label = f"Import {self.index + 1}/{len(self.files)}"
            self.cursor.secondary_percent = self.settings.batch_remesh_progress
            self.cursor.status_line = t(
                bpy.context,
                "import_cursor_paused" if self.settings.batch_stage == "PAUSED"
                else "import_cursor_processing",
            )

    def finish(self, context, status, rollback=False):
        if self.finished:
            return
        if self.job:
            self.job.abort()
            self.job = None
        self.restore_remesh_settings()
        self.collect_bake_created()
        self.restore_bake_settings()
        if self.cursor is not None:
            self.cursor.close()
            self.cursor = None
        if rollback:
            for obj in self.owned_objects & set(bpy.data.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            for mesh in self.owned_meshes & set(bpy.data.meshes):
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            for material in self.owned_gray_materials & set(bpy.data.materials):
                if material.users == 0:
                    bpy.data.materials.remove(material)
            for material in self.owned_bake_materials & set(bpy.data.materials):
                if material.users == 0:
                    bpy.data.materials.remove(material)
            for image in self.owned_bake_images & set(bpy.data.images):
                if image.users == 0:
                    bpy.data.images.remove(image)
            for collection in self.owned_collections & set(bpy.data.collections):
                if not collection.objects and not collection.children:
                    bpy.data.collections.remove(collection)
            self.settings.batch_imported_count = 0
            self.settings.batch_imported_object_count = 0
            self.settings.batch_import_progress = 0
            self.settings.batch_current_progress = 0
            self.settings.batch_remesh_progress = 0
            self.settings.batch_remaining_count = len(self.files)
            for obj in self.original_selection:
                if obj in set(bpy.data.objects):
                    obj.select_set(True)
            if self.original_active in set(bpy.data.objects):
                self.view_layer.objects.active = self.original_active
        self.settings.batch_is_running = False
        self.settings.batch_is_paused = False
        self.settings.batch_stage = status
        self.timing.stop()
        self.update_timing()
        if status != "DONE":
            self.settings.batch_eta_seconds = -1.0
        self.finished = True
        redraw(context)


class OBJECT_OT_polygroups_import_control(bpy.types.Operator):
    bl_idname = "object.polygroups_import_control"
    bl_label = "Import Queue Control"
    bl_description = "Pause/stop after the current file; cancel removes this run's imported objects"
    action: bpy.props.EnumProperty(items=(
        ("PAUSE", "Pause / Resume", "Pause after the current file or resume the queue"),
        ("NEXT_ONE", "Do Next", "Process one more file, then pause again"),
        ("NEXT_ALL", "Do Next All", "Resume and process every remaining file"),
        ("STOP", "Stop", "Finish the current file and keep imported results"),
        ("CANCEL", "Cancel", "Abort remeshing and remove all objects created by this import run"),
    ))

    @classmethod
    def poll(cls, context):
        return ACTIVE_QUEUE is not None and not ACTIVE_QUEUE.finished

    def execute(self, context):
        settings = ACTIVE_QUEUE.settings
        if self.action == "PAUSE":
            settings.batch_is_paused = not settings.batch_is_paused
        elif self.action == "NEXT_ONE":
            ACTIVE_QUEUE.pause_after_next_file = True
            settings.batch_is_paused = False
        elif self.action == "NEXT_ALL":
            ACTIVE_QUEUE.pause_after_each = False
            ACTIVE_QUEUE.pause_after_next_file = False
            settings.batch_is_paused = False
        elif self.action == "STOP":
            settings.batch_stop_requested = True
        else:
            settings.batch_cancel_requested = True
        redraw(context)
        return {"FINISHED"}
