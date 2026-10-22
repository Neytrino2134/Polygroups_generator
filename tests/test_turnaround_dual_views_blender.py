"""Real PNG renders: four clean views plus four Freestyle views."""
import sys, tempfile
from pathlib import Path
import bpy, addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_cube_add()
assert bpy.ops.object.polygroups_prepare_turnaround_animation()=={'FINISHED'}
s=bpy.context.scene.polygroups_render_settings
bpy.ops.object.camera_add(location=(3,-6,3))
camera=bpy.context.object;camera.rotation_euler=(-camera.location).to_track_quat('-Z','Y').to_euler();bpy.context.scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=(1,-3,4));bpy.context.object.data.energy=500
s.resolution_x=s.resolution_y=64;s.resolution_scale=100;s.max_samples=1;s.render_engine='CYCLES'
s.animation_views_image_format='PNG';s.freestyle_edges=True;s.freestyle_as_render_pass=True
assert s.animation_views_freestyle_dual is False
s.animation_views_freestyle_dual=True
scene=bpy.context.scene
before=(scene.render.use_freestyle,bpy.context.view_layer.freestyle_settings.as_render_pass)
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_dual_views_') as folder:
 s.output_directory=folder
 assert bpy.ops.object.polygroups_render_turnaround_views()=={'FINISHED'}
 files=list(Path(folder).rglob('*.png'));assert len(files)==8,files
 for angle in (0,90,180,270):
  pair=[]
  for suffix in ('Clean','Freestyle'):
   path=next(p for p in files if p.name.endswith(f'_{angle:03d}_{suffix}.png'))
   image=bpy.data.images.load(str(path));pair.append(tuple(image.pixels[:]));bpy.data.images.remove(image)
  assert pair[0] and pair[0]!=pair[1],angle
 assert before==(scene.render.use_freestyle,bpy.context.view_layer.freestyle_settings.as_render_pass)
 assert s.animation_collection_name and not s.is_running
 s.animation_views_freestyle_dual=False
 assert bpy.ops.object.polygroups_render_turnaround_views()=={'FINISHED'}
 assert len(list(Path(folder).rglob('*.png')))==12
print('DUAL_FREESTYLE_FOUR_VIEWS_OK')
