"""Real Auto Render outputs, fixed 10%-margin camera, studio replacement, texture modes."""
import sys,tempfile
from math import cos, sin, radians
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.operators import auto_render as auto,render_queue as rq,render_studio as studio
from polygroups_generator.operators.render_textures import texture_planes
from polygroups_generator.operators import sequential_jobs as jobs
context=bpy.context;scene=context.scene;p=scene.polygroups_model_preparation_settings;s=scene.polygroups_render_settings
assert all((p.phase2_auto_scene,p.phase2_auto_camera,p.phase2_auto_selection,p.phase2_auto_freestyle,p.phase2_auto_freestyle_pass,p.phase2_auto_multiview,p.phase2_auto_mv_hero,p.phase2_auto_textures))
assert p.phase2_auto_mv_offset==1 and p.phase2_auto_mv_angle=='-30'
assert abs(p.phase2_auto_freestyle_color[0]-.80695226)<1e-6
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
old=bpy.data.collections.new('Scene');scene.collection.children.link(old)
data=bpy.data.meshes.new('OldBackdrop');data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
obj=bpy.data.objects.new('ForeignBackdrop',data);old.objects.link(obj)
bpy.ops.object.camera_add();bpy.context.object.name='ForeignCamera'
bpy.ops.object.light_add(type='POINT');bpy.context.object.name='ForeignLight'
mat=bpy.data.materials.new('AssetMaterial');mat.use_nodes=True
shader=mat.node_tree.nodes.get('Principled BSDF')
images=[]
for kind,color in (('BaseColor',(.2,.5,.8,1)),('Normal',(.5,.5,1,1))):
 image=bpy.data.images.new(kind,width=4,height=4);image.pixels[:]=list(color)*16;images.append(image)
 node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
 if kind=='BaseColor':mat.node_tree.links.new(node.outputs['Color'],shader.inputs['Base Color'])
 else:
  normal=mat.node_tree.nodes.new('ShaderNodeNormalMap');mat.node_tree.links.new(node.outputs['Color'],normal.inputs['Color']);mat.node_tree.links.new(normal.outputs['Normal'],shader.inputs['Normal'])
sources=[]
for index,origin,scale in ((1,(0,0,1),(1,1,1)),(2,(9,3,2),(2,.6,3))):
 col=bpy.data.collections.new(f'Desert_Stones_01_{index:02d}_Collection');scene.collection.children.link(col)
 for suffix,delta in (('MID',0),('LOD0',4)):
  bpy.ops.mesh.primitive_cube_add(location=(origin[0]+delta,origin[1],origin[2]))
  obj=bpy.context.object;obj.name=f'SM_Desert_Stones_01_{index:02d}_{suffix}';obj.scale=scale;obj.data.materials.append(mat)
  for previous in list(obj.users_collection):previous.objects.unlink(obj)
  col.objects.link(obj);sources.append(obj)
context.view_layer.update()
originals={obj:obj.matrix_world.copy() for obj in sources}
image_spaces=[image.colorspace_settings.name for image in images]
real_config=auto.configure_auto_render;real_render=auto.render_asset_job
frames={};projections={}
def small_render(ctx):
 real_config(ctx)
 assert (s.resolution_x,s.resolution_y)==(2048,1152) and s.render_engine=='EEVEE'
 assert s.render_mid and s.render_lod_enabled and s.render_lod_level=='LOD0' and not s.render_high
 s.resolution_scale=5

