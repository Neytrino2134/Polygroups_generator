"""Remesh execution with progress retained in the sidebar."""

import time

import bpy
from bpy.app.handlers import persistent

from ..core.remesh_job import RemeshJob, remesh_backend
from .import_queue import redraw


ACTIVE_REMESH = None


def remesh_available(context):
    from . import import_queue
    return (ACTIVE_REMESH is None and import_queue.ACTIVE_QUEUE is None
            and context.active_object is not None and context.active_object.type == "MESH")


@persistent
def stop_remesh(*_args):
    global ACTIVE_REMESH
    if ACTIVE_REMESH is not None:
        ACTIVE_REMESH.finish(bpy.context, "CANCELLED")
        if ACTIVE_REMESH.timer is not None:
            bpy.context.window_manager.event_timer_remove(ACTIVE_REMESH.timer)
            ACTIVE_REMESH.timer = None
        ACTIVE_REMESH = None


class RemeshSession:
    def __init__(self, context, report):
        self.scene = context.scene
        self.view_layer = context.view_layer
        self.source = context.active_object
        self.status = self.scene.polygroups_remesh_status
        self.job = RemeshJob(remesh_backend(context), report)
        self.started = time.monotonic()
        self.timer = None
        self.done = False
        self.source_hidden = self.source.hide_get(view_layer=self.view_layer)
        self.status.is_running = True
        self.status.cancel_requested = False
        self.status.stage = "STARTING"
        self.status.source_name = self.source.name
        self.status.result_name = ""
        self.status.polygon_count = 0
        self.status.message = ""
        self.status.progress = 0
        self.status.elapsed_seconds = 0

    def select_source(self, context):
        if self.source.name not in self.view_layer.objects:
            raise RuntimeError("Source object is no longer in the View Layer")
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in context.selected_objects:
            obj.select_set(False)
        self.source.hide_set(False, view_layer=self.view_layer)
        self.source.select_set(True)
        self.view_layer.objects.active = self.source

    def step(self, context):
        if self.done:
            return
        self.status.elapsed_seconds = time.monotonic() - self.started
        if self.status.cancel_requested:
            self.finish(context, "CANCELLED")
            return
        try:
            if self.status.stage == "STARTING":
                self.select_source(context)
                self.job.start(context)
                self.status.stage = "RUNNING"
            elif self.status.stage == "RUNNING":
                done, progress = self.job.poll()
                self.status.progress = max(self.status.progress, min(99, progress * 99))
                self.status.message = self.job.message
                if done:
                    self.status.stage = "FINISHING"
            elif self.status.stage == "FINISHING":
                self.select_source(context)
                outputs = self.job.finish(context)
                meshes = [obj for obj in outputs if obj.type == "MESH"]
                self.status.polygon_count = sum(len(obj.data.polygons) for obj in meshes)
                self.status.result_name = ", ".join(obj.name for obj in meshes)
                self.status.progress = 100
                self.finish(context, "DONE")
        except Exception as error:
            self.status.message = str(error)
            self.finish(context, "FAILED")
        self.status.elapsed_seconds = time.monotonic() - self.started

    def finish(self, context, stage):
        if self.done:
            return
        if stage != "DONE":
            self.job.abort()
            if self.source in set(bpy.data.objects):
                self.source.hide_set(self.source_hidden, view_layer=self.view_layer)
        else:
            self.status.message = ""
        self.status.elapsed_seconds = time.monotonic() - self.started
        self.status.stage = stage
        self.status.is_running = False
        self.done = True
        redraw(context)


class OBJECT_OT_polygroups_run_remesh(bpy.types.Operator):
    bl_idname = "object.polygroups_run_remesh"
    bl_label = "Remesh with Progress"
    bl_options = {"UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return remesh_available(context)

    def execute(self, context):
        global ACTIVE_REMESH
        try:
            self._session = RemeshSession(context, self.report)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        ACTIVE_REMESH = self._session
        self._next_tick = time.monotonic() + 0.15
        self._session.timer = context.window_manager.event_timer_add(0.15, window=context.window)
        context.window_manager.modal_handler_add(self)
        redraw(context)
        return {"RUNNING_MODAL"}

    def cleanup(self, context):
        global ACTIVE_REMESH
        if self._session.timer is not None:
            context.window_manager.event_timer_remove(self._session.timer)
            self._session.timer = None
        if ACTIVE_REMESH is self._session:
            ACTIVE_REMESH = None

    def modal(self, context, event):
        if self._session.done:
            self.cleanup(context)
            return {"FINISHED"}
        if event.type == "ESC":
            self._session.status.cancel_requested = True
        elif event.type != "TIMER" or time.monotonic() < self._next_tick:
            return {"PASS_THROUGH"}
        self._next_tick = time.monotonic() + 0.15
        with context.temp_override(scene=self._session.scene, view_layer=self._session.view_layer):
            self._session.step(context)
        redraw(context)
        if self._session.done:
            self.cleanup(context)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def cancel(self, context):
        self._session.finish(context, "CANCELLED")
        self.cleanup(context)


class OBJECT_OT_polygroups_cancel_remesh(bpy.types.Operator):
    bl_idname = "object.polygroups_cancel_remesh"
    bl_label = "Cancel Remesh"

    @classmethod
    def poll(cls, context):
        return ACTIVE_REMESH is not None and not ACTIVE_REMESH.done

    def execute(self, context):
        ACTIVE_REMESH.status.cancel_requested = True
        return {"FINISHED"}
