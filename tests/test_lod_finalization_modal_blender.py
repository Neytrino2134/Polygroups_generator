"""Run without --background: actual modal progress, stop, then Batch Finalization."""
import sys,tempfile,time,traceback,shutil
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
started=time.monotonic();state={}

def finish(error=''):
 if error: print('LOD_MODAL_FAILED',error,flush=True)
 else: print('LOD_MODAL_STOP_AND_FINALIZATION_PASSED',flush=True)
 if state.get("directory"):
  shutil.rmtree(state["directory"])
 bpy.ops.wm.quit_blender()
 return None

def context_override():
 window=bpy.context.window_manager.windows[0]
 area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
 region=next(r for r in area.regions if r.type=='WINDOW')
 return bpy.context.temp_override(window=window,area=area,region=region)

def check():
 try:
  if time.monotonic()-started>40:raise RuntimeError('Timeout')
  s=bpy.context.scene.polygroups_mesh_finalization_settings
  from polygroups_generator.operators import sequential_jobs as jobs
  if state['stage']=='SMART':
   if .4<s.smart_lods_progress/100<.99 and not state.get('stopping'):
    assert s.smart_lods_is_running
    bpy.ops.object.polygroups_stop_lod_job();state['stopping']=True
   if not s.smart_lods_is_running:
    assert state.get('stopping') and s.smart_lods_status.startswith('Stopped'),s.smart_lods_status
    assert len([o for o in bpy.data.objects if o.get('polygroups_lod_source')])==2
    assert jobs.ACTIVE_JOB is None
    for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    col=bpy.data.collections.new('Generated.001');bpy.context.scene.collection.children.link(col)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8)
    source=bpy.context.object;source.name='Retopo_12_Highpoly_Generated.001'
    for old in list(source.users_collection):old.objects.unlink(source)
    col.objects.link(source);col.hide_viewport=True
    p=bpy.context.scene.polygroups_model_preparation_settings
    p.phase2_final_lod_engine='UNREAL';p.phase2_final_rename_engine='FAB'
    s.unreal_lod_prepare_materials=False
    with context_override():
     assert bpy.ops.object.polygroups_batch_finalization('EXEC_DEFAULT',asset='desert stones',name_index='08',version_index='01')=={'RUNNING_MODAL'}
    state['stage']='FINAL'
  elif state['stage']=='FINAL':
   p=bpy.context.scene.polygroups_model_preparation_settings
   if p.phase2_final_is_running:
    state['final_progress']=state.get('final_progress',False) or 0<p.phase2_final_progress<100
   else:
    assert p.phase2_final_progress==100 and state.get('final_progress'),p.phase2_status
    assert all('SM_Desert_Stones_08_01'+suffix in bpy.data.objects for suffix in ('_MID','_LOD0','_LOD1'))
    assert jobs.ACTIVE_JOB is None
    return finish()
  return .03
 except Exception:
  return finish(traceback.format_exc())

def start():
 try:
  bpy.context.preferences.use_preferences_save=False
  addon_utils.enable(ROOT.name,default_set=True)
  directory=Path(tempfile.mkdtemp(dir=ROOT,prefix='test_lod_modal_'))
  state['directory']=directory
  bpy.ops.wm.save_as_mainfile(filepath=str(directory/'Working.blend'))
  for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
  sources=[]
  for i in range(3):
   bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8);obj=bpy.context.object;obj.name=f'Source{i}';sources.append(obj)
  bpy.ops.object.select_all(action='DESELECT')
  for source in sources:source.select_set(True)
  bpy.context.view_layer.objects.active=sources[0]
  s=bpy.context.scene.polygroups_mesh_finalization_settings
  s.smart_lods_count=2;s.smart_lods_target_1=80;s.smart_lods_target_2=40
  with context_override():
   assert bpy.ops.object.polygroups_generate_smart_lods('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
  state['stage']='SMART'
  bpy.app.timers.register(check,first_interval=.03)
 except Exception:return finish(traceback.format_exc())
 return None
bpy.app.timers.register(start,first_interval=.5)
