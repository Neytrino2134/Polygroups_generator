"""Actual UI Auto Render progress and cancellation after an image boundary."""
import sys,tempfile,time,traceback,shutil
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
state={};started=time.monotonic()
def finish(error=''):
 print('AUTO_RENDER_MODAL_FAILED '+error if error else 'AUTO_RENDER_MODAL_STOP_PASSED',flush=True)
 if state.get('directory'):shutil.rmtree(state['directory'])
 bpy.ops.wm.quit_blender();return None

def check():
 try:
  if time.monotonic()-started>30:raise RuntimeError('Timeout')
  p=bpy.context.scene.polygroups_model_preparation_settings;s=bpy.context.scene.polygroups_render_settings
  if p.phase2_auto_render_running and 3<p.phase2_final_progress<100 and not state.get('stop'):
   assert s.is_running
   from polygroups_generator.operators import sequential_jobs as jobs,render_queue as rq
   preview=jobs.ACTIVE_JOB._preview
   assert preview.handle is not None and preview.completed==s.queue_index==1
   assert preview.total==s.total_count==4
   assert preview.views and all(space.region_3d.view_perspective=='CAMERA' and space.camera==bpy.context.scene.camera
                               for area,space,*_ in preview.views)
   visible=[o for o in bpy.context.scene.objects if o.get(rq.MULTIVIEW_PROP) and not o.hide_render]
   assert len(visible)==3 and all(o.visible_get() for o in visible)
   state['preview']=preview
   screenshot=ROOT/'user_data/render_diagnostics/auto_render_progress.png'
   screenshot.parent.mkdir(parents=True,exist_ok=True)
   bpy.ops.screen.screenshot(filepath=str(screenshot))
   bpy.ops.object.polygroups_stop_lod_job();state['stop']=True
  if not p.phase2_auto_render_running:
   from polygroups_generator.operators import sequential_jobs as jobs,render_queue as rq
   assert state.get('stop') and p.phase2_status.startswith('Stopped'),p.phase2_status
   assert not s.is_running and jobs.ACTIVE_JOB is None
   assert state['preview'].handle is None and not state['preview'].views
   assert not any(o.get(rq.MULTIVIEW_PROP) for o in bpy.data.objects)
   assert len(list(state['directory'].rglob('*.png')))>=1
   return finish()
  return .02
 except Exception:return finish(traceback.format_exc())

def start():
 try:
  bpy.context.preferences.use_preferences_save=False;addon_utils.enable(ROOT.name,default_set=True)
  directory=Path(tempfile.mkdtemp(dir=ROOT,prefix='test_auto_modal_'));state['directory']=directory
  bpy.ops.wm.save_as_mainfile(filepath=str(directory/'Working.blend'))
  col=bpy.data.collections.new('Desert_Stones_01_01_Collection');bpy.context.scene.collection.children.link(col)
  for suffix in ('MID','LOD0'):
   bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object;obj.name='SM_Desert_Stones_01_01_'+suffix
   for old in list(obj.users_collection):old.objects.unlink(obj)
   col.objects.link(obj)
  p=bpy.context.scene.polygroups_model_preparation_settings;s=bpy.context.scene.polygroups_render_settings
  p.phase2_auto_freestyle=False;p.phase2_auto_textures=False
  s.max_samples=1;s.output_directory=str(directory/'Renders');s.skip_existing=False
  from polygroups_generator.operators import auto_render as auto
  real_config=auto.configure_auto_render
  def config(context):real_config(context);s.resolution_scale=5
  auto.configure_auto_render=config
  w=bpy.context.window_manager.windows[0];a=next(a for a in w.screen.areas if a.type=='VIEW_3D');r=next(r for r in a.regions if r.type=='WINDOW')
  with bpy.context.temp_override(window=w,area=a,region=r):
   assert bpy.ops.object.polygroups_phase2_auto_render()=={'RUNNING_MODAL'}
  bpy.app.timers.register(check,first_interval=.02)
 except Exception:return finish(traceback.format_exc())
 return None
bpy.app.timers.register(start,first_interval=.5)
