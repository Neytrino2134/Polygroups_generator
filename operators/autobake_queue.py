"""Run AutoBake sequentially for explicit pairs or low-poly targets."""
from collections import Counter
from contextlib import ExitStack

import bpy

from ..core.generated_index import bake_output_name
from .baking import _redraw_bake_ui, _safe_path_name
from .phase2_zbrush_export import export_visibility, preserved_selection
from .rebake_queue import editable
from .safety_checks import find_matching_highpoly, selected_mesh_objects
from .sequential_jobs import SequentialJob


class OBJECT_OT_polygroups_autobake_queue_edit(bpy.types.Operator):
    bl_idname = "object.polygroups_autobake_queue_edit"
    bl_label = "Edit AutoBake Queue"
    bl_options = {"UNDO"}

    action: bpy.props.EnumProperty(items=(
        ("ADD", "Add to Queue", "Queue the active low-poly and an optional selected high-poly"),
        ("REMOVE", "Remove", "Remove this queue entry"),
        ("CLEAR", "Clear Queue", "Remove all entries from the queue"),
    ))
    index: bpy.props.IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return editable(context)

    def execute(self, context):
        settings = context.scene.polygroups_baking_settings
        queue = settings.autobake_queue
        if self.action == "CLEAR":
            queue.clear()
        elif self.action == "REMOVE":
            if not 0 <= self.index < len(queue):
                return {"CANCELLED"}
            queue.remove(self.index)
        else:
            meshes = selected_mesh_objects(context)
            target = context.active_object
            if len(meshes) not in {1, 2} or target not in meshes:
                self.report({"WARNING"}, "Select one low-poly, or select high-poly first and low-poly last")
                return {"CANCELLED"}
            source = next((obj for obj in meshes if obj != target), None)
            entry = next((item for item in queue if item.target == target), None)
            if entry is None:
                entry = queue.add()
                entry.target = target
            entry.source = source
            entry.manual_source = source is not None
            entry.state, entry.message = "PENDING", ""
        settings.autobake_queue_status = f"{len(queue)} queued"
        settings.autobake_queue_progress = 0
        return {"FINISHED"}


class OBJECT_OT_polygroups_autobake_queue_run(SequentialJob, bpy.types.Operator):
    bl_idname = "object.polygroups_autobake_queue_run"
    bl_label = "Run AutoBake Queue"
    bl_description = "Bake queued targets in order and save their textures next to the blend file"
    _is_autobake_queue = True
    _autobake_dispatching = False

    @classmethod
    def poll(cls, context):
        return editable(context) and bool(context.scene.polygroups_baking_settings.autobake_queue)

    def execute(self, context):
        settings = context.scene.polygroups_baking_settings
        if not bpy.data.filepath:
            self.report({"WARNING"}, "Save the blend file before running the AutoBake queue")
            return {"CANCELLED"}
        if not (settings.bake_base_color or settings.bake_normal):
            self.report({"WARNING"}, "Enable Base Color or Normal before running the AutoBake queue")
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        self.entries = list(settings.autobake_queue)
        self.current = None
        for entry in self.entries:
            entry.state, entry.message = "PENDING", ""
        settings.autobake_queue_running = True
        return self.start_job(context, self.steps(context), modal=not bpy.app.background)

    def update_job(self, context, fraction, message):
        settings = self._job_scene.polygroups_baking_settings
        settings.autobake_queue_progress = fraction * 100
        settings.autobake_queue_status = message
        _redraw_bake_ui(context)

    def advance_job(self, context):
        settings = self._job_scene.polygroups_baking_settings
        if self.stop_requested and settings.bake_task_is_running:
            settings.autobake_queue_status = "Stopping after current bake"
            return {"RUNNING_MODAL"}
        return super().advance_job(context)

    def steps(self, context):
        settings = self._job_scene.polygroups_baking_settings
        total = len(self.entries)
        output_names = Counter(_safe_path_name(bake_output_name(entry.target)).casefold()
                               for entry in self.entries if entry.target)
        with preserved_selection(context):
            for index, entry in enumerate(self.entries):
                self.current = entry
                entry.state, entry.message = "RUNNING", ""
                target = entry.target
                label = f"{index + 1}/{total}: {target.name if target else 'Missing target'}"
                try:
                    if target is None or target.name not in context.scene.objects or target.type != "MESH":
                        raise ValueError("Queued low-poly is missing from this scene")
                    if not target.data.uv_layers:
                        raise ValueError("Low-poly has no UV map")
                    source = entry.source
                    if not entry.manual_source:
                        source, expected, collection = find_matching_highpoly(target)
                        if source is None:
                            owner = collection.name if collection else "Generated.N"
                            raise ValueError(f"{expected or 'High-poly'} not found in {owner}")
                    if source is None or source.name not in context.scene.objects or source.type != "MESH":
                        raise ValueError("Queued high-poly is missing from this scene")
                    if output_names[_safe_path_name(bake_output_name(target)).casefold()] > 1:
                        # AutoBake normally names textures by Generated.N; avoid sharing files between targets.
                        target["polygroups_bake_output_suffix"] = target.name
                    with ExitStack() as stack:
                        for obj in (target, source):
                            stack.enter_context(export_visibility(context, obj))
                        for obj in context.selected_objects:
                            obj.select_set(False)
                        source.select_set(True)
                        target.select_set(True)
                        context.view_layer.objects.active = target
                        settings.bake_task_stage = ""
                        settings.bake_task_message = ""
                        self._autobake_dispatching = True
                        try:
                            result = bpy.ops.object.polygroups_bake_task(
                                "EXEC_DEFAULT", prepare_materials=True, align_source=entry.manual_source,
                                require_texture_save=True,
                            )
                        finally:
                            self._autobake_dispatching = False
                        if not {"FINISHED", "RUNNING_MODAL"} & result:
                            raise RuntimeError(settings.bake_task_message or "AutoBake could not start")
                        while settings.bake_task_is_running:
                            yield (index + settings.bake_task_progress / 100) / total, (
                                f"{label} | {settings.bake_task_message}"
                            )
                        if settings.bake_task_stage != "DONE":
                            raise RuntimeError(settings.bake_task_message or "AutoBake failed")
                    entry.state, entry.message = "DONE", "Textures saved"
                except (ValueError, RuntimeError, OSError, ReferenceError) as error:
                    entry.state, entry.message = "FAILED", str(error).removeprefix("Error: ").strip()
                yield (index + 1) / total, f"{label} | {entry.message}"
        self.current = None

    def finish_job(self, context, stopped=False, error=""):
        if self._job_done:
            return self._job_result
        settings = self._job_scene.polygroups_baking_settings
        if self.current is not None and self.current.state == "RUNNING":
            self.current.state = "DONE" if settings.bake_task_stage == "DONE" else "CANCELLED"
            self.current.message = settings.bake_task_message
        counts = Counter(entry.state for entry in self.entries)
        failed = counts["FAILED"]
        summary = f"{counts['DONE']}/{len(self.entries)} baked"
        if failed:
            summary += f" | {failed} failed"
        if stopped:
            summary += " | Stopped"
        result = super().finish_job(context, stopped=stopped, error=error)
        settings.autobake_queue_running = False
        settings.autobake_queue_status = error or summary
        if not stopped and not error:
            self.report({"WARNING" if failed else "INFO"}, summary)
            if failed and not counts["DONE"]:
                self._job_result = result = {"CANCELLED"}
        _redraw_bake_ui(context)
        return result


CLASSES = (OBJECT_OT_polygroups_autobake_queue_edit, OBJECT_OT_polygroups_autobake_queue_run)
