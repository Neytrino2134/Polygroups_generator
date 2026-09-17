"""Sequential import/prepare/remesh state machine, advanced by the UI timer."""

import os
import re
import traceback
import time

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


ACTIVE_QUEUE = None


def redo_source(collection):
    """Return the original highpoly in a numbered Generated collection."""
    match = re.fullmatch(r"Generated\.(\d+)", collection.name) if collection else None
    if match is None:
        return None
    name = f"Highpoly_Generated.{match.group(1)}"
    return next((obj for obj in collection.objects if obj.type == "MESH" and obj.name == name), None)


def active_highpoly_collection(context):
    """Resolve only the selected active Highpoly_Generated.N mesh."""
    source = context.active_object
    if (source is None or source.type != "MESH" or not source.select_get()
            or re.fullmatch(r"Highpoly_Generated\.(\d+)", source.name) is None):
        return None
    return next((collection for collection in source.users_collection
                 if redo_source(collection) == source), None)


def redo_collections(view_layer):
    from .generated_visibility import generated_paths
    return [path[-1].collection for path in generated_paths(view_layer)
            if redo_source(path[-1].collection) is not None]


def selected_redo_collection(context):
    collections = redo_collections(context.view_layer)
    if not collections:
        return None
    name = context.scene.polygroups_model_preparation_settings.batch_redo_collection_name
    selected = next((collection for collection in collections if collection.name == name), None)
    if selected is not None:
        return selected
    active = context.active_object
    return next((collection for collection in collections
                 if active is not None and collection in active.users_collection), collections[0])


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


def reset_batch_import_settings(settings):
    """Return persisted/stale queue UI state to a clean idle state."""
    settings.batch_is_running = False
    settings.batch_is_paused = False
    settings.batch_stop_requested = False
    settings.batch_cancel_requested = False
    settings.batch_stage = ""
    settings.batch_last_error = ""
    settings.batch_total_count = 0
    settings.batch_imported_count = 0
    settings.batch_imported_object_count = 0
    settings.batch_failed_count = 0
    settings.batch_remaining_count = 0
    settings.batch_import_progress = 0.0
    settings.batch_current_progress = 0.0
    settings.batch_remesh_progress = 0.0
    settings.batch_baking_progress = 0.0
    settings.batch_current_file = ""
    settings.batch_elapsed_seconds = 0.0
    settings.batch_current_seconds = 0.0
    settings.batch_average_seconds = 0.0
    settings.batch_eta_seconds = -1.0


def save_current_blend_file():
    """Save without opening a file browser; Batch Import must remain modal."""
    if not bpy.data.filepath:
        return {"CANCELLED"}
    return bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)


def generated_collection_output_path(blend_filepath, collection_name):
    """Return the sibling blend path used for a numbered Generated collection."""
    match = re.fullmatch(r"Generated\.(\d+)", collection_name or "")
    if match is None:
        raise ValueError("Separate saving requires a numbered Generated.N collection")
    source = os.path.abspath(blend_filepath) if blend_filepath else ""
    if not source:
        raise ValueError("Save the working blend file before using separate collection saving")
    stem, _extension = os.path.splitext(os.path.basename(source))
    return os.path.join(
        os.path.dirname(source),
        f"{stem}_Generated_{match.group(1)}.blend",
    )


def generated_collection_files(blend_filepath):
    """Return numbered separate Generated files belonging to the working blend."""
    source = os.path.abspath(blend_filepath) if blend_filepath else ""
    if not source:
        raise ValueError("Save the working blend file before restoring separate collections")
    directory = os.path.dirname(source)
    stem, _extension = os.path.splitext(os.path.basename(source))
    pattern = re.compile(rf"^{re.escape(stem)}_Generated_(\d+)\.blend$", re.IGNORECASE)
    files = []
    for entry in os.scandir(directory):
        if not entry.is_file():
            continue
        match = pattern.fullmatch(entry.name)
        if match is not None:
            digits = match.group(1)
            files.append((int(digits), digits, entry.path))
    return sorted(files, key=lambda item: item[0])


