"""Sequential import/prepare/remesh state machine, advanced by the UI timer."""

import os

import bpy
from bpy.app.handlers import persistent

from ..core.remesh_defaults import apply_quad_remesher_defaults_once, get_remesh_preset_counts
from ..core.remesh_job import RemeshJob, remesh_backend
from .apply_weld import apply_weld_to_objects
from .rename_objects import get_next_object_index, rename_and_move_objects


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
        self.owned_objects = set()
        self.owned_collections = set()
        self.owned_meshes = set()
        self.groups = []
        self.original_selection = list(context.selected_objects)
        self.original_active = context.view_layer.objects.active
        self.rename_index = get_next_object_index()
        settings = self.settings
        prefix = "file_import" if file_selection else "batch"
        self.rename = getattr(settings, prefix + "_auto_rename_objects")
        self.weld = getattr(settings, prefix + "_apply_weld")
        self.auto_remesh = getattr(settings, prefix + "_auto_remesh")
        self.separate = getattr(settings, prefix + "_separate_collections")
        self.quad_count = dict(get_remesh_preset_counts(context))[
            getattr(settings, prefix + "_remesh_preset")
        ]
        self.backend = remesh_backend(context) if self.auto_remesh else None
        self.weld_distance = settings.weld_distance
        self.arrange = settings.batch_auto_arrange_objects
        self.arrange_options = (settings.batch_arrange_spacing,
                                settings.batch_arrange_mode, settings.batch_arrange_rows)
        self.finished = False
        self.timer = None

    def begin(self):
        settings = self.settings
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
        settings.batch_current_file = ""
        settings.batch_last_error = ""
        settings.batch_stage = "QUEUED"

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
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

    def step(self, context):
        settings = self.settings
        if settings.batch_cancel_requested:
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
                settings.batch_stage = "PAUSED"
                return
            self.file_objects = []
            self.meshes = []
            self.mesh_index = 0
            self.collection = None
            settings.batch_current_file = os.path.basename(self.files[self.index])
            settings.batch_current_progress = 0
            self.stage = "IMPORT"
            settings.batch_stage = self.stage
            return  # Give the panel a frame to display the next file.
        try:
            self.advance(context)
        except Exception as error:
            if self.job:
                self.job.abort()
                self.job = None
                if self.mesh_index < len(self.meshes):
                    self.meshes[self.mesh_index].hide_set(False)
            settings.batch_last_error = f"{settings.batch_current_file}: {error}"
            self.report({"WARNING"}, settings.batch_last_error)
            settings.batch_failed_count += 1
            self.complete_file(success=False)
        self.update_progress()

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
            if self.weld:
                count = apply_weld_to_objects(context, self.meshes, self.weld_distance, self.report)
                if count != len(self.meshes):
                    raise RuntimeError("Weld failed for one or more meshes")
            self.stage = "REMESH" if self.auto_remesh else "COMPLETE"
        elif self.stage == "REMESH":
            source = self.meshes[self.mesh_index]
            self.select_source(context, source)
            apply_quad_remesher_defaults_once(self.scene)
            self.scene.qremesher.target_count = self.quad_count
            self.job = RemeshJob(self.backend, self.report)
            self.job.start(context)
            self.stage = "WAIT_REMESH"
        elif self.stage == "WAIT_REMESH":
            done, progress = self.job.poll()
            self.update_progress(progress)
            if not done:
                return
            source = self.meshes[self.mesh_index]
            self.select_source(context, source)
            before = set(self.owned_objects)
            self.tracked(lambda: self.job.finish(context))
            outputs = list(self.owned_objects - before)
            if not any(obj.type == "MESH" for obj in outputs):
                raise RuntimeError("Quad Remesher did not create a mesh")
            self.file_objects.extend(outputs)
            if self.collection:
                move_to_collection(outputs, self.collection)
            self.job = None
            self.mesh_index += 1
            self.stage = "REMESH" if self.mesh_index < len(self.meshes) else "COMPLETE"
        elif self.stage == "COMPLETE":
            self.groups.append((self.meshes[0], list(self.file_objects)))
            if self.arrange:
                self.arrange_groups()
            self.complete_file(success=True)
        settings.batch_stage = self.stage

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
        if success:
            self.settings.batch_current_progress = 100
            self.settings.batch_imported_count += 1
            self.settings.batch_imported_object_count += len(self.meshes)
        self.index += 1
        self.stage = "NEXT"
        self.settings.batch_stage = "NEXT"

    def update_progress(self, remesh_progress=None):
        fraction = 0.0
        if self.stage not in {"NEXT", "IMPORT"}:
            fraction = {"RENAME": 0.1, "WELD": 0.2, "REMESH": 0.3,
                        "WAIT_REMESH": 0.3, "COMPLETE": 0.99}[self.stage]
        if self.stage in {"REMESH", "WAIT_REMESH"} and self.meshes:
            fraction = 0.3 + 0.69 * (self.mesh_index + (remesh_progress or 0)) / len(self.meshes)
        if self.stage != "NEXT":
            self.settings.batch_current_progress = max(
                self.settings.batch_current_progress, 100 * fraction,
            )
            fraction = self.settings.batch_current_progress / 100
        value = 100 * (self.index + fraction) / len(self.files)
        self.settings.batch_import_progress = max(self.settings.batch_import_progress, value)
        self.settings.batch_remaining_count = len(self.files) - self.index

    def finish(self, context, status, rollback=False):
        if self.finished:
            return
        if self.job:
            self.job.abort()
            self.job = None
        if rollback:
            for obj in self.owned_objects & set(bpy.data.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            for mesh in self.owned_meshes & set(bpy.data.meshes):
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            for collection in self.owned_collections & set(bpy.data.collections):
                if not collection.objects and not collection.children:
                    bpy.data.collections.remove(collection)
            self.settings.batch_imported_count = 0
            self.settings.batch_imported_object_count = 0
            self.settings.batch_import_progress = 0
            self.settings.batch_current_progress = 0
            self.settings.batch_remaining_count = len(self.files)
            for obj in self.original_selection:
                if obj in set(bpy.data.objects):
                    obj.select_set(True)
            if self.original_active in set(bpy.data.objects):
                self.view_layer.objects.active = self.original_active
        self.settings.batch_is_running = False
        self.settings.batch_is_paused = False
        self.settings.batch_stage = status
        self.finished = True
        redraw(context)


class OBJECT_OT_polygroups_import_control(bpy.types.Operator):
    bl_idname = "object.polygroups_import_control"
    bl_label = "Import Queue Control"
    bl_description = "Pause/stop after the current file; cancel removes this run's imported objects"
    action: bpy.props.EnumProperty(items=(
        ("PAUSE", "Pause / Resume", "Pause after the current file or resume the queue"),
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
        elif self.action == "STOP":
            settings.batch_stop_requested = True
        else:
            settings.batch_cancel_requested = True
        redraw(context)
        return {"FINISHED"}
