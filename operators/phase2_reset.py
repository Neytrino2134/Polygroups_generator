"""Recover Phase 2 ownership and progress after an interrupted or failed run."""
import json

import bpy


def reset_available(context):
    if context.scene is None or any(bpy.app.is_job_running(kind) for kind in ('OBJECT_BAKE', 'RENDER')):
        return False
    from . import baking, import_queue, phase2_pipeline, phase2_processing, remesh_progress, sequential_jobs
    from . import render_queue, turnaround_animation
    # A Phase 2 reset must not take ownership of an unrelated manual job.
    if (import_queue.ACTIVE_QUEUE is not None or remesh_progress.ACTIVE_REMESH is not None
            or render_queue._ACTIVE_QUEUE_TASK is not None or turnaround_animation._ACTIVE_RENDER_TASK is not None):
        return False
    for owner in (phase2_pipeline.ACTIVE_PIPELINE, phase2_processing.ACTIVE_PHASE2):
        if owner is not None and owner.scene != context.scene:
            return False
    job = sequential_jobs.ACTIVE_JOB
    if job is not None and (not (getattr(job, 'phase2_job', False) or getattr(job, '_is_relod', False))
                            or job._job_scene != context.scene):
        return False
    task = baking._ACTIVE_BAKE_TASK
    if task is not None and task.settings != context.scene.polygroups_baking_settings:
        return False
    return True