def restore_retopo_collection(filepath, collection_name, scene):
    """Append only Retopo_* objects from one separately saved Generated.N."""
    with bpy.data.libraries.load(filepath, link=False) as (source, target):
        if collection_name not in source.collections:
            return 0
        target.collections = [collection_name]
    imported_collection = target.collections[0] if target.collections else None
    if imported_collection is None:
        return 0

    destination = bpy.data.collections.get(collection_name)
    if destination is imported_collection:
        destination = None
    if destination is None:
        destination = bpy.data.collections.new(collection_name)
        scene.collection.children.link(destination)

    # Re-running restore should reproduce the file, not create .001 duplicates.
    for obj in list(destination.objects):
        if obj.name.startswith("Retopo_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    imported_collections = []
    pending = [imported_collection]
    while pending:
        collection = pending.pop()
        if collection in imported_collections:
            continue
        imported_collections.append(collection)
        pending.extend(collection.children)
    imported_objects = set(imported_collection.all_objects)
    restored = []
    for obj in imported_objects:
        if obj.name.startswith("Retopo_"):
            destination.objects.link(obj)
            restored.append(obj)

    # Discard the appended HighPoly and temporary collection hierarchy. Retopo
    # objects survive because they are now linked directly to the destination.
    for obj in imported_objects:
        if obj not in restored:
            bpy.data.objects.remove(obj, do_unlink=True)
    for collection in reversed(imported_collections):
        if collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection, do_unlink=True)
    return len(restored)


