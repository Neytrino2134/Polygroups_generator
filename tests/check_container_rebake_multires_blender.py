"""Real Container/Multires Cycles ReBake; redirect all outputs to a disposable folder.
Open the original Containers_01_01.blend before running. No input files are saved.
"""
import sys,tempfile,hashlib,shutil
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import rebake_final,baking
c=bpy.context;s=c.scene.polygroups_baking_settings
c.scene.render.engine='CYCLES';c.scene.cycles.device='CPU';c.scene.cycles.samples=1
s.bake_base_color=s.bake_normal=s.bake_artifact_mask=True
s.bake_artifact_autofill=s.bake_artifact_geometry=s.bake_artifact_self_intersections=False
s.bake_artifact_match_normal=True;s.bake_artifact_radius=0
s.use_auto_cage=s.autogenerate_smart_cage=False;s.cage_extrusion=.02;s.ray_distance=.1
s.auto_pack_uv_before_bake=False
obj=bpy.data.objects['SM_Containers_01_01_MID']
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);c.view_layer.objects.active=obj
outputs,resolution=rebake_final.final_texture_outputs(obj,s)
hashes={path:hashlib.sha256(path.read_bytes()).hexdigest() for image,path in outputs.values() if path.is_file()}
original_outputs=rebake_final.final_texture_outputs
launch=baking.OBJECT_OT_polygroups_bake_task._launch_pass
passes=[]
# Test outputs live on C: while the original blend lives on D:. Blender cannot
# make those paths relative; keep only these disposable test paths absolute.
relative_path=bpy.path.relpath
def temporary_relative_path(path,*args,**kwargs):
 try:return relative_path(path,*args,**kwargs)
 except ValueError:
  if Path(path).is_relative_to(folder):return str(path)
  raise
with tempfile.TemporaryDirectory(prefix='rebake-container-',dir=ROOT/'user_data'/'repair_diagnostics') as directory:
 folder=Path(directory)
 def redirected(target,settings):
  values,_size=original_outputs(target,settings);result={}
  for channel,(image,path) in values.items():
   destination=folder/path.name
   if path.is_file():shutil.copy2(path,destination)
   result[channel]=(image,destination)
  return result,32
 def checked_launch(task,context,node,kind):
  assert task.final_rebake_session.frozen_source is not None
  source=task.sources[0]
  assert all(not m.show_render and not m.show_viewport for m in source.modifiers)
  passes.append(kind);print('CONTAINER_BAKE_PASS',kind,source.name,len(source.data.vertices),flush=True)
  return launch(task,context,node,kind)
 with patch.object(rebake_final,'final_texture_outputs',redirected),patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',checked_launch),patch.object(bpy.path,'relpath',temporary_relative_path):
  assert bpy.ops.object.polygroups_rebake_final_mesh(repair_mesh=False)=={'FINISHED'},s.bake_task_message
 assert passes==['DIFFUSE','NORMAL'] and s.bake_task_stage=='DONE',s.bake_task_message
 assert any(folder.glob('*_ArtifactMask.png'))
 assert not any('FrozenHighpoly' in mesh.name for mesh in bpy.data.meshes)
for path,value in hashes.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==value,'Original texture modified: '+str(path)
print('REAL_CONTAINER_MULTires_REBAKE_AND_DIAGNOSTICS_OK_ORIGINAL_FILES_UNCHANGED',flush=True)