def reset_phase2_state(context):
    """Close owned resources even if one cleanup failed; never delete results."""
    from . import baking, phase2_pipeline, phase2_processing, sequential_jobs, zbrush_cleanup
    from .import_queue import redraw
    if not reset_available(context):
        raise RuntimeError('Wait for the active Blender bake/render or unrelated job before resetting Phase 2')
    warnings = []

    def attempt(label, function):
        try:
            function()
        except Exception as error:
            warnings.append(f'{label}: {error}')

    def remove_timer(owner, name):
        timer = getattr(owner, name, None)
        if timer is not None:
            attempt('timer', lambda:context.window_manager.event_timer_remove(timer))
            setattr(owner, name, None)

    # Stop the bake coordinator between host bake jobs, including projection,
    # ReBake material/visibility changes and any appended temporary highpoly.
    task = baking._ACTIVE_BAKE_TASK
    if task is not None:
        attempt('bake task', lambda:task._finish(context, False, 'Phase 2 state reset', cancelled=True))
        if not getattr(task, '_task_finished', False):
            projection = getattr(task, 'projection', None)
            if projection is not None:
                attempt('projection', projection.close)
                task.projection = None
            session = getattr(task, 'final_rebake_session', None)
            if session is not None:
                attempt('rebake restore', lambda:session.close(False))
                attempt('temporary highpoly', session.cleanup_import)
                task.final_rebake_session = None
            attempt('bake visibility', lambda:baking._restore_bake_render_objects(
                getattr(task, 'render_visibility', {})))
            task.render_visibility = {}
            task._task_finished, task._task_result = True, {'CANCELLED'}
        remove_timer(task, '_timer')
        baking._ACTIVE_BAKE_TASK = None
    if baking._BAKE_CURSOR_HANDLE is not None:
        handle = baking._BAKE_CURSOR_HANDLE
        attempt('bake overlay', lambda:bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW'))
        baking._BAKE_CURSOR_HANDLE = None

    # Mark the old modal owner finished before closing generators. A later
    # queued timer event must never resume a reset run.
    run = phase2_pipeline.ACTIVE_PIPELINE
    if run is not None:
        run.finished = True
        run.stop_requested = True
        run.paused = run.pause_requested = False
        attempt('ZBrush stop', lambda:run.signal_zbrush('STOP'))
        phase2_pipeline.DISPATCHING = True
        try:
            if run.iterator is not None:
                attempt('pipeline stage', run.iterator.close)
                run.iterator = None
            for owner, name, value, was_set in reversed(run.saved):
                attempt('restore ' + name, lambda owner=owner,name=name,value=value,was_set=was_set:
                        setattr(owner,name,value) if was_set else owner.property_unset(name))
            run.saved.clear()
        finally:
            phase2_pipeline.DISPATCHING = False
        if run.overlay is not None:
            attempt('pipeline overlay', run.overlay.close)
            run.overlay = None
        remove_timer(run, 'timer')
        phase2_pipeline.ACTIVE_PIPELINE = None
    phase2_pipeline.DISPATCHING = False

    queue = phase2_processing.ACTIVE_PHASE2
    if queue is not None:
        attempt('restore queue', lambda:queue.finish(stopped=True))
        if queue.mid_remesh is not None:
            attempt('remesh abort', queue.mid_remesh.abort)
            queue.mid_remesh = None
        attempt('restore bake settings', queue.restore_bake_settings)
        queue.finished = True
        remove_timer(queue, 'timer')
        phase2_processing.ACTIVE_PHASE2 = None

    job = sequential_jobs.ACTIVE_JOB
    if job is not None:
        attempt('finalization job', lambda:job.finish_job(context, stopped=True))
        if getattr(job, '_iterator', None) is not None:
            attempt('finalization stage', job._iterator.close)
        job._job_done, job._job_result = True, {'CANCELLED'}
        remove_timer(job, '_job_timer')
        preview = getattr(job, '_preview', None)
        if preview is not None:
            attempt('render preview', preview.close)
        sequential_jobs.ACTIVE_JOB = None

    # A reset cancels pending success-cleanup, so a late ZBrush result cannot
    # remove the retained source collections after the UI has returned to Ready.
    watch = zbrush_cleanup._WATCH
    if watch is not None and watch.get('scene') == context.scene:
        def stop_watch():
            target = watch['root'] / 'job_control.json'
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(job_id=watch['job_id'], action='STOP')), encoding='utf-8')
            temporary.replace(target)
        attempt('ZBrush cleanup stop', stop_watch)
        zbrush_cleanup._WATCH = None
        if bpy.app.timers.is_registered(zbrush_cleanup.poll_success):
            attempt('ZBrush cleanup timer', lambda:bpy.app.timers.unregister(zbrush_cleanup.poll_success))

    p = context.scene.polygroups_model_preparation_settings
    for prop in p.bl_rna.properties:
        if prop.identifier.startswith('phase2_pipeline_'):
            p.property_unset(prop.identifier)
    for name in ('phase2_is_running', 'phase2_final_is_running', 'phase2_auto_render_running',
                 'phase2_done_count', 'phase2_failed_count', 'phase2_skipped_count', 'phase2_total_count',
                 'phase2_final_progress', 'phase2_autosave_status'):
        p.property_unset(name)
    for name in ('phase2_rebake_queue_running','phase2_rebake_queue_progress','phase2_rebake_queue_status'):
        p.property_unset(name)
    for name in ('phase2_relod_running', 'phase2_relod_progress', 'phase2_relod_status',
                 'phase2_relod_done', 'phase2_relod_total'):
        p.property_unset(name)
    for entry in p.phase2_rebake_queue:
        entry.state,entry.message='PENDING',''
    p.phase2_status = 'Ready'
    # No Import owner is running (checked above); clear only its stale blocker.
    p.batch_is_running = False
    bake = context.scene.polygroups_baking_settings
    for prop in bake.bl_rna.properties:
        if prop.identifier.startswith('bake_task_'):
            bake.property_unset(prop.identifier)
    final = context.scene.polygroups_mesh_finalization_settings
    for name in ('smart_lods_is_running', 'smart_lods_progress', 'smart_lods_status'):
        final.property_unset(name)
    render = context.scene.polygroups_render_settings
    render.is_running = render.stop_requested = False
    context.window_manager.progress_end()
    if context.workspace:
        context.workspace.status_text_set(None)
    redraw(context)
    return warnings


class OBJECT_OT_polygroups_phase2_reset_state(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_reset_state'
    bl_label = 'Reset State'
    bl_description = 'Stop interrupted Phase 2 tasks and clear their queue, timers and progress; retain meshes, exports and processing options'

    @classmethod
    def poll(cls, context):
        return reset_available(context)

    def execute(self, context):
        warnings = reset_phase2_state(context)
        self.report({'WARNING'} if warnings else {'INFO'},
                    'Phase 2 state reset' + ('; ' + '; '.join(warnings) if warnings else ''))
        return {'FINISHED'}