def write_collection_blend(filepath, collection):
    """Save a directly openable copy while keeping the working file active."""
    if collection.name not in bpy.data.collections:
        raise RuntimeError("The Generated.N collection no longer exists")
    # Do not use bpy.data.libraries.write with a temporary Scene here. Blender
    # 5.2 can crash in BKE_view_layer_copy_data when that partial write runs
    # from the modal Batch Import operator after baking. Save As Copy follows
    # Blender's regular full-file writer and does not change bpy.data.filepath.
    # Remove other generated datablocks, not merely their view-layer visibility.
    # Keep empty placeholders in the working file for Restore Separate Retopo.
    placeholders = []
    for other in list(bpy.data.collections):
        if other in set(bpy.data.collections) and other != collection and re.fullmatch(r"Generated(?:\.\d+)?", other.name):
            placeholders.append(other.name)
            for obj in list(other.all_objects):
                if obj not in set(collection.all_objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
            pending = [other]
            hierarchy = []
            while pending:
                child = pending.pop()
                if child not in hierarchy and child != collection:
                    hierarchy.append(child)
                    pending.extend(child.children)
            for child in reversed(hierarchy):
                if child.name in bpy.data.collections:
                    bpy.data.collections.remove(child, do_unlink=True)
    try:
        result = bpy.ops.wm.save_as_mainfile(
            filepath=filepath, copy=True, relative_remap=True, check_existing=False,
        )
        if "FINISHED" not in result:
            raise RuntimeError("Blender did not finish saving the Generated.N copy")
    finally:
        for name in placeholders:
            placeholder = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(placeholder)


def move_to_collection(objects, collection):
    for obj in objects:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        for previous in list(obj.users_collection):
            if previous != collection:
                previous.objects.unlink(obj)


class ImportQueue:
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
                                settings.batch_arrange_mode, settings.batch_arrange_rows)
        self.auto_save = bool(self.batch_stages and settings.batch_auto_save)
        self.auto_save_interval = max(1, settings.batch_auto_save_interval)
        self.successful_imports_since_save = 0
        self.auto_save_unsaved_warned = False
        self.save_generated_separately = bool(
            self.batch_stages
            and self.separate
            and settings.batch_save_generated_separately
        )
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
        self.disable_completed_collection = self.batch_stages and self.separate
        if self.redo_mode:
            self.disable_completed_collection = False
        self.auto_smart_uv_project = bool(
            getattr(settings, prefix + "_auto_smart_uv_project")
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
        self.quad_count = dict(get_remesh_preset_counts(context))[
            getattr(settings, prefix + "_remesh_preset")
        ]
        self.weld_distance = settings.weld_distance
        self.arrange = settings.batch_auto_arrange_objects
        if self.redo_mode:
            self.arrange = False
        self.arrange_options = (
            settings.batch_arrange_spacing,
            settings.batch_arrange_mode,
            settings.batch_arrange_rows,
        )
        self.auto_save = bool(self.batch_stages and settings.batch_auto_save)
        self.auto_save_interval = max(1, settings.batch_auto_save_interval)
        self.save_generated_separately = bool(
            self.batch_stages
            and self.separate
            and settings.batch_save_generated_separately
        )

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

    def prepare_redo(self, context):
        collection = self.redo_collection
        source = redo_source(collection)
        if source is None or collection.name not in bpy.data.collections:
            raise RuntimeError("The selected Generated collection has no matching highpoly")
        if not ensure_collection_visible_in_view_layer(context, collection):
            raise RuntimeError("The selected Generated collection is not in this View Layer")
        self.collection = collection
        self.meshes = [source]
        self.file_record["input_tris"] = self.count_tris(self.meshes)
        self.file_objects = [source]
        self.pass_sources = [source]
        self.configure_passes(context)
        if not any(method for _number, method, _count, _unwrap, _unwrap_method in self.passes):
            raise RuntimeError("Enable at least one Remesh pass before rebuilding this collection")
        self.redo_source_visibility = (source, source.hide_viewport, source.hide_get(), source.hide_render)
        self.select_source(context, source)
        if self.cursor is None:
            self.cursor = RemeshCursor(context, label="Redo")
        old_results = [obj for obj in list(collection.objects) if obj.name.startswith("Retopo_")]
        if old_results:
            backup = bpy.data.collections.new(f"__PolygroupsRedoBackup_{collection.name}")
            self.redo_backup_collection = backup
            for index, obj in enumerate(old_results):
                links = list(obj.users_collection)
                self.redo_backup.append((obj, obj.name, links))
                for previous in links:
                    previous.objects.unlink(obj)
                backup.objects.link(obj)
                obj.name = f"__PolygroupsRedoBackup_{collection.name}_{index:03d}"

    def discard_redo_backup(self):
        materials = set()
        images = set()
        for obj, _name, _links in self.redo_backup:
            if obj.name in bpy.data.objects:
                mesh = obj.data if obj.type == "MESH" else None
                if mesh is not None:
                    materials.update(material for material in mesh.materials if material is not None)
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh is not None and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        for material in materials:
            if material.node_tree is not None:
                images.update(node.image for node in material.node_tree.nodes
                              if node.type == "TEX_IMAGE" and node.image is not None)
            if material.users == 0:
                bpy.data.materials.remove(material)
        for image in images:
            if image.users == 0:
                bpy.data.images.remove(image)
        self.redo_backup.clear()
        if self.redo_backup_collection is not None:
            bpy.data.collections.remove(self.redo_backup_collection)
            self.redo_backup_collection = None
        if self.redo_source_visibility is not None and not self.settings.batch_autobake_enabled:
            source, hidden_viewport, hidden_local, hidden_render = self.redo_source_visibility
            if source.name in bpy.data.objects:
                source.hide_viewport = hidden_viewport
                source.hide_set(hidden_local)
                source.hide_render = hidden_render
        self.redo_source_visibility = None

    def restore_redo_backup(self):
        if not self.redo_mode:
            return
        for obj in self.owned_objects & set(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in self.owned_meshes & set(bpy.data.meshes):
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for material in (self.owned_gray_materials | self.owned_bake_materials) & set(bpy.data.materials):
            if material.users == 0:
                bpy.data.materials.remove(material)
        for image in self.owned_bake_images & set(bpy.data.images):
            if image.users == 0:
                bpy.data.images.remove(image)
        self.owned_objects.clear()
        self.owned_meshes.clear()
        self.owned_gray_materials.clear()
        self.owned_bake_materials.clear()
        self.owned_bake_images.clear()
        for obj, name, links in self.redo_backup:
            if obj.name not in bpy.data.objects:
                continue
            obj.name = name
            for collection in links:
                if collection.name in bpy.data.collections:
                    collection.objects.link(obj)
        self.redo_backup.clear()
        if self.redo_backup_collection is not None:
            bpy.data.collections.remove(self.redo_backup_collection)
            self.redo_backup_collection = None
        if self.redo_source_visibility is not None:
            source, hidden_viewport, hidden_local, hidden_render = self.redo_source_visibility
            if source.name in bpy.data.objects:
                source.hide_viewport = hidden_viewport
                source.hide_set(hidden_local)
                source.hide_render = hidden_render
            self.redo_source_visibility = None

    def configure_passes(self, context):
        settings = self.settings
        self.passes = []
        if not self.batch_stages:
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
                        getattr(settings, f"batch_stage_{number}_auto_unwrap_method"),
                    ))
        self.stage = (self.first_cleanup_stage()
                      if self.batch_stages and not settings.batch_stage_2_enabled
                      else "PASS_SETUP")

    def tracked(self, action):
        """Track only IDs created by our synchronous action, even if it fails."""
        before_objects = set(bpy.data.objects)
        before_collections = set(bpy.data.collections)
        before_meshes = set(bpy.data.meshes)
        before_materials = set(bpy.data.materials)
        before_images = set(bpy.data.images)
        try:
            return action()
        finally:
            self.owned_objects.update(set(bpy.data.objects) - before_objects)
            self.owned_collections.update(set(bpy.data.collections) - before_collections)
            self.owned_meshes.update(set(bpy.data.meshes) - before_meshes)
            self.owned_materials.update(set(bpy.data.materials) - before_materials)
            self.owned_images.update(set(bpy.data.images) - before_images)

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
            max_width_percent=(self.settings.batch_narrow_island_max_width_percent
                               if not second else getattr(narrow, prefix + "max_width_percent")),
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
        if getattr(settings, f"batch_stage_{self.pass_number}_autofix_fin_loose"):
            _remove_fin_faces_for_autofix(context, obj)
            _delete_loose_geometry_for_autofix(context, obj)
        if getattr(settings, f"batch_stage_{self.pass_number}_autofix_close_nonmanifold"):
            _fill_open_nonmanifold_boundaries(obj)
        if getattr(settings, f"batch_stage_{self.pass_number}_autofix_triangulate_ngons"):
            _triangulate_ngons_for_autofix(obj)

    def first_cleanup_stage(self):
        if not self.batch_stages:
            return "PASS_SETUP"
        if self.settings.batch_narrow_island_enabled:
            return "NARROW_SPLIT"
        if self.settings.batch_small_islands_enabled:
            return "SMALL_ISLANDS"
        return "PASS_SETUP"

    def second_cleanup_stage(self):
        if not self.batch_stages:
            return "PASS_SETUP"
        if self.settings.batch_second_narrow_island_enabled:
            return "SECOND_NARROW_SPLIT"
        if self.settings.batch_second_small_islands_enabled:
            return "SECOND_SMALL_ISLANDS"
        return "PASS_SETUP"

    def pre_unwrap_stage(self, loose_cleanup_done=False):
        if self.batch_stages and self.pass_number in (3, 4):
            self.mesh_index = 0
            if (not loose_cleanup_done and getattr(
                    self.settings, f"batch_stage_{self.pass_number}_remove_small_loose_parts")):
                return "REMOVE_SMALL_LOOSE_PARTS"
            if getattr(self.settings, f"batch_stage_{self.pass_number}_autofix_enabled"):
                return "AUTOFIX_SECOND"
            return "UNWRAP_PASS"
        if (
            self.remove_small_loose_parts
            and self.pass_number == (2 if self.batch_stages else 1)
        ):
            self.mesh_index = 0
            return "REMOVE_SMALL_LOOSE_PARTS"
        if (
            self.batch_stages
            and self.pass_number == 2
            and self.settings.batch_first_uv_repair_enabled
        ):
            self.mesh_index = 0
            return "FIRST_UV_REPAIR"
        return "UNWRAP_PASS"

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
            self.complete_file(success=False)
            if self.save_generated_separately and not self.redo_mode:
                self.clear_failed_file()
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

    def finalization_stage(self):
        self.mesh_index = 0
        if self.batch_stages and self.settings.batch_smart_decimate_enabled:
            self.pass_number = 11
            return "SMART_DECIMATE"
        if self.batch_stages and self.settings.batch_smart_lods_enabled:
            self.pass_number = 12
            return "SMART_LODS"
        return "COMPLETE"

    def finalize_mesh(self, context, obj):
        settings = self.settings
        self.select_source(context, obj)
        if self.stage == "SMART_DECIMATE":
            from .smart_decimate import SEAMS_DECIMATE_MODIFIER_NAME, SMART_DECIMATE_MODIFIER_NAME
            result = self.tracked(lambda: bpy.ops.object.polygroups_smart_decimate(
                triangle_limit=settings.batch_smart_decimate_triangle_limit,
                duplicate_and_apply=False,
            ))
            if "FINISHED" not in result:
                raise RuntimeError(f"Smart Decimate failed for {obj.name}: check UV seam edges")
            for name in (SEAMS_DECIMATE_MODIFIER_NAME, SMART_DECIMATE_MODIFIER_NAME):
                if "FINISHED" not in self.tracked(lambda: bpy.ops.object.modifier_apply(modifier=name)):
                    raise RuntimeError(f"Applying {name} failed for {obj.name}")
            self.file_record.setdefault("finalization", []).append({
                "object": obj.name, "stage": 11,
                "triangle_limit": settings.batch_smart_decimate_triangle_limit,
                "output_tris": self.count_tris([obj]),
                "limit_reached": self.count_tris([obj]) <= settings.batch_smart_decimate_triangle_limit,
            })
        else:
            lod_settings = self.scene.polygroups_mesh_finalization_settings
            names = ["smart_lods_count", "smart_lods_final_decimate", "smart_lods_triangulate_all"]
            names.extend(f"smart_lods_target_{i}" for i in range(1, 6))
            previous = {name: getattr(lod_settings, name) for name in names + ["smart_lods_auto_arrange"]}
            before = set(bpy.data.objects)
            try:
                for name in names:
                    setattr(lod_settings, name, getattr(settings, "batch_" + name))
                lod_settings.smart_lods_auto_arrange = False
                result = self.tracked(lambda: bpy.ops.object.polygroups_generate_smart_lods())
                if "FINISHED" not in result:
                    raise RuntimeError(f"Smart LODs failed for {obj.name}")
            finally:
                for name, value in previous.items():
                    setattr(lod_settings, name, value)
            outputs = sorted(set(bpy.data.objects) - before, key=lambda item: item.name)
            self.file_objects.extend(outputs)
            if self.collection:
                move_to_collection(outputs, self.collection)
            self.result_meshes.extend(item for item in outputs if item.type == "MESH")
            self.file_record.setdefault("finalization", []).append({
                "object": obj.name, "stage": 12,
                "fallback": settings.batch_smart_lods_final_decimate,
                "triangulate": settings.batch_smart_lods_triangulate_all,
                "lods": [{"object": item.name, "output_tris": self.count_tris([item]),
                          "triangle_limit": getattr(settings, f"batch_smart_lods_target_{index}"),
                          "limit_reached": self.count_tris([item]) <= getattr(settings, f"batch_smart_lods_target_{index}")}
                         for index, item in enumerate((item for item in outputs if item.type == "MESH"), 1)],
            })

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

    @staticmethod
    def count_tris(objects):
        return sum(max(0, len(poly.vertices) - 2)
                   for obj in set(objects) if obj.type == "MESH" for poly in obj.data.polygons)

    def write_batch_report(self, event, data):
        if self.batch_report is not None:
            try:
                self.batch_report.event(event, data)
            except OSError as error:
                self.report({"WARNING"}, f"Cannot update batch reports: {error}")

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

    def save_and_clear_completed_collection(self):
        """Export the successful Generated.N collection, then commit an empty placeholder."""
        collection = self.collection
        if collection is None:
            raise RuntimeError("Separate saving could not find the completed Generated.N collection")
        output_path = generated_collection_output_path(bpy.data.filepath, collection.name)
        working_path = bpy.data.filepath
        write_collection_blend(output_path, collection)
        if getattr(self, "file_record", None) is not None:
            self.file_record["output_file"] = output_path
        if bpy.data.filepath != working_path:
            raise RuntimeError("Separate saving unexpectedly changed the working blend path")

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
    bl_description = "Restore Retopo objects from separate Generated.N blend files without HighPoly objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "polygroups_model_preparation_settings", None)
        return bool(bpy.data.filepath and settings and not settings.batch_is_running)

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
                count = restore_retopo_collection(filepath, collection_name, context.scene)
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
        message = f"Restored {restored_objects} Retopo object(s) from {restored_files} file(s)"
        if skipped:
            message += f"; skipped {len(skipped)} file(s)"
        self.report({"WARNING"} if skipped else {"INFO"}, message)
        return {"FINISHED"}
