"""Regression: fitted camera must retain Area-light illumination in Eevee."""
import sys, tempfile
from pathlib import Path
from unittest.mock import patch
import bpy, addon_utils
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import auto_render as auto, render_queue as rq, render_studio as studio
ctx=bpy.context; scene=ctx.scene
p=scene.polygroups_model_preparation_settings;s=scene.polygroups_render_settings
for obj in list(bpy.data.objects): bpy.data.objects.remove(obj,do_unlink=True)
col=bpy.data.collections.new('Stone_01_01_Collection');scene.collection.children.link(col)
bpy.ops.mesh.primitive_cube_add(location=(7,3,1))
source=ctx.object;source.name='SM_Stone_01_01_MID';source.scale=(.6,.35,1)
for old in list(source.users_collection):old.objects.unlink(source)
col.objects.link(source)
studio.reset_studio(ctx,'ALL')
scene.world.use_nodes=True
scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=0
p.phase2_auto_scene=False;p.phase2_auto_camera=True
p.phase2_auto_textures=False;p.phase2_auto_freestyle=False;p.phase2_auto_transparent=False
s.skip_existing=False;s.max_samples=8
config=auto.configure_auto_render;render=rq._render_current_job
seen=[];frames=[];records=[]
def small(context):config(context);s.resolution_scale=10
def state():
 return {o.name: (tuple(v for row in o.matrix_world for v in row),o.hide_render)
         for o in scene.objects if o.type in {'LIGHT','CAMERA'} or o.get(rq.MULTIVIEW_PROP)}
def pixels(path):
 image=bpy.data.images.load(str(path),check_existing=False)
 values=list(image.pixels[:]);bpy.data.images.remove(image);return values
def inspect(context,settings,job):
 before=state();camera=scene.camera.matrix_world.copy();frames.append(camera)
 assert scene.camera.data.clip_end/scene.camera.data.clip_start<10000
 assert all(o.type!='LIGHT' or o.data.type=='AREA' for o in scene.objects)
 visible=[o for o in scene.objects if o.get(rq.MULTIVIEW_PROP) and not o.hide_render]
 assert len(visible)==(1 if job['view_mode']=='Hero' else 3)
 assert settings.multiview_offset==1 and settings.multiview_angle=='-30'
 render(context,settings,job)
 records.append((dict(job),before,camera))
 if job['view_mode']=='Hero':
  lights=[o for o in scene.objects if o.type=='LIGHT'];energies=[o.data.energy for o in lights]
  try:
   for o in lights:o.data.energy=0
   dark={**job,'output_path':str(Path(job['output_path']).with_name('lights_off.png'))}
   render(context,settings,dark)
  finally:
   for o,energy in zip(lights,energies):o.data.energy=energy
  lit=pixels(job['output_path']);unlit=pixels(dark['output_path'])
  difference=sum(abs(a-b) for a,b in zip(lit,unlit))/len(lit)
  print('LIGHT_IMAGE_DIFFERENCE',difference,max(lit[::4]),max(unlit[::4]))
  assert difference>.01,'Studio Area lights contribute no meaningful image energy'
 seen.append(job['view_mode'])
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_shared_queue_') as folder:
 bpy.ops.wm.save_as_mainfile(filepath=str(Path(folder)/'Working.blend'))
 s.output_directory=str(Path(folder)/'Renders')
 with patch.object(auto,'configure_auto_render',small),patch.object(rq,'_render_current_job',inspect):
  assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
 for job,before,camera in records:
  manual={**job,'output_path':str(Path(job['output_path']).with_name('manual_'+Path(job['output_path']).name))}
  with rq.prepared_queue_job(ctx,s,manual):
   scene.camera.matrix_world=camera
   ctx.view_layer.update()
   assert state()==before,(state(),before)
   render(ctx,s,manual)
  assert pixels(job['output_path'])==pixels(manual['output_path'])
 assert seen==['Multiview','Hero'],seen
 assert frames[0]==frames[1],'Camera moved between Multiview and Hero'
 assert not any(o.get(rq.MULTIVIEW_PROP) for o in scene.objects)
 assert not s.is_running
print('AREA_LIGHT_CAMERA_CLIPPING_REGRESSION_PASSED')
