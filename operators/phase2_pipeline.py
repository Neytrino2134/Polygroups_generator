"""Single owner of the sequential Phase 2 queue and its lifecycle."""
import json
import time

import bpy
from bpy.app.handlers import persistent

ACTIVE_PIPELINE = None
DISPATCHING = False


class Phase2Pipeline:
    def __init__(self, context, report):
        from .phase2_pipeline_stages import selected_stages
        self.scene, self.view_layer = context.scene, context.view_layer
        self.settings = self.scene.polygroups_model_preparation_settings
        self.report = report
        self.plan = selected_stages(self.settings)
        if self.settings.phase2_run_zbrush and self.settings.phase2_run_zbrush_at_end:
            # Cleanup deletes ZBrush sources, so keep it after the deferred job.
            tail = [entry for key in ('ZBRUSH', 'CLEANUP') for entry in self.plan if entry[0] == key]
            self.plan = [entry for entry in self.plan if entry[0] not in {'ZBRUSH', 'CLEANUP'}] + tail
        if not self.plan:
            raise ValueError('Select at least one Phase 2 pass')
        if self.settings.phase2_run_export and not any((self.settings.phase2_export_glb,
                self.settings.phase2_export_fbx, self.settings.phase2_export_gltf)):
            raise ValueError('Enable GLB, FBX or GLTF for Export Prepared')
        self.rows = [dict(key=key, label=label, state='PENDING', progress=0, seconds=0)
                     for key, label, _, _ in self.plan]
        self.index = 0
        self.iterator = None
        self.finished = False
        self.pause_requested = self.stop_requested = self.stop_after_stage = False
        self.paused = False
        self.saved = []
        self.zbrush_root = None
        self.zbrush_job = None
        self.started = self.stage_started = time.monotonic()
        self.fraction = 0
        self.overlay = None
        self.timer = None

    def override(self, settings, key, value):
        if not any(owner == settings and name == key for owner, name, _, _ in self.saved):
            self.saved.append((settings, key, getattr(settings, key), settings.is_property_set(key)))
        setattr(settings, key, value)

    def begin(self, context):
        global ACTIVE_PIPELINE
        ACTIVE_PIPELINE = self
        p = self.settings
        p.phase2_pipeline_running = True
        p.phase2_pipeline_paused = False
        p.phase2_pipeline_state = 'RUNNING'
        p.phase2_pipeline_done = 0
        p.phase2_pipeline_total = len(self.plan)
        p.phase2_pipeline_progress = p.phase2_pipeline_stage_progress = 0
        p.phase2_pipeline_detail_progress = 0
        p.phase2_pipeline_collection_times = '[]'
        p.phase2_pipeline_collection_seconds = 0
        p.phase2_pipeline_collection_index = p.phase2_pipeline_collection_total = 0
        p.phase2_pipeline_stage_eta = -1
        p.phase2_pipeline_status = 'Starting Phase 2'
        from ..core.phase2_progress import PipelineOverlay
        self.overlay = PipelineOverlay(context)
        self.publish(context)

    def detail(self, progress, text):
        self.settings.phase2_pipeline_detail_progress = min(100, max(0, progress))
        self.settings.phase2_pipeline_detail = text

    def publish(self, context):
        p = self.settings
        now = time.monotonic()
        p.phase2_pipeline_elapsed = now - self.started
        p.phase2_pipeline_stage_seconds = now - self.stage_started
        p.phase2_pipeline_paused = self.paused
        p.phase2_pipeline_done = self.index
        p.phase2_pipeline_progress = 100*(self.index + self.fraction)/len(self.plan)
        p.phase2_pipeline_stage_progress = 100*self.fraction
        if self.index < len(self.rows) and self.rows[self.index]['state'] != 'PENDING':
            row = self.rows[self.index]
            row.update(progress=100*self.fraction, seconds=round(now-self.stage_started, 1))
        p.phase2_pipeline_queue = json.dumps(self.rows)
        from ..core import run_progress
        key, label = (self.plan[self.index][:2] if self.index < len(self.plan) else ('', ''))
        p.phase2_pipeline_stage_label = label
        p.phase2_pipeline_prev_seconds = p.phase2_pipeline_avg_seconds = 0
        if key == 'RESTORE' and p.phase2_pipeline_collection_total:
            previous, average, remaining = run_progress.collection_estimate(
                run_progress.parse_timings(p.phase2_pipeline_collection_times),
                p.phase2_pipeline_collection_index, p.phase2_pipeline_collection_total,
                p.phase2_pipeline_collection_seconds)
            p.phase2_pipeline_prev_seconds, p.phase2_pipeline_avg_seconds = previous, average
            p.phase2_pipeline_stage_eta = remaining
        else:
            p.phase2_pipeline_stage_eta = run_progress.fraction_estimate(self.fraction, now - self.stage_started)
        from .import_queue import redraw
        redraw(context)

    def signal_zbrush(self, action):
        if self.zbrush_job is None:
            return
        root, job_id = self.zbrush_job
        try:
            target = root / 'job_control.json'
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(dict(job_id=job_id, action=action)), encoding='utf-8')
            temp.replace(target)
        except OSError as error:
            self.report({'WARNING'}, f'Cannot send ZBrush control: {error}')

    def control(self, action):
        p = self.settings
        if action == 'PAUSE':
            self.signal_zbrush('PAUSE')
            self.pause_requested = True
            p.phase2_pipeline_status = 'Pause requested: finishing current collection / file / image'
        elif action == 'RESUME':
            self.signal_zbrush('RESUME')
            self.pause_requested = self.paused = False
            p.phase2_pipeline_state = 'RUNNING'
            p.phase2_pipeline_status = 'Resuming Phase 2'
        elif action == 'STOP_STAGE':
            self.signal_zbrush('RESUME')
            self.stop_after_stage = True
            self.paused = self.pause_requested = False
            p.phase2_pipeline_status = 'Stop requested: finishing current pass'
        elif action == 'STOP_NOW':
            self.signal_zbrush('STOP')
            self.stop_requested = True
            self.paused = self.pause_requested = False
            p.phase2_pipeline_status = 'Stopping permanently at the next safe host boundary'

    def busy(self):
        bake = self.scene.polygroups_baking_settings
        return bake.bake_task_is_running or bpy.app.is_job_running('OBJECT_BAKE') or bpy.app.is_job_running('RENDER')

    def step(self, context):
        global DISPATCHING
        if self.finished:
            return
        try:
            if self.stop_requested:
                if self.busy():
                    self.publish(context)
                    return
                self.finish(context, 'STOPPED')
                return
            if self.paused:
                self.publish(context)
                return
            if self.index >= len(self.plan):
                self.finish(context, 'COMPLETED')
                return
            if self.iterator is None:
                self.stage_started = time.monotonic()
                self.fraction = 0
                self.rows[self.index]['state'] = 'RUNNING'
                self.detail(0, self.plan[self.index][1])
                self.iterator = iter(self.plan[self.index][3](self, context))
            DISPATCHING = True
            try:
                fraction, text, boundary = next(self.iterator)
            except StopIteration:
                self.rows[self.index].update(state='DONE', progress=100,
                    seconds=round(time.monotonic()-self.stage_started, 1))
                self.iterator = None
                self.index += 1
                self.fraction = 0
                if self.stop_after_stage:
                    self.finish(context, 'STOPPED')
                    return
                if self.pause_requested and self.index < len(self.plan):
                    self.paused = True
                    self.settings.phase2_pipeline_state = 'PAUSED'
                    self.settings.phase2_pipeline_status = 'Paused after pass'
                self.publish(context)
                return
            finally:
                DISPATCHING = False
            self.fraction = max(self.fraction, min(1, max(0, fraction)))
            if not self.pause_requested and not self.stop_after_stage:
                self.settings.phase2_pipeline_status = text
            if self.plan[self.index][0] not in {'RESTORE', 'ZBRUSH', 'RENDER'}:
                self.detail(100*self.fraction, text)
            if boundary and self.pause_requested:
                self.paused = True
                self.settings.phase2_pipeline_state = 'PAUSED'
                self.settings.phase2_pipeline_status = 'Paused after current item'
            self.publish(context)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            self.finish(context, 'FAILED', str(error))

    def finish(self, context, state, error=''):
        global ACTIVE_PIPELINE, DISPATCHING
        if self.finished:
            return
        self.finished = True
        if state in {"STOPPED", "FAILED"}:
            self.signal_zbrush("STOP")
        DISPATCHING = True
        try:
            if self.iterator is not None:
                self.iterator.close()
        except Exception as cleanup_error:
            error = error or str(cleanup_error)
            state = 'FAILED'
        finally:
            DISPATCHING = False
            for settings, name, value, was_set in reversed(self.saved):
                setattr(settings, name, value) if was_set else settings.property_unset(name)
            self.saved.clear()
            if self.index < len(self.rows):
                self.rows[self.index]['state'] = 'SKIPPED' if self.rows[self.index]['state'] == 'PENDING' else state
            for row in self.rows[self.index+1:]:
                row['state'] = 'SKIPPED'
            self.paused = self.pause_requested = False
            self.settings.phase2_pipeline_running = False
            self.settings.phase2_pipeline_paused = False
            self.settings.phase2_pipeline_state = state
            self.settings.phase2_pipeline_status = f'{state}: {error}' if error else f'Phase 2 {state.lower()}'
            if state == 'COMPLETED':
                self.index = len(self.plan)
                self.fraction = 0
            self.publish(context)
            from ..core.run_progress import end_combined
            end_combined()
            if self.overlay:
                self.overlay.close()
            if self.timer is not None:
                context.window_manager.event_timer_remove(self.timer)
                self.timer = None
            if ACTIVE_PIPELINE is self:
                ACTIVE_PIPELINE = None


