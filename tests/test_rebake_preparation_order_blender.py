"""Real ReBake order: repair -> pack -> frozen Multires -> Cycles/diagnostics."""
import sys,tempfile
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import rebake_final,baking
from polygroups_generator.operators.repair_mesh_folds import MESH_OT_polygroups_repair_mesh_folds as Repair
from polygroups_generator.operators.uvpackmaster_controls import OBJECT_OT_polygroups_uvpackmaster_pack as Pack
from polygroups_generator.core.bake_projection import ProjectionSession,invalidate
c=bpy.context;scene=c.scene;s=scene.polygroups_baking_settings;p=scene.polygroups_model_preparation_settings
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
s.bake_base_color=s.bake_normal=s.bake_artifact_mask=True;s.bake_artifact_autofill=False
s.bake_artifact_geometry=s.bake_artifact_self_intersections=False;s.bake_artifact_radius=0;s.bake_margin=0
s.use_auto_cage=s.autogenerate_smart_cage=False;s.cage_extrusion=.2;s.ray_distance=1
s.auto_pack_uv_before_bake=True;p.phase2_rebake_repack_uv=True
bpy.ops.mesh.primitive_plane_add(size=2);target=c.object;target.name='SM_Preparation_01_01_MID'
material=bpy.data.materials.new('Final material');material.use_nodes=True;target.data.materials.append(material)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=6,y_subdivisions=6,size=3,location=(0,0,.1))
high=c.object;high.name='Resculpting_01_Highpoly_Generated.001'
source_material=bpy.data.materials.new('Source material');source_material.use_nodes=True
source_material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.1,.8,.2,1)
high.data.materials.append(source_material)
mod=high.modifiers.new('Multires source','MULTIRES');bpy.ops.object.multires_subdivide(modifier=mod.name,mode='SIMPLE')
mod.levels=0;mod.render_levels=1;mod.show_render=mod.show_viewport=False
original_data=high.data;original_uv=tuple(tuple(l.uv) for l in high.data.uv_layers.active.data)
flags=(mod.show_viewport,mod.show_render,mod.levels,mod.render_levels)
events=[];packed=[]

def repair(operator,context):
 events.append('repair');target.data.uv_layers.active.data[0].uv.x+=.01;target.data.update();return {'FINISHED'}
def pack(operator,context):
 events.append('pack')
 for l in target.data.uv_layers.active.data:l.uv=(l.uv.x*.9+.04,l.uv.y*.9+.04)
 target.data.update();packed[:]=[tuple(l.uv) for l in target.data.uv_layers.active.data];return {'FINISHED'}
freeze=rebake_final.FinalRebakeSession.freeze_source_geometry
launch=baking.OBJECT_OT_polygroups_bake_task._launch_pass

def frozen(session):
 events.append('freeze');assert events[:2]==['repair','pack'];return freeze(session)
def checked_launch(task,context,node,kind):
 events.append(kind)
 assert task.final_rebake_session.target_prepared
 assert high.data!=original_data and len(high.data.vertices)>len(original_data.vertices)
 assert not mod.show_viewport and not mod.show_render
 assert [tuple(l.uv) for l in target.data.uv_layers.active.data]==packed
 assert not s.auto_pack_uv_before_bake
 return launch(task,context,node,kind)

with tempfile.TemporaryDirectory() as directory:
 folder=Path(directory)
 for channel,color in (('BaseColor',(1,0,0,1)),('Normal',(.5,.5,1,1))):
  image=bpy.data.images.new('T_Preparation_01_01_'+channel,width=32,height=32)
  image.generated_color=color;image.filepath_raw=str(folder/(image.name+'.png'));image.file_format='PNG'
  if channel=='Normal':image.colorspace_settings.name='Non-Color'
  image.save();node=material.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
 bpy.ops.object.select_all(action='DESELECT');target.select_set(True);c.view_layer.objects.active=target
 with patch.object(Repair,'execute',repair),patch.object(Pack,'execute',pack),\
      patch.object(rebake_final.FinalRebakeSession,'freeze_source_geometry',frozen),\
      patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',checked_launch):
  assert bpy.ops.object.polygroups_rebake_final_mesh(repair_mesh=True)=={'FINISHED'},s.bake_task_message
 assert events==['repair','pack','freeze','DIFFUSE','NORMAL'],events
 assert high.data==original_data and (mod.show_viewport,mod.show_render,mod.levels,mod.render_levels)==flags
 assert tuple(tuple(l.uv) for l in original_data.uv_layers.active.data)==original_uv
 assert not any(mesh.name.startswith('ReBake_') and 'FrozenHighpoly' in mesh.name for mesh in bpy.data.meshes)
 assert s.auto_pack_uv_before_bake
 print('REBAKE_REPAIR_PACK_FREEZE_REAL_CYCLES_OK',flush=True)
 # A pending failed pack is honored even when Repair Mesh is disabled for retry.
 target['polygroups_rebake_uv_needs_pack']=True
 session=rebake_final.FinalRebakeSession(c,target,s,repair_mesh=False)
 with patch.object(Repair,'execute') as no_repair,patch.object(Pack,'execute',lambda *_:{'CANCELLED'}):
  try:session.repair_target()
  except RuntimeError as error:assert 'UV repack' in str(error)
  else:raise AssertionError('Failed pack must stop preparation')
  assert not no_repair.called and target.get('polygroups_rebake_uv_needs_pack')
 with patch.object(Repair,'execute') as no_repair,patch.object(Pack,'execute',pack):
  session.repair_target();assert not no_repair.called
 assert session.target_prepared and not target.get('polygroups_rebake_uv_needs_pack')
 session.close(False)
 # Geometry/UV edits still fail with object/component details; closing restores data.
 session=rebake_final.FinalRebakeSession(c,target,s);session.begin()
 normal=bpy.data.images.new('Guard normal',width=16,height=16)
 invalidate(target);baking._configure_bake_settings(c,s,'NORMAL')
 projection=ProjectionSession(c,target,[high],s,normal,read_normal=False)
 high.data.uv_layers.active.data[0].uv.x+=.01;high.data.update();c.view_layer.update()
 try:projection.validate()
 except ValueError as error:assert high.name in str(error) and 'UV' in str(error),str(error)
 else:raise AssertionError('A real UV edit must not be accepted')
 projection.close();session.close(False)
 assert high.data==original_data and (mod.show_viewport,mod.show_render,mod.levels,mod.render_levels)==flags
 assert tuple(tuple(l.uv) for l in high.data.uv_layers.active.data)==original_uv
 print('REBAKE_PENDING_PACK_RETRY_AND_STRICT_UV_GUARD_OK',flush=True)
