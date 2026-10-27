"""GUI host: Reset detaches old modal pipeline and bake timers/overlays."""
import sys
import tempfile
import time
import traceback
from pathlib import Path

import addon_utils
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_pipeline as pipeline, phase2_pipeline_stages as stages
from polygroups_generator.operators import baking

LOG=ROOT/'phase2_reset_modal.log'
LOG.write_text('STARTING\n',encoding='utf-8')
temporary=tempfile.TemporaryDirectory(dir=ROOT,prefix='test_reset_modal_')
state=dict(phase='START',started=time.monotonic(),events=[])
original_stages=stages.STAGES


def pending(run,context):
    try:
        while True:
            state['events'].append('step')
            yield .3,'Pending reset',True
    finally:state['events'].append('closed')


def tick():
    try:
        if time.monotonic()-state['started']>25:raise TimeoutError(state)
        window=bpy.context.window_manager.windows[0]
        area=next(area for area in window.screen.areas if area.type=='VIEW_3D')
        region=next(region for region in area.regions if region.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            context=bpy.context
            p=context.scene.polygroups_model_preparation_settings
            if state['phase']=='START':
                bpy.ops.wm.save_as_mainfile(filepath=str(Path(temporary.name)/'Working.blend'))
                stages.STAGES=[('RESET_TEST','Reset test','phase2_run_restore',pending)]
                assert bpy.ops.object.polygroups_start_phase2('EXEC_DEFAULT')=={'RUNNING_MODAL'}
                state['run']=pipeline.ACTIVE_PIPELINE
                state['phase']='RESET_PIPELINE'
                return .4
            if state['phase']=='RESET_PIPELINE':
                run=state['run']
                assert state['events'] and run.timer is not None and run.overlay.handle is not None
                assert bpy.ops.object.polygroups_phase2_reset_state()=={'FINISHED'}
                assert run.finished and run.timer is None and run.overlay is None
                assert pipeline.ACTIVE_PIPELINE is None and not p.phase2_pipeline_running
                state['event_count']=len(state['events'])
                state['phase']='START_BAKE'
                return .4
            if state['phase']=='START_BAKE':
                assert len(state['events'])==state['event_count'] and state['events'][-1]=='closed'
                target=context.active_object
                bpy.ops.mesh.primitive_cube_add(location=(0,0,3))
                high=context.active_object;target.select_set(True);high.select_set(True)
                context.view_layer.objects.active=target
                bake=context.scene.polygroups_baking_settings
                bake.bake_base_color=True;bake.bake_normal=False
                assert bpy.ops.object.polygroups_bake_task('EXEC_DEFAULT')=={'RUNNING_MODAL'}
                task=baking._ACTIVE_BAKE_TASK
                assert task is not None and baking._BAKE_CURSOR_HANDLE is not None
                assert bpy.ops.object.polygroups_phase2_reset_state()=={'FINISHED'}
                assert task._task_finished and task._timer is None
                assert baking._ACTIVE_BAKE_TASK is None and baking._BAKE_CURSOR_HANDLE is None
                state['phase']='DONE'
                return .4
            assert pipeline.ACTIVE_PIPELINE is None and not p.phase2_pipeline_running
            assert baking._ACTIVE_BAKE_TASK is None and not context.scene.polygroups_baking_settings.bake_task_is_running
            LOG.write_text('PHASE2_RESET_MODAL_PIPELINE_AND_BAKE_OK\n',encoding='utf-8')
        stages.STAGES=original_stages
        temporary.cleanup()
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc(),encoding='utf-8')
        stages.STAGES=original_stages
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick,first_interval=1)
