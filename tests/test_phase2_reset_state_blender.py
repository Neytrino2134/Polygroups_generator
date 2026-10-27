"""Recover stale status, owned generators/timers and cleanup failures safely."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_reset as reset, phase2_pipeline as pipeline
from polygroups_generator.operators import phase2_pipeline_stages as stages, phase2_processing as phase
from polygroups_generator.operators import baking, import_queue, zbrush_cleanup, sequential_jobs
from polygroups_generator.custom_ui.schema import capture,walk

context=bpy.context
p=context.scene.polygroups_model_preparation_settings
bake=context.scene.polygroups_baking_settings
final=context.scene.polygroups_mesh_finalization_settings
render=context.scene.polygroups_render_settings


def assert_ready():
    assert pipeline.ACTIVE_PIPELINE is None and not pipeline.DISPATCHING
    assert phase.ACTIVE_PHASE2 is None and baking._ACTIVE_BAKE_TASK is None
    assert not any((p.phase2_pipeline_running,p.phase2_pipeline_paused,p.phase2_is_running,
                   p.phase2_final_is_running,p.phase2_auto_render_running,bake.bake_task_is_running,
                   final.smart_lods_is_running,render.is_running))
    assert p.phase2_pipeline_queue=='[]' and p.phase2_pipeline_status=='Ready'
    assert p.phase2_pipeline_collection_times=='[]' and p.phase2_status=='Ready'
    assert p.phase2_pipeline_progress==p.phase2_pipeline_stage_progress==p.phase2_pipeline_detail_progress==0
    assert p.phase2_pipeline_done==p.phase2_pipeline_total==p.phase2_done_count==p.phase2_failed_count==0
    assert not bake.bake_task_stage and bake.bake_task_progress==0


with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_phase2_reset_') as directory:
    root=Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
    retained=root/'completed.fbx';retained.write_bytes(b'completed output')
    mesh=context.active_object.data
    mesh_before=[tuple(vertex.co) for vertex in mesh.vertices]
    options=('phase2_run_mode','phase2_run_resculpt_retopo01','phase2_run_high_remesh',
             'phase2_rebake_create_lods','phase2_rebake_export_selected','phase2_run_export')
    saved_options={name:getattr(p,name) for name in options}

    p.phase2_pipeline_running=p.phase2_pipeline_paused=True
    p.phase2_pipeline_state='FAILED';p.phase2_pipeline_status='crash'
    p.phase2_pipeline_progress=72;p.phase2_pipeline_stage_progress=58;p.phase2_pipeline_detail_progress=41
    p.phase2_pipeline_done=3;p.phase2_pipeline_total=7;p.phase2_pipeline_queue='not valid JSON'
    p.phase2_pipeline_elapsed=123;p.phase2_pipeline_collection_times='["stale"]'
    p.phase2_is_running=p.phase2_final_is_running=p.phase2_auto_render_running=True
    p.phase2_done_count=5;p.phase2_failed_count=2;p.phase2_total_count=12
    p.phase2_autosave_status='stale autosave failure'
    bake.bake_task_is_running=True;bake.bake_task_stage='NORMAL_WAIT';bake.bake_task_progress=68
    final.smart_lods_is_running=True;render.is_running=True
    assert bpy.ops.object.polygroups_phase2_reset_state.poll()
    panel=capture(context,1)
    assert not panel.errors,panel.errors
    buttons=[node for node in walk(panel.node) if node.get('kind')=='button'
             and 'polygroups_phase2_reset_state' in node.get('id','')]
    assert len(buttons)==1 and buttons[0]['enabled'],buttons
    assert bpy.ops.object.polygroups_phase2_reset_state()=={'FINISHED'}
    assert_ready()
    assert saved_options=={name:getattr(p,name) for name in options}
    assert mesh_before==[tuple(vertex.co) for vertex in mesh.vertices]
    assert retained.read_bytes()==b'completed output'
    assert bpy.ops.object.polygroups_start_phase2.poll()

    # Actual host jobs are never force-reset, even when status is stale.
    for busy in ('OBJECT_BAKE','RENDER'):
        proxy=SimpleNamespace(app=SimpleNamespace(is_job_running=lambda kind:kind==busy))
        with patch.object(reset,'bpy',proxy):
            assert not reset.reset_available(context)
            try:reset.reset_phase2_state(context)
            except RuntimeError:pass
            else:raise AssertionError('Busy Blender job was reset')

    events=[]
    previous=p.phase2_auto_bake
    def pending(run,ctx):
        run.override(p,'phase2_auto_bake',not previous)
        try:
            events.append('started')
            yield .4,'Waiting',False
            events.append('must not resume')
        finally:events.append('closed')
    plan=[('TEST','Test','phase2_run_restore',pending)]
    with patch.object(stages,'STAGES',plan):
        run=pipeline.Phase2Pipeline(context,lambda *_:None);run.begin(context);run.step(context)
    run.timer=context.window_manager.event_timer_add(.1,window=context.window)
    assert p.phase2_auto_bake!=previous
    assert reset.reset_phase2_state(context)==[]
    assert events==['started','closed'] and run.finished and run.timer is None
    assert not run.saved and run.iterator is None and run.overlay is None
    assert p.phase2_auto_bake==previous
    run.step(context)
    assert events==['started','closed']
    assert_ready()

    # A broken stage finalizer cannot prevent option restoration or ownership reset.
    def broken(run,ctx):
        run.override(p,'phase2_auto_bake',not previous)
        try:yield .2,'Broken cleanup',False
        finally:raise RuntimeError('injected stage cleanup failure')
    with patch.object(stages,'STAGES',[('BROKEN','Broken','phase2_run_restore',broken)]):
        run=pipeline.Phase2Pipeline(context,lambda *_:None);run.begin(context);run.step(context)
    warnings=reset.reset_phase2_state(context)
    assert any('injected stage cleanup failure' in message for message in warnings),warnings
    assert p.phase2_auto_bake==previous
    assert_ready()

    # Orphaned restore/remesh jobs and idle bake coordinators also clean up.
    queue=phase.Phase2Queue(context,[('mock','Generated.001')],True,False,lambda *_:None)
    queue.begin();queue.mid_remesh=SimpleNamespace(abort=lambda:events.append('abort remesh'))
    queue.timer=context.window_manager.event_timer_add(.1,window=context.window)
    phase.ACTIVE_PHASE2=queue
    session=SimpleNamespace(close=lambda success:events.append(('session restore',success)),
                            cleanup_import=lambda:events.append('remove temporary highpoly'))
    task=SimpleNamespace(settings=bake,_task_finished=False,
                         projection=SimpleNamespace(close=lambda:events.append('projection close')),
                         final_rebake_session=session,render_visibility={},
                         _finish=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('injected bake cleanup failure')))
    baking._ACTIVE_BAKE_TASK=task
    warnings=reset.reset_phase2_state(context)
    assert any('injected bake cleanup failure' in message for message in warnings)
    assert 'abort remesh' in events and ('session restore',False) in events
    assert 'remove temporary highpoly' in events and 'projection close' in events
    assert queue.finished and queue.timer is None and task._task_finished
    assert_ready()

    # Pending ZBrush cleanup is disarmed; completed files remain on disk.
    zbrush_cleanup._WATCH=dict(scene=context.scene,root=root,job_id='reset-test')
    bpy.app.timers.register(zbrush_cleanup.poll_success,first_interval=100)
    assert reset.reset_phase2_state(context)==[]
    assert zbrush_cleanup._WATCH is None and not bpy.app.timers.is_registered(zbrush_cleanup.poll_success)
    assert json.loads((root/'job_control.json').read_text())==dict(job_id='reset-test',action='STOP')
    assert retained.read_bytes()==b'completed output'
    assert_ready()

    # A real idle BakeTask is finalized once, with its visibility restored.
    target=context.active_object
    bpy.ops.mesh.primitive_cube_add(location=(0,0,3))
    high=context.active_object
    target.select_set(True);high.select_set(True);context.view_layer.objects.active=target
    bake.bake_base_color=True;bake.bake_normal=False
    def reset_idle_bake(task,ctx):
        assert baking._ACTIVE_BAKE_TASK == task
        assert reset.reset_phase2_state(ctx)==[]
        assert task._task_finished and baking._ACTIVE_BAKE_TASK is None
        return task._task_result
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_step',reset_idle_bake):
        assert bpy.ops.object.polygroups_bake_task('EXEC_DEFAULT')=={'CANCELLED'}
    assert_ready()

    def finalization():
        try:yield None
        finally:events.append('finalization closed')
    iterator=finalization();next(iterator)
    job=SimpleNamespace(phase2_job=True,_job_scene=context.scene,_iterator=iterator,
        _job_timer=context.window_manager.event_timer_add(.1,window=context.window),
        _preview=SimpleNamespace(close=lambda:events.append('preview closed')),
        finish_job=lambda *args,**kwargs:events.append('finalization stopped'))
    sequential_jobs.ACTIVE_JOB=job
    assert reset.reset_phase2_state(context)==[]
    assert job._job_done and job._job_timer is None and sequential_jobs.ACTIVE_JOB is None
    assert 'finalization closed' in events and 'preview closed' in events
    assert_ready()

    # An unrelated import/LOD job cannot be stopped through this button.
    import_queue.ACTIVE_QUEUE=object()
    assert not reset.reset_available(context)
    import_queue.ACTIVE_QUEUE=None
    sequential_jobs.ACTIVE_JOB=SimpleNamespace(phase2_job=False)
    assert not reset.reset_available(context)
    sequential_jobs.ACTIVE_JOB=None
    assert reset.reset_phase2_state(context)==[]  # repeated reset is harmless
print('PHASE2_RESET_STATE_RECOVERY_AND_UI_OK',flush=True)
