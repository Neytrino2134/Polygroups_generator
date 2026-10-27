"""GUI host: real asynchronous bakes are serial and stop after the current item."""
import sys
import tempfile
import time
import traceback
from pathlib import Path
import addon_utils
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import baking,sequential_jobs
LOG=ROOT/'rebake_queue_modal.log';LOG.write_text('STARTING\n',encoding='utf-8')
temporary=tempfile.TemporaryDirectory(dir=ROOT,prefix='test_rebake_queue_modal_')
state=dict(phase='START',started=time.monotonic(),seen=[])


def fixture(context,index):
    scene=context.scene;asset=f'ModalQueue_00_{index:02d}'
    col=bpy.data.collections.new(asset+'_Collection');scene.collection.children.link(col)
    for high,z in ((False,0),(True,.02)):
        mesh=bpy.data.meshes.new(asset)
        mesh.from_pydata([(-1,-1,z),(1,-1,z),(1,1,z),(-1,1,z)],[],[(0,1,2,3)])
        layer=mesh.uv_layers.new()
        for loop,xy in zip(layer.data,((0,0),(1,0),(1,1),(0,1))):loop.uv=xy
        obj=bpy.data.objects.new(f'Resculpting_01_Highpoly_Generated.{index:03d}' if high else 'SM_'+asset+'_MID',mesh)
        col.objects.link(obj)
        material=bpy.data.materials.new(asset+str(high));material.use_nodes=True
        obj.data.materials.append(material)
        if high:
            material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(0,1,0,1)
        else:
            target=obj
            image=bpy.data.images.new('T_'+asset+'_BaseColor',width=16,height=16)
            image.generated_color=(1,0,0,1);image.filepath_raw=str(Path(temporary.name)/(image.name+'.png'))
            image.file_format='PNG';image.save()
            material.node_tree.nodes.new('ShaderNodeTexImage').image=image
    return target


def launch(context):
    target=context.scene.polygroups_model_preparation_settings.phase2_rebake_queue[0].target
    context.view_layer.objects.active=target;target.select_set(True)
    assert bpy.ops.object.polygroups_rebake_final_mesh(use_queue=True,repair_mesh=True)=={'RUNNING_MODAL'}


def tick():
    try:
        if time.monotonic()-state['started']>65:raise TimeoutError(state)
        window=bpy.context.window_manager.windows[0]
        area=next(area for area in window.screen.areas if area.type=='VIEW_3D')
        region=next(region for region in area.regions if region.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            context=bpy.context;scene=context.scene;p=scene.polygroups_model_preparation_settings
            if state['phase']=='START':
                bpy.ops.wm.save_as_mainfile(filepath=str(Path(temporary.name)/'Working.blend'))
                scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
                bake=scene.polygroups_baking_settings
                bake.bake_base_color=True;bake.bake_normal=False;bake.bake_artifact_mask=False;bake.bake_artifact_autofill=False
                bake.use_auto_cage=True;bake.use_smart_cage=False;bake.autogenerate_smart_cage=False
                for index in (1,2):p.phase2_rebake_queue.add().target=fixture(context,index)
                launch(context);state['phase']='RUN_ALL';return .15
            task=baking._ACTIVE_BAKE_TASK
            if task is not None and task.target.name not in state['seen']:state['seen'].append(task.target.name)
            if state['phase']=='RUN_ALL':
                if sequential_jobs.ACTIVE_JOB is not None:return .15
                assert [entry.state for entry in p.phase2_rebake_queue]==['DONE','DONE']
                assert state['seen']==[entry.target.name for entry in p.phase2_rebake_queue],state
                assert not p.phase2_rebake_queue_running and task is None and p.phase2_rebake_queue_progress==100
                state['seen']=[];launch(context);state['phase']='STOP_CURRENT';return .15
            if state['phase']=='STOP_CURRENT':
                if task is None:return .15
                assert bpy.ops.object.polygroups_stop_lod_job()=={'FINISHED'}
                assert p.phase2_rebake_queue_running
                state['phase']='WAIT_STOP';return .15
            if sequential_jobs.ACTIVE_JOB is not None:return .15
            assert [entry.state for entry in p.phase2_rebake_queue]==['DONE','PENDING']
            assert state['seen']==[p.phase2_rebake_queue[0].target.name],state
            assert task is None and not p.phase2_rebake_queue_running
            LOG.write_text('REBAKE_QUEUE_MODAL_SERIAL_AND_STOP_AFTER_CURRENT_OK\n',encoding='utf-8')
        temporary.cleanup();bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc(),encoding='utf-8');bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick,first_interval=1)
