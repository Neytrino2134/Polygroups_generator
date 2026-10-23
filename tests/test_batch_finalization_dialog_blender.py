"""UI dialog -> Start/Enter -> real modal Batch Finalization."""
import sys,tempfile,time,traceback,shutil
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
state={};started=time.monotonic()
def finish(error=''):
 print('BATCH_DIALOG_FAILED '+error if error else 'BATCH_DIALOG_START_PASSED',flush=True)
 if state.get('directory'):shutil.rmtree(state['directory'])
 bpy.ops.wm.quit_blender();return None

def check():
 try:
  if time.monotonic()-started>20:raise RuntimeError('Dialog/processing timeout')
  p=bpy.context.scene.polygroups_model_preparation_settings
  if p.phase2_final_is_running:state['running']=True
  if state.get('running') and not p.phase2_final_is_running:
   assert p.phase2_final_progress==100,p.phase2_status
   assert 'SM_Desert_Stones_10_01_MID' in bpy.data.objects
   return finish()
  return .03
 except Exception:return finish(traceback.format_exc())
def accept():
 bpy.context.window_manager.windows[0].event_simulate(type='RET',value='PRESS')
 bpy.context.window_manager.windows[0].event_simulate(type='RET',value='RELEASE')
 return None

def start():
 try:
  bpy.context.preferences.use_preferences_save=False;addon_utils.enable(ROOT.name,default_set=True)
  directory=Path(tempfile.mkdtemp(dir=ROOT,prefix='test_batch_dialog_'));state['directory']=directory
  bpy.ops.wm.save_as_mainfile(filepath=str(directory/'Working.blend'))
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  col=bpy.data.collections.new('Generated.001');bpy.context.scene.collection.children.link(col)
  bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8);source=bpy.context.object
  source.name='Retopo_12_Highpoly_Generated.001'
  for old in list(source.users_collection):old.objects.unlink(source)
  col.objects.link(source)
  s=bpy.context.scene.polygroups_mesh_finalization_settings
  s.smart_lods_count=2;s.smart_lods_target_1=80;s.smart_lods_target_2=40
  s.unreal_lod_asset_name='desert stones';s.unreal_lod_name_index='10';s.unreal_lod_version_index='01'
  s.unreal_lod_prepare_materials=False
  window=bpy.context.window_manager.windows[0];area=next(a for a in window.screen.areas if a.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
  with bpy.context.temp_override(window=window,area=area,region=region):
   assert bpy.ops.object.polygroups_batch_finalization('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
  bpy.app.timers.register(accept,first_interval=.5)
  bpy.app.timers.register(check,first_interval=.1)
 except Exception:return finish(traceback.format_exc())
 return None
bpy.app.timers.register(start,first_interval=.5)
