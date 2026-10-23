"""Cooperative, stoppable UI jobs; each generator yield is an interrupt boundary."""
import bpy
from bpy.app.handlers import persistent

ACTIVE_JOB = None


@persistent
def stop_jobs(*args):
    if ACTIVE_JOB is not None:
        ACTIVE_JOB.finish_job(bpy.context, stopped=True)


class SequentialJob:
    def update_job(self, context, fraction, message):
        s = context.scene.polygroups_mesh_finalization_settings
        s.smart_lods_progress = min(100, max(0, fraction * 100))
        s.smart_lods_status = f'{s.smart_lods_progress:.0f}% | {message}'
        context.window_manager.progress_update(s.smart_lods_progress)
        if context.workspace:
            context.workspace.status_text_set(s.smart_lods_status)
        if getattr(self, 'phase2_job', False):
            p = context.scene.polygroups_model_preparation_settings
            p.phase2_status = s.smart_lods_status
            p.phase2_final_progress = s.smart_lods_progress
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    def start_job(self, context, iterator, modal=False):
        global ACTIVE_JOB
        if ACTIVE_JOB is not None:
            self.report({'ERROR'}, 'Another LOD/finalization job is running')
            return {'CANCELLED'}
        self._job_context = context.copy()
        self._iterator = iterator
        self._job_timer = None
        self._job_done = False
        self.stop_requested = False
        self._job_scene = context.scene
        self._job_workspace = context.workspace
        ACTIVE_JOB = self
        context.scene.polygroups_mesh_finalization_settings.smart_lods_is_running = True
        if getattr(self, 'phase2_job', False):
            context.scene.polygroups_model_preparation_settings.phase2_final_is_running = True
            context.scene.polygroups_model_preparation_settings.phase2_total_count = 0
        context.window_manager.progress_begin(0, 100)
        self.update_job(context, 0, 'Starting')
        if modal and not bpy.app.background:
            self._job_timer = context.window_manager.event_timer_add(.1, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        while not self._job_done:
            self.advance_job(context)
        return self._job_result

    def advance_job(self, context):
        if self.stop_requested:
            return self.finish_job(context, stopped=True)
        try:
            fraction, message = next(self._iterator)
            self.update_job(context, fraction, message)
        except StopIteration:
            return self.finish_job(context)
        except Exception as error:
            self.report({'WARNING'} if isinstance(error, ValueError) else {'ERROR'}, str(error))
            return self.finish_job(context, error=str(error))
        return {'RUNNING_MODAL'}

    def finish_job(self, context, stopped=False, error=''):
        global ACTIVE_JOB
        if self._job_done:
            return self._job_result
        self._job_done = True
        try:
            self._iterator.close()
        except Exception as cleanup_error:
            error = error or str(cleanup_error)
        if self._job_timer:
            context.window_manager.event_timer_remove(self._job_timer)
            self._job_timer = None
        s = self._job_scene.polygroups_mesh_finalization_settings
        s.smart_lods_is_running = False
        if not stopped and not error:
            s.smart_lods_progress = 100
        s.smart_lods_status = ('Failed: ' + error if error else
            'Stopped' if stopped else 'Completed') + f' | {s.smart_lods_progress:.0f}%'
        if getattr(self, 'phase2_job', False):
            p = self._job_scene.polygroups_model_preparation_settings
            p.phase2_final_is_running = False
            p.phase2_status = s.smart_lods_status
            p.phase2_final_progress = s.smart_lods_progress
        context.window_manager.progress_end()
        if self._job_workspace:
            self._job_workspace.status_text_set(None)
        ACTIVE_JOB = None
        self._job_result = {'CANCELLED'} if error else {'FINISHED'}
        return self._job_result

    def modal(self, context, event):
        if self._job_done:
            return self._job_result
        if event.type == 'ESC' and event.value == 'PRESS':
            self.stop_requested = True
        if event.type == 'TIMER' or self.stop_requested:
            # Bind all operations to the scene/view layer where the job began.
            with context.temp_override(scene=self._job_scene,
                    view_layer=self._job_context['view_layer']):
                return self.advance_job(context)
        return {'PASS_THROUGH'}


class OBJECT_OT_polygroups_stop_lod_job(bpy.types.Operator):
    bl_idname = 'object.polygroups_stop_lod_job'
    bl_label = 'Stop Processing'
    bl_description = 'Stop at the next LOD boundary; completed assets are retained'

    @classmethod
    def poll(cls, context):
        return ACTIVE_JOB is not None

    def execute(self, context):
        ACTIVE_JOB.stop_requested = True
        return {'FINISHED'}
