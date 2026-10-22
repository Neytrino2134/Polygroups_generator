"""Sequential import/prepare/remesh state machine, advanced by the UI timer."""

import os
import re
import traceback
import time
from contextlib import contextmanager

from ..core.batch_report import BatchReport

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
    ensure_collection_visible_in_view_layer,
    get_next_object_index,
    layer_collection_paths,
    rename_and_move_objects,
)
from .small_loose_parts import remove_small_loose_parts
from .unwrap_angle_based import smart_project_all, smart_uv_unwrap_all
from ..core.remesh_cursor import RemeshCursor
from ..localization import t


from .queue_processing import QueueProcessingMixin
from .queue_redo import QueueRedoMixin
from .queue_storage import (
    _BATCH_IMPORT_IDLE_STATE,
    active_highpoly_collection,
    generated_collection_files,
    generated_collection_output_path,
    idle_import_state_for_copy,
    move_to_collection,
    redo_collections,
    redo_source,
    reset_batch_import_settings,
    restore_retopo_collection,
    selected_redo_collection,
    write_collection_blend,
)


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


class ImportQueue(QueueProcessingMixin, QueueRedoMixin):
    def __init__(self, context, files, file_selection, report, redo_collection=None,
                 automatic_processing=False):
        self.scene = context.scene
        self.view_layer = context.view_layer
        self.settings = self.scene.polygroups_model_preparation_settings
        self.batch_report = None
        self.file_record = None
        def audited_report(kind, message):
            report(kind, message)
            if self.batch_report is not None:
                try:
                    self.batch_report.event("message", {
                        "file": self.files[self.index] if self.index < len(self.files) else None,
                        "stage": self.stage, "level": sorted(kind), "message": str(message),
                    })
                except OSError:
                    pass
        self.report = audited_report
        self.files = list(files)
        self.redo_collection = redo_collection
        self.redo_mode = redo_collection is not None
        self.batch_stages = not file_selection or automatic_processing or self.redo_mode
        self.redo_backup = []
        self.redo_backup_collection = None
        self.redo_source_visibility = None
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
        self.owned_materials = set()
        self.owned_images = set()
        self.owned_gray_materials = set()
        self.owned_bake_materials = set()
        self.owned_bake_images = set()
        self.groups = []
        self.original_selection = list(context.selected_objects)
        self.original_active = context.view_layer.objects.active
        self.rename_index = get_next_object_index()
        settings = self.settings
        prefix = "batch" if self.batch_stages else "file_import"
        self.file_selection = file_selection
        self.prefix = prefix
        self.rename = getattr(settings, prefix + "_auto_rename_objects")
        self.weld = getattr(settings, prefix + "_apply_weld")
        self.auto_remesh = getattr(settings, prefix + "_auto_remesh")
        self.remesh_method = getattr(settings, prefix + "_remesh_method")
        self.voxel_size = getattr(settings, prefix + "_voxel_size")
        self.clear_material = getattr(settings, prefix + "_clear_material")
        self.separate = getattr(settings, prefix + "_separate_collections")
        self.disable_completed_collection = self.batch_stages and self.separate
        if self.redo_mode:
            self.disable_completed_collection = False
        self.disable_view_assist = getattr(settings, prefix + "_disable_view_assist")
        auto_smart_uv_property = prefix + "_auto_smart_uv_project"
        self.auto_smart_uv_project = bool(
            getattr(settings, auto_smart_uv_property)
            and (self.auto_remesh or self.batch_stages)
        )
        self.auto_unwrap_method = getattr(settings, prefix + "_auto_unwrap_method")
        if self.batch_stages:
            self.remove_small_loose_parts = settings.batch_first_remove_small_loose_parts
            self.small_loose_part_metric = settings.batch_first_small_loose_part_metric
            self.small_loose_part_threshold = settings.batch_first_small_loose_part_threshold_percent
        else:
            self.remove_small_loose_parts = settings.file_import_remove_small_loose_parts
            self.small_loose_part_metric = settings.file_import_small_loose_part_metric
            self.small_loose_part_threshold = settings.file_import_small_loose_part_threshold_percent
        if not self.batch_stages and not self.auto_remesh:
            setattr(settings, auto_smart_uv_property, False)
        self.quad_count = dict(get_remesh_preset_counts(context))[
            getattr(settings, prefix + "_remesh_preset")
        ]
        self.weld_distance = settings.weld_distance
        self.arrange = settings.batch_auto_arrange_objects
        self.arrange_options = (settings.batch_arrange_spacing,
                                settings.batch_arrange_mode, settings.batch_arrange_rows,
                                settings.batch_arrange_plane,
                                settings.batch_arrange_alignment,
                                settings.batch_arrange_secondary_spacing)
        self.auto_save = bool(self.batch_stages and settings.batch_auto_save)
        self.auto_save_interval = max(1, settings.batch_auto_save_interval)
        self.successful_imports_since_save = 0
        self.auto_save_unsaved_warned = False
        self.save_generated_separately = bool(
            self.batch_stages
            and self.separate
            and settings.batch_save_generated_separately
        )
        self.separately_saved_files = []
        self.separately_saved_count = 0
        self.separately_saved_object_count = 0
        self.pause_after_each = bool(
            self.batch_stages and settings.batch_import_mode == "PAUSE_EACH"
        )
        self.pause_after_next_file = False
        self.finished = False
        self.timer = None
        self.cursor = None
        self.saved_remesh_settings = None
        self.saved_unwrap_checker = None
        self.saved_bake_settings = None
        self.bake_snapshot = None


    def begin(self):
        directory = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else (
            os.path.dirname(os.path.abspath(self.files[0])) if not self.redo_mode else bpy.app.tempdir
        )
        try:
            self.batch_report = BatchReport(directory, self.files)
            self.report({"INFO"}, f"Batch reports: {self.batch_report.directory}")
        except OSError as error:
            self.report({"WARNING"}, f"Cannot create batch reports: {error}")
        self.timing = ImportTiming()
        settings = self.settings
        # Import owns its UV workflow. Disable the seam/remesh automatic unwrap
        # and Smart UV Unwrap packing switches on the first import run.
        seam_settings = self.scene.polygroups_seam_finalization_settings
        seam_settings.auto_unwrap_after_seam = False
        seam_settings.smart_uv_unwrap_auto_pack = False
        self.saved_unwrap_checker = settings.remesh_auto_unwrap_checker
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
        settings.batch_baking_progress = 0
        settings.batch_current_file = ""
        settings.batch_last_error = ""
        settings.batch_stage = "QUEUED"
        if (self.auto_save or self.save_generated_separately) and not bpy.data.filepath:
            self.report(
                {"WARNING"},
                "Batch saving is enabled, but the blend file has not been saved yet",
            )
            self.auto_save_unsaved_warned = True
        self.update_timing()

    def update_timing(self):
        self.settings.batch_elapsed_seconds = self.timing.elapsed()
        self.settings.batch_current_seconds = self.timing.current_elapsed()
        self.settings.batch_average_seconds = self.timing.average()
        self.settings.batch_eta_seconds = self.timing.remaining(len(self.files) - self.index)


    def step(self, context):
        settings = self.settings
        self.update_timing()
        if settings.batch_cancel_requested and not (
            self.stage == "BAKE_WAIT"
            and self.scene.polygroups_baking_settings.bake_task_is_running
        ):
            self.finish(context, "CANCELLED")
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
            self.file_owned_before = {
                kind: set(getattr(self, "owned_" + kind))
                for kind in ("objects", "collections", "meshes", "materials", "images")
            }
            self.file_record = {
                "file": self.files[self.index], "status": "processing",
                "input_tris": None, "output_tris": None, "stages": [],
                "started": time.time(),
            }
            self.last_logged_stage = None
            self.pass_number = None
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
            settings.batch_baking_progress = 0
            self.timing.start_file()
            self.update_timing()
            self.stage = "REDO_PREPARE" if self.redo_mode else "IMPORT"
            settings.batch_stage = self.stage
            return  # Give the panel a frame to display the next file.
        try:
            stage_key = (self.stage, getattr(self, "pass_number", None), self.mesh_index)
            if stage_key != self.last_logged_stage:
                self.last_logged_stage = stage_key
                event = {"stage": self.stage, "pass": stage_key[1],
                         "mesh_index": self.mesh_index, "time": time.time()}
                self.file_record["stages"].append(event)
                self.write_batch_report("stage", event)
            self.advance(context)
        except Exception as error:
            self.file_record.update(
                error=str(error), error_type=type(error).__name__,
                failed_stage=self.stage, failed_pass=getattr(self, "pass_number", None),
                mesh_index=self.mesh_index, traceback=traceback.format_exc(),
            )
            if self.job and hasattr(self.job, "diagnostics"):
                self.file_record["remesher"] = self.job.diagnostics()
            self.write_batch_report("error", self.file_record)
            if self.job:
                self.job.abort()
                self.job = None
                if self.mesh_index < len(self.pass_sources):
                    self.pass_sources[self.mesh_index].hide_viewport = False
                    self.pass_sources[self.mesh_index].hide_set(False)
            self.restore_remesh_settings()
            self.collect_bake_created()
            self.restore_bake_settings()
            self.restore_redo_backup()
            settings.batch_last_error = f"{settings.batch_current_file}: {error}"
            self.report({"WARNING"}, settings.batch_last_error)
            settings.batch_failed_count += 1
            self.preserve_partial_file()
            self.complete_file(success=False)
        self.update_progress()
        self.update_timing()

    def advance(self, context):
        from .batch_import import find_import_operator

        settings = self.settings
        if self.stage == "REDO_PREPARE":
            self.prepare_redo(context)
        elif self.stage == "IMPORT":
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
            self.file_record["input_tris"] = self.count_tris(self.meshes)
            if self.separate:
                number = 1
                while bpy.data.collections.get(f"Generated.{number:03d}"):
                    number += 1
                self.collection = bpy.data.collections.new(f"Generated.{number:03d}")
                self.collection.color_tag = "COLOR_05"
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
            self.configure_passes(context)
        elif self.stage == "PASS_SETUP":
            if (self.batch_stages and not self.second_cleanup_done
                    and (self.pass_index >= len(self.passes)
                         or self.passes[self.pass_index][0] == 4)):
                self.second_cleanup_done = True
                self.mesh_index = 0
                self.stage = self.second_cleanup_stage()
            elif self.pass_index >= len(self.passes):
                if self.batch_stages and settings.batch_stage_5_enabled:
                    self.stage = "PACK"
                else:
                    self.mesh_index = 0
                    self.stage = ("BAKE_SETUP" if self.batch_stages and settings.batch_autobake_enabled
                                  else self.finalization_stage())
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
                self.stage = "REMESH" if self.pass_method else self.pre_unwrap_stage()
        elif self.stage == "REMESH":
            settings.batch_remesh_progress = 0
            settings.batch_baking_progress = 0
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
            if (self.batch_stages and self.pass_number in (3, 4)
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
                self.stage = self.pre_unwrap_stage()
        elif self.stage == "AUTOFIX_SECOND":
            targets = self.pass_outputs or self.pass_sources
            self.autofix_second_pass(context, targets[self.mesh_index])
            self.mesh_index += 1
            self.stage = "AUTOFIX_SECOND" if self.mesh_index < len(targets) else "UNWRAP_PASS"
        elif self.stage == "REMOVE_SMALL_LOOSE_PARTS":
            targets = self.pass_outputs or self.pass_sources
            obj = targets[self.mesh_index]
            later_pass = self.batch_stages and self.pass_number in (3, 4)
            metric = (getattr(settings, f"batch_stage_{self.pass_number}_small_loose_part_metric")
                      if later_pass else self.small_loose_part_metric)
            threshold = (getattr(settings, f"batch_stage_{self.pass_number}_small_loose_part_threshold_percent")
                         if later_pass else self.small_loose_part_threshold)
            result = remove_small_loose_parts(
                obj,
                metric=metric,
                threshold_percent=threshold,
            )
            if result["part_count"]:
                self.report(
                    {"INFO"},
                    f"{obj.name}: removed {result['part_count']} small loose part(s) "
                    f"below {threshold:g}%",
                )
            self.mesh_index += 1
            if self.mesh_index < len(targets):
                self.stage = "REMOVE_SMALL_LOOSE_PARTS"
            else:
                self.mesh_index = 0
                self.stage = (
                    "FIRST_UV_REPAIR"
                    if self.batch_stages and self.pass_number == 2
                    and settings.batch_first_uv_repair_enabled
                    else self.pre_unwrap_stage(loose_cleanup_done=True) if later_pass
                    else "UNWRAP_PASS"
                )
        elif self.stage in {"FIRST_UV_REPAIR", "POST_UNWRAP_UV_REPAIR"}:
            repair_stage = self.stage
            repair_prefix = ("batch_first_uv_repair" if repair_stage == "FIRST_UV_REPAIR"
                             else f"batch_stage_{self.pass_number}_uv_repair")
            targets = self.pass_outputs or self.pass_sources
            obj = targets[self.mesh_index]
            self.select_source(context, obj)
            if obj.data.uv_layers.active is None:
                self.report({"INFO"}, f"{obj.name}: Smart UV Repair skipped; no UV map")
            else:
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                try:
                    result = bpy.ops.mesh.polygroups_repair_uv_stretch(
                        "EXEC_DEFAULT",
                        threshold=getattr(settings, repair_prefix + "_threshold"),
                        grow_threshold=1.8,
                        min_faces=getattr(settings, repair_prefix + "_min_faces"),
                        smooth_steps=2,
                        surface_angle=getattr(settings, repair_prefix + "_surface_angle"),
                        selected_only=False,
                        sharp_preference=3.0,
                        create_edges=True,
                        pin_generated=True,
                        merge_small_islands=True,
                        small_island_threshold=3.0,
                        smart_relax=True,
                        average_island_scale=True,
                        native_pack=True,
                        cleanup_artifacts=True,
                        artifact_method="MERGE_CENTER",
                        artifact_max_faces=7,
                        artifact_stretch=8.0,
                        artifact_compactness=10.0,
                    )
                finally:
                    if obj.mode == "EDIT":
                        bpy.ops.object.mode_set(mode="OBJECT")
                if "FINISHED" not in result:
                    raise RuntimeError(f"Smart UV Repair failed for {obj.name}")
            self.mesh_index += 1
            self.stage = (repair_stage if self.mesh_index < len(targets) else
                          "UNWRAP_PASS" if repair_stage == "FIRST_UV_REPAIR" else "COMPLETE_UNWRAP_PASS")
        elif self.stage == "UNWRAP_PASS":
            self.restore_remesh_settings()
            targets = self.pass_outputs or self.pass_sources
            if self.pass_unwrap:
                for obj in targets:
                    self.select_source(context, obj)
                    if self.pass_unwrap_method == "SMART":
                        seam_settings = self.scene.polygroups_seam_preparation_settings
                        previous_angle = seam_settings.smart_seam_angle_limit
                        if self.batch_stages and self.pass_number == 2:
                            seam_settings.smart_seam_angle_limit = settings.batch_first_surface_angle
                        try:
                            success, _packed = smart_uv_unwrap_all(context, obj)
                        finally:
                            seam_settings.smart_seam_angle_limit = previous_angle
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
            self.mesh_index = 0
            self.stage = (
                "POST_UNWRAP_UV_REPAIR"
                if self.batch_stages and self.pass_number in (3, 4) and self.pass_unwrap
                and getattr(settings, f"batch_stage_{self.pass_number}_uv_repair_enabled")
                else "COMPLETE_UNWRAP_PASS"
            )
        elif self.stage == "COMPLETE_UNWRAP_PASS":
            targets = self.pass_outputs or self.pass_sources
            self.repair_completed_pass_geometry(context, targets)
            self.pass_sources = targets
            self.result_meshes = list(targets)
            self.pass_index += 1
            if self.batch_stages and self.pass_number == 2:
                self.mesh_index = 0
                self.stage = self.first_cleanup_stage()
            elif self.batch_stages and self.pass_number == 3:
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
            self.stage = "BAKE_SETUP" if settings.batch_autobake_enabled else self.finalization_stage()
        elif self.stage == "BAKE_SETUP":
            settings.batch_baking_progress = 0
            self.start_auto_bake(context, self.pass_sources[self.mesh_index])
            self.stage = "BAKE_WAIT"
        elif self.stage == "BAKE_WAIT":
            bake = self.scene.polygroups_baking_settings
            settings.batch_baking_progress = bake.bake_task_progress
            if bake.bake_task_is_running:
                return
            self.collect_bake_created()
            if bake.bake_task_stage != "DONE":
                raise RuntimeError(f"Auto Bake failed: {bake.bake_task_message}")
            settings.batch_baking_progress = 100
            self.mesh_index += 1
            if self.mesh_index < len(self.pass_sources):
                self.stage = "BAKE_SETUP"
            else:
                self.restore_bake_settings()
                self.stage = self.finalization_stage()
        elif self.stage in ("SMART_DECIMATE", "SMART_LODS"):
            self.finalize_mesh(context, self.pass_sources[self.mesh_index])
            self.mesh_index += 1
            if self.mesh_index == len(self.pass_sources):
                self.stage = "COMPLETE"
        elif self.stage == "COMPLETE":
            self.file_record["output_tris"] = self.count_tris((self.pass_sources or self.meshes) + self.result_meshes)
            completed_object_count = len(self.meshes)
            if self.save_generated_separately:
                self.save_and_clear_completed_collection()
            else:
                self.groups.append((self.meshes[0], list(self.file_objects)))
                if self.arrange:
                    self.arrange_groups()
            self.complete_file(success=True, object_count=completed_object_count)
            self.auto_save_successful_meshes()
        settings.batch_stage = self.stage


    def write_batch_report(self, event, data):
        if self.batch_report is not None:
            try:
                self.batch_report.event(event, data)
            except OSError as error:
                self.report({"WARNING"}, f"Cannot update batch reports: {error}")

    def preserve_partial_file(self):
        """Preserve partial work in scene, or save and clear it in separate-file mode."""
        if self.redo_mode or self.file_record is None:
            return
        existing = set(bpy.data.objects)
        before = getattr(self, 'file_owned_before', {}).get('objects', set())
        objects = (self.owned_objects - before) & existing
        if not objects:
            return
        if self.separate and self.collection is None:
            number = 1
            while bpy.data.collections.get(f"Generated.{number:03d}"):
                number += 1
            self.collection = bpy.data.collections.new(f"Generated.{number:03d}")
            self.scene.collection.children.link(self.collection)
            self.owned_collections.add(self.collection)
        if self.collection is not None:
            self.collection.color_tag = "COLOR_05"
            move_to_collection(objects, self.collection)
        for obj in objects:
            obj.hide_viewport = False
            obj.hide_set(False)
        if self.save_generated_separately and self.collection is not None:
            try:
                self.save_and_clear_completed_collection(completed=False)
            except Exception as error:
                self.report({'WARNING'}, f'Partial batch results remain in scene; save failed: {error}')

    def clear_failed_file(self):
        collection_name = self.collection.name if self.collection else None
        for kind in ("objects", "collections", "meshes", "materials", "images"):
            owned = getattr(self, "owned_" + kind)
            ids = getattr(bpy.data, kind)
            for item in (owned - self.file_owned_before[kind]) & set(ids):
                if kind in ("objects", "collections") or item.users == 0:
                    owned.discard(item)
                    ids.remove(item, do_unlink=True)
        if collection_name:
            placeholder = bpy.data.collections.new(collection_name)
            self.scene.collection.children.link(placeholder)
        self.collection = None
        self.file_objects = []
        self.meshes = []
        self.pass_sources = []
        self.pass_outputs = []
        self.result_meshes = []

    def complete_file(self, success, object_count=None):
        if self.collection is not None:
            self.collection.color_tag = "COLOR_02" if success else "COLOR_05"
        if self.file_record is not None:
            self.file_record.update(status="success" if success else "failed", finished=time.time())
            self.write_batch_report("file_complete", self.file_record)
            self.file_record = None
        self.timing.complete_file(success)
        if success:
            self.completed_collection = self.collection
            self.settings.batch_current_progress = 100
            self.settings.batch_imported_count += 1
            self.settings.batch_imported_object_count += (
                len(self.meshes) if object_count is None else object_count
            )
        self.index += 1
        self.stage = "NEXT"
        self.settings.batch_stage = "NEXT"
        if self.index < len(self.files) and (
            self.pause_after_each or self.pause_after_next_file
        ):
            self.settings.batch_is_paused = True
        self.pause_after_next_file = False

    def auto_save_successful_meshes(self):
        if self.save_generated_separately:
            return
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

    def save_and_clear_completed_collection(self, completed=True):
        """Export the successful Generated.N collection, then commit an empty placeholder."""
        collection = self.collection
        if collection is None:
            raise RuntimeError("Separate saving could not find the completed Generated.N collection")
        collection.color_tag = "COLOR_02" if completed else "COLOR_05"
        output_path = generated_collection_output_path(bpy.data.filepath, collection.name)
        working_path = bpy.data.filepath
        write_collection_blend(output_path, collection)
        if getattr(self, "file_record", None) is not None:
            self.file_record["output_file"] = output_path
        if bpy.data.filepath != working_path:
            raise RuntimeError("Separate saving unexpectedly changed the working blend path")

        if hasattr(self, 'separately_saved_files'):
            self.separately_saved_files.append((output_path, collection.name))
        saved_object_count = len(self.meshes)
        removed_objects = list(collection.all_objects)
        for obj in removed_objects:
            self.owned_objects.discard(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        pending = list(collection.children)
        children = []
        while pending:
            child = pending.pop()
            if child not in children:
                children.append(child)
                pending.extend(child.children)
        for child in reversed(children):
            self.owned_collections.discard(child)
            bpy.data.collections.remove(child, do_unlink=True)

        for mesh in list(self.owned_meshes):
            if mesh.users == 0:
                self.owned_meshes.discard(mesh)
                bpy.data.meshes.remove(mesh)
        material_sets = (
            self.owned_materials,
            self.owned_gray_materials,
            self.owned_bake_materials,
        )
        for material in list(set().union(*material_sets)):
            if material.users == 0:
                for material_set in material_sets:
                    material_set.discard(material)
                bpy.data.materials.remove(material)
        image_sets = (self.owned_images, self.owned_bake_images)
        for image in list(set().union(*image_sets)):
            if image.users == 0:
                for image_set in image_sets:
                    image_set.discard(image)
                bpy.data.images.remove(image)

        # This empty collection is now committed state and must survive a later queue cancel.
        self.owned_collections.discard(collection)
        self.file_objects = []
        self.meshes = []
        self.pass_sources = []
        self.pass_outputs = []
        self.result_meshes = []
        if completed:
            self.separately_saved_count += 1
            self.separately_saved_object_count += saved_object_count
        try:
            result = save_current_blend_file()
        except Exception as error:
            self.report(
                {"WARNING"},
                f"Saved {os.path.basename(output_path)}, but could not save the working file: {error}",
            )
        else:
            if "FINISHED" not in result:
                self.report(
                    {"WARNING"},
                    f"Saved {os.path.basename(output_path)}, but the working file save did not finish",
                )
        self.report({"INFO"}, f"Saved {os.path.basename(output_path)}")

    def update_progress(self, remesh_progress=None):
        fraction = {"NEXT": 0.0, "IMPORT": 0.0, "RENAME": 0.05,
                    "WELD": 0.10, "PACK": 0.93, "BAKE_SETUP": 0.94,
                    "SMART_DECIMATE": 0.985, "SMART_LODS": 0.985,
                    "COMPLETE": 0.99}.get(self.stage, 0.15)
        if self.stage == "BAKE_WAIT":
            bake = self.scene.polygroups_baking_settings
            fraction = 0.94 + 0.045 * (
                self.mesh_index + bake.bake_task_progress / 100.0
            ) / max(1, len(self.pass_sources))
        if self.stage in {
            "PASS_SETUP", "REMESH", "WAIT_REMESH", "AUTOFIX_SECOND",
            "REMOVE_SMALL_LOOSE_PARTS", "UNWRAP_PASS",
        }:
            count = max(1, len(getattr(self, "passes", ())))
            completed = min(self.pass_index, count)
            within = 0.0
            if self.stage in {"REMESH", "WAIT_REMESH"} and self.pass_sources:
                within = 0.85 * (self.mesh_index + (remesh_progress or 0)) / len(self.pass_sources)
            elif self.stage == "UNWRAP_PASS":
                within = 0.9
            elif self.stage == "REMOVE_SMALL_LOOSE_PARTS":
                within = 0.88 + 0.02 * self.mesh_index / max(
                    1, len(self.pass_outputs or self.pass_sources),
                )
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
            self.cursor.label = f"{'Redo' if self.redo_mode else 'Import'} {self.index + 1}/{len(self.files)}"
            self.cursor.secondary_percent = self.settings.batch_remesh_progress
            self.cursor.primary_in_corner = True
            if self.stage in {"BAKE_SETUP", "BAKE_WAIT"}:
                self.cursor.secondary_label = t(bpy.context, "import_baking_progress")
                self.cursor.secondary_percent = self.settings.batch_baking_progress
            else:
                self.cursor.secondary_label = t(bpy.context, "import_remesh_progress")
            self.cursor.status_line = t(
                bpy.context,
                "import_cursor_paused" if self.settings.batch_stage == "PAUSED"
                else "import_cursor_processing",
            )

    def finish(self, context, status, rollback=False):
        if self.finished:
            return
        if self.file_record is not None and self.collection is not None and status != "DONE":
            self.collection.color_tag = "COLOR_05"
        if self.saved_unwrap_checker is not None:
            self.settings.remesh_auto_unwrap_checker = self.saved_unwrap_checker
            self.saved_unwrap_checker = None
        if self.job:
            self.job.abort()
            self.job = None
        self.restore_remesh_settings()
        self.collect_bake_created()
        self.restore_bake_settings()
        if self.redo_mode:
            if status == "DONE":
                self.discard_redo_backup()
            else:
                self.restore_redo_backup()
        if self.cursor is not None:
            self.cursor.close()
            self.cursor = None
        if not rollback and not self.redo_mode and status != 'DONE':
            self.preserve_partial_file()
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
            for material in self.owned_materials & set(bpy.data.materials):
                if material.users == 0:
                    bpy.data.materials.remove(material)
            for image in self.owned_bake_images & set(bpy.data.images):
                if image.users == 0:
                    bpy.data.images.remove(image)
            for image in self.owned_images & set(bpy.data.images):
                if image.users == 0:
                    bpy.data.images.remove(image)
            for collection in self.owned_collections & set(bpy.data.collections):
                if not collection.objects and not collection.children:
                    bpy.data.collections.remove(collection)
            self.settings.batch_imported_count = self.separately_saved_count
            self.settings.batch_imported_object_count = self.separately_saved_object_count
            self.settings.batch_import_progress = 0
            self.settings.batch_current_progress = 0
            self.settings.batch_remesh_progress = 0
            self.settings.batch_baking_progress = 0
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
        if self.file_record is not None:
            self.file_record.update(status="cancelled" if rollback else "interrupted",
                                    failed_stage=self.stage, finished=time.time())
            self.write_batch_report("file_complete", self.file_record)
            self.file_record = None
        self.write_batch_report("finish", {"status": status})
        self.finished = True
        if (
            status == "DONE"
            and self.save_generated_separately
            and self.settings.batch_auto_restore_separate_retopo
        ):
            try:
                with context.temp_override(scene=self.scene, view_layer=self.view_layer):
                    result = bpy.ops.object.polygroups_restore_separate_retopo()
                if result != {"FINISHED"}:
                    self.report({"WARNING"}, "Automatic Retopo restore did not complete")
            except Exception as error:
                self.report({"WARNING"}, f"Automatic Retopo restore failed: {error}")
        if not rollback and not self.redo_mode and status != 'DONE':
            if self.save_generated_separately and bpy.data.filepath:
                try:
                    save_current_blend_file()
                except Exception as error:
                    self.report({'WARNING'}, f'Could not save recovered batch: {error}')
        redraw(context)


class OBJECT_OT_polygroups_toggle_batch_stage(bpy.types.Operator):
    bl_idname = "object.polygroups_toggle_batch_stage"
    bl_label = "Expand or Collapse Processing Stage"
    bl_description = "Show or hide this stage's settings without changing whether it runs"
    bl_options = {"INTERNAL"}

    stage: bpy.props.IntProperty(min=1, max=12, options={"SKIP_SAVE"})

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        settings.batch_expanded_stages ^= 1 << (self.stage - 1)
        redraw(context)
        return {"FINISHED"}


class OBJECT_OT_polygroups_batch_redo_select(bpy.types.Operator):
    bl_idname = "object.polygroups_batch_redo_select"
    bl_label = "Select Collection for Redo"
    bl_description = "Switch between Generated.N collections with an original highpoly"
    bl_options = {"REGISTER", "UNDO"}

    direction: bpy.props.EnumProperty(items=(
        ("PREVIOUS", "Previous", "Select the previous Generated collection"),
        ("NEXT", "Next", "Select the next Generated collection"),
    ))

    @classmethod
    def poll(cls, context):
        return (context.mode == "OBJECT"
                and not context.scene.polygroups_model_preparation_settings.batch_is_running
                and bool(redo_collections(context.view_layer)))

    def execute(self, context):
        from .generated_visibility import generated_paths, reveal_active_collection_in_outliners

        collections = redo_collections(context.view_layer)
        current = selected_redo_collection(context)
        index = collections.index(current) + (1 if self.direction == "NEXT" else -1)
        if not 0 <= index < len(collections):
            self.report({"INFO"}, "No collection in that direction")
            return {"CANCELLED"}
        target = collections[index]
        paths = generated_paths(context.view_layer)
        target_path = next(path for path in paths if path[-1].collection == target)
        for path in paths:
            if path[-1] not in target_path:
                path[-1].exclude = True
        for layer in target_path[1:]:
            layer.exclude = False
            layer.hide_viewport = False
        target.hide_viewport = False
        context.view_layer.update()
        context.view_layer.active_layer_collection = target_path[-1]
        context.scene.polygroups_model_preparation_settings.batch_redo_collection_name = target.name
        for obj in context.selected_objects:
            obj.select_set(False)
        context.view_layer.objects.active = None
        candidates = sorted(
            (obj for obj in target.objects if obj.type == "MESH"
             and obj.name in context.view_layer.objects
             and obj.visible_get(view_layer=context.view_layer) and not obj.hide_select),
            key=lambda obj: (not obj.name.startswith("Retopo_"), obj.name),
        )
        if candidates:
            candidates[0].select_set(True)
            context.view_layer.objects.active = candidates[0]
        reveal_active_collection_in_outliners(context)
        self.report({"INFO"}, target.name)
        return {"FINISHED"}


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


class OBJECT_OT_polygroups_reset_import_state(bpy.types.Operator):
    bl_idname = "object.polygroups_reset_import_state"
    bl_label = "Reset Import State"
    bl_description = "Stop stale processing and unlock Batch Import controls"
    bl_options = {"REGISTER"}

    def execute(self, context):
        global ACTIVE_QUEUE

        from .phase2_processing import ACTIVE_PHASE2
        if ACTIVE_PHASE2 is not None:
            ACTIVE_PHASE2.stop_requested = True
            self.report({"INFO"}, "Phase 2 will stop after the current bake")
            return {"FINISHED"}

        if bpy.app.is_job_running("OBJECT_BAKE"):
            self.report({"WARNING"}, "Cannot reset while Blender is actively baking")
            return {"CANCELLED"}

        queue = ACTIVE_QUEUE
        reset_warning = ""
        if queue is not None:
            try:
                queue.finish(context, "STOPPED")
            except Exception as error:
                reset_warning = str(error)
                job = getattr(queue, "job", None)
                if job is not None:
                    try:
                        job.abort()
                    except Exception:
                        pass
                queue.finished = True
            timer = getattr(queue, "timer", None)
            if timer is not None:
                try:
                    context.window_manager.event_timer_remove(timer)
                except Exception:
                    pass
                queue.timer = None
            ACTIVE_QUEUE = None

        from . import remesh_progress
        if remesh_progress.ACTIVE_REMESH is not None:
            try:
                remesh_progress.stop_remesh()
            except Exception as error:
                reset_warning = reset_warning or str(error)
                remesh_progress.ACTIVE_REMESH = None

        reset_batch_import_settings(context.scene.polygroups_model_preparation_settings)
        bake_settings = context.scene.polygroups_baking_settings
        bake_settings.bake_task_is_running = False
        bake_settings.bake_task_stage = ""
        bake_settings.bake_task_progress = 0.0
        bake_settings.bake_task_message = ""
        remesh_status = context.scene.polygroups_remesh_status
        remesh_status.is_running = False
        remesh_status.cancel_requested = False
        remesh_status.stage = ""
        remesh_status.progress = 0.0
        remesh_status.message = ""
        redraw(context)
        if reset_warning:
            self.report({"WARNING"}, f"Import state reset after cleanup warning: {reset_warning}")
        else:
            self.report({"INFO"}, "Import processing state reset")
        return {"FINISHED"}


class OBJECT_OT_polygroups_restore_separate_retopo(bpy.types.Operator):
    bl_idname = "object.polygroups_restore_separate_retopo"
    bl_label = "Restore Retopo from Separate Files"
    bl_description = "Restore Retopo objects from separate Generated.N blend files using the Include Highpoly Generated setting"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "polygroups_model_preparation_settings", None)
        return bool(bpy.data.filepath and settings and not settings.batch_is_running
                    and not settings.phase2_is_running)

    def execute(self, context):
        try:
            files = generated_collection_files(bpy.data.filepath)
        except (OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if not files:
            self.report({"WARNING"}, "No separate Generated.N blend files were found")
            return {"CANCELLED"}

        restored_files = 0
        restored_objects = 0
        skipped = []
        for _number, digits, filepath in files:
            collection_name = f"Generated.{digits}"
            try:
                count = restore_retopo_collection(
                    filepath, collection_name, context.scene,
                    include_highpoly=context.scene.polygroups_model_preparation_settings.batch_restore_include_highpoly,
                )
            except Exception as error:
                skipped.append(f"{os.path.basename(filepath)}: {error}")
                continue
            if count:
                restored_files += 1
                restored_objects += count
            else:
                skipped.append(os.path.basename(filepath))

        redraw(context)
        if restored_objects == 0:
            message = "No Retopo objects were restored"
            if skipped:
                message += f" ({len(skipped)} file(s) skipped)"
            self.report({"WARNING"}, message)
            return {"CANCELLED"}
        message = f"Restored {restored_objects} object(s) from {restored_files} file(s)"
        if skipped:
            message += f"; skipped {len(skipped)} file(s)"
        self.report({"WARNING"} if skipped else {"INFO"}, message)
        return {"FINISHED"}