def inspect_render(ctx,job,views,origin):
 ctx.view_layer.update()
 for role,_label,position,_energy,_size in studio.LIGHT_DEFAULTS:
  light=getattr(s,'studio_'+role)
  actual=light.evaluated_get(ctx.evaluated_depsgraph_get()).matrix_world.translation
  assert (actual-origin-Vector(position)).length<1e-4,(role,tuple(actual),tuple(origin))
 for source,group in views.items():
  for obj,angle in zip(group,(-30,150,60)):
   direction=obj.matrix_world.to_quaternion() @ Vector((1,0,0))
   expected=Vector((cos(radians(angle)),sin(radians(angle)),0))
   assert (direction-expected).length<1e-4,(obj.name,tuple(direction),tuple(expected))
 camera=scene.camera;matrix=camera.matrix_world.copy()
 key=job['collection']
 if key in frames:assert max(abs(matrix[i][j]-frames[key][i][j]) for i in range(4) for j in range(4))<1e-5
 else:
  frames[key]=matrix
  objects=[obj for group in views.values() for obj in group]+texture_planes(bpy.data.collections[key])
  pts,_,_=auto.selected_bounds(ctx,objects)
  projected=[world_to_camera_view(scene,camera,point) for point in pts]
  assert all(.0999<=v.x<=.9001 and .0999<=v.y<=.9001 and v.z>0 for v in projected),[(tuple(v)) for v in projected]
  projections[key]=True
 assert (s.studio_camera_position.matrix_world.translation-origin).length<1e-5
 real_render(ctx,job,views,origin)

with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_auto_render_') as directory:
 root=Path(directory);bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
 s.output_directory=str(root/'ALL');s.max_samples=1;s.skip_existing=False;s.overwrite_existing=True
 with patch.object(auto,'configure_auto_render',small_render),patch.object(auto,'render_asset_job',inspect_render):
  assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
 assert 'ForeignCamera' not in bpy.data.objects and 'ForeignLight' not in bpy.data.objects and 'ForeignBackdrop' not in bpy.data.objects
 assert len(frames)==2 and all(projections.values())
 assert s.queue_index==s.total_count==10,(s.queue_index,s.total_count)
 files=list((root/'ALL').rglob('*.png'));assert len(files)==26,len(files)
 assert len([path for path in files if 'BaseColor_Normal' in path.name])==2
 assert not any(obj.get(rq.MULTIVIEW_PROP) and not obj.get(rq.MULTIVIEW_PREPARED_PROP) for obj in bpy.data.objects)
 assert not s.is_running and not p.phase2_auto_render_running
 assert [image.colorspace_settings.name for image in images]==image_spaces
 for obj in sources:assert obj.matrix_world==originals[obj]
 cameras=len(bpy.data.cameras);lights=len(bpy.data.lights)
 # Per-asset preparation uses the same studio and paired texture output.
 for prop,kind in auto.MANAGED_STUDIO.values():setattr(s,prop,None)
 p.phase2_auto_texture_prepare='EACH';p.phase2_auto_freestyle=False
 s.output_directory=str(root/'EACH');frames.clear();projections.clear()
 with patch.object(auto,'configure_auto_render',small_render),patch.object(auto,'render_asset_job',inspect_render):
  assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
 assert len(bpy.data.cameras)==cameras and len(bpy.data.lights)==lights
 assert len(list((root/'EACH').rglob('*.png')))==10
 # Unscaled production 2K render, with the optional groups switched off.
 for obj in sources[1:]:bpy.data.objects.remove(obj,do_unlink=True)
 p.phase2_auto_multiview=False;p.phase2_auto_textures=False;p.phase2_auto_freestyle=False
 s.output_directory=str(root/'2K')
 assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
 files=list((root/'2K').rglob('*.png'));assert len(files)==1,files
 image=bpy.data.images.load(str(files[0]));assert tuple(image.size)==(2048,1152);bpy.data.images.remove(image)
 # A render error must close the job and remove temporary views.
 p.phase2_auto_multiview=True
 s.output_directory=str(root/'Failed')
 def fail_render(*args):raise RuntimeError('Injected render failure')
 try:
  with patch.object(auto,'configure_auto_render',small_render),patch.object(auto,'render_asset_job',fail_render):
   bpy.ops.object.polygroups_phase2_auto_render()
 except RuntimeError as error:assert 'Injected render failure' in str(error)
 else:raise AssertionError('Expected the injected render failure')
 assert jobs.ACTIVE_JOB is None and not s.is_running and not p.phase2_auto_render_running
 assert p.phase2_status.startswith('Failed'),p.phase2_status
 assert not any(obj.get(rq.MULTIVIEW_PROP) for obj in bpy.data.objects)
 from polygroups_generator.custom_ui.schema import capture
 model=capture(context,1);assert not model.errors,model.errors
print('PHASE2_AUTO_RENDER_PASSED')