@persistent
def stop_pipeline(*_):
    if ACTIVE_PIPELINE is not None:
        ACTIVE_PIPELINE.finish(bpy.context, 'STOPPED')


class OBJECT_OT_polygroups_start_phase2(bpy.types.Operator):
    bl_idname = 'object.polygroups_start_phase2'
    bl_label = 'Start Phase 2 Process'
    bl_description = 'Run all enabled Phase 2 passes sequentially with one queue'

    @classmethod
    def poll(cls, context):
        from .phase2_processing import available
        from .zbrush_cleanup import cleanup_pending
        return context.mode == 'OBJECT' and ACTIVE_PIPELINE is None and available(context) and not cleanup_pending()

    def execute(self, context):
        try:
            run = Phase2Pipeline(context, self.report)
            run.begin(context)
        except Exception as error:
            if ACTIVE_PIPELINE is not None:
                ACTIVE_PIPELINE.finish(context, 'FAILED', str(error))
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.run = run
        if bpy.app.background:
            while not run.finished:
                run.step(context)
                if not run.finished:
                    time.sleep(.01)
            return {'CANCELLED'} if run.settings.phase2_pipeline_state == 'FAILED' else {'FINISHED'}
        run.timer = context.window_manager.event_timer_add(.15, window=context.window)
        self._next_tick = time.monotonic()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        run = self.run
        if run.finished:
            return {'CANCELLED'} if run.settings.phase2_pipeline_state == 'FAILED' else {'FINISHED'}
        if event.type == 'ESC' and event.value == 'PRESS':
            run.control('STOP_NOW')
        if event.type == 'TIMER' and time.monotonic() >= self._next_tick:
            self._next_tick = time.monotonic() + .15
            with context.temp_override(scene=run.scene, view_layer=run.view_layer):
                run.step(context)
        return {'PASS_THROUGH'}


class OBJECT_OT_polygroups_phase2_pipeline_control(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_pipeline_control'
    bl_label = 'Phase 2 Queue Control'
    action: bpy.props.EnumProperty(items=(('PAUSE', 'Pause after Current', ''),
        ('RESUME', 'Resume', ''), ('STOP_STAGE', 'Stop after Stage', ''), ('STOP_NOW', 'Stop Now', '')))

    @classmethod
    def poll(cls, context):
        return ACTIVE_PIPELINE is not None

    def execute(self, context):
        ACTIVE_PIPELINE.control(self.action)
        ACTIVE_PIPELINE.publish(context)
        return {'FINISHED'}
