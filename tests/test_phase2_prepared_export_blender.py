"""Actual FAB/Unity GLB+GLTF+FBX batches and successful-only Generated cleanup."""
import sys,json,tempfile
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.phase2_export import prepared_meshes
from polygroups_generator.operators import unreal_lod_rename
ctx=bpy.context;s=ctx.scene.polygroups_mesh_finalization_settings;p=ctx.scene.polygroups_model_preparation_settings
assert p.phase2_export_sort=='LODS_FORMAT' and p.phase2_export_json
assert not p.phase2_final_cleanup_generated
def clear():
 for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
 for col in list(bpy.data.collections):bpy.data.collections.remove(col)
def cube(name,col):
 bpy.ops.mesh.primitive_cube_add(location=(3,4,5));obj=ctx.object;obj.name=name
 for old in list(obj.users_collection):old.objects.unlink(obj)
 col.objects.link(obj);return obj
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_phase2_export_') as directory:
 root=Path(directory);clear();meshes=[]
 for i in (1,2):
  base=f'Stones_01_{i:02d}';col=bpy.data.collections.new(base+'_Collection');ctx.scene.collection.children.link(col)
  for suffix in ('MID','LOD0','LOD1'):meshes.append(cube('SM_'+base+'_'+suffix,col))
  col.hide_viewport=True
 other=bpy.data.collections.new('Other');ctx.scene.collection.children.link(other)
 cube('Unrelated_MID',other)
 assert len(prepared_meshes(ctx))==6
 bpy.ops.wm.save_as_mainfile(filepath=str(root/'Pack.blend'))
 p.phase2_export_glb=p.phase2_export_gltf=p.phase2_export_fbx=True
 s.unreal_glb_mode=s.unreal_gltf_mode='COMBINED'
 originals={o:o.matrix_world.copy() for o in meshes}
 oldsort=s.mesh_export_sort
 assert bpy.ops.object.polygroups_phase2_export()=={'FINISHED'}
 out=root/'!Unreal';info=json.loads((out/'MeshInfo.json').read_text())
 assert info['Engine']=='Unreal' and info['totals']['meshes']==6
 for fmt in ('GLB','GLTF','FBX'):
  assert (out/fmt/'MeshInfo.json').exists()
  assert len(list((out/fmt).glob('*.'+fmt.lower())))==(6 if fmt=='FBX' else 4)
 assert s.mesh_export_sort==oldsort
 assert all(o.matrix_world==originals[o] for o in meshes)
 assert set(ctx.selected_objects)==set(meshes)
 # Unity-prepared base + .LODN names, using the same formats and shared layout.
 clear();meshes=[]
 for i in (1,2):
  base=f'Unity_01_{i:02d}';col=bpy.data.collections.new(base+'_LOD0_Collection');ctx.scene.collection.children.link(col)
  for suffix in ('','.LOD1'):
   obj=cube(base+suffix,col);obj['unity_prepared']=True;meshes.append(obj)
 p.phase2_export_engine='UNITY';s.unity_export_directory=str(root/'Unity')
 s.unity_export_autosave=True;s.unity_use_auto_rig_pro=False
 s.unity_export_overwrite=True;s.unity_export_clear_asset_folder=False
 oldflags=(s.unity_export_fbx,s.unity_export_gltf,s.unity_export_glb)
 assert bpy.ops.object.polygroups_phase2_export()=={'FINISHED'}
 info=json.loads((root/'Unity'/'MeshInfo.json').read_text())
 assert info['Engine']=='Unity' and info['totals']['meshes']==4
 for fmt in ('GLB','GLTF','FBX'):
  assert len(list((root/'Unity'/fmt).glob('*.'+fmt.lower())))==(4 if fmt=='FBX' else 2)
 assert (s.unity_export_fbx,s.unity_export_gltf,s.unity_export_glb)==oldflags
 assert s.unity_export_autosave
 # The regular section-12 Unity exporter also supports GLB-only output.
 s.unity_export_directory=str(root/'UnityNormal')
 s.unity_export_fbx=s.unity_export_gltf=False;s.unity_export_glb=True
 s.unity_export_all_renders=False
 assert bpy.ops.object.polygroups_export_unity('EXEC_DEFAULT')=={'FINISHED'}
 assert (root/'UnityNormal'/'Unity_01_01'/'GLB'/'Unity_01_01.glb').is_file()
 # Cleanup is gated on successful Rename; shared objects survive.
 def fixture():
  clear();col=bpy.data.collections.new('Generated.001');ctx.scene.collection.children.link(col)
  cube('Retopo_12_Highpoly_Generated.001',col)
  return col
 p.phase2_final_lods=False;p.phase2_final_rename=True;p.phase2_final_rename_engine='FAB'
 p.phase2_final_cleanup_generated=True;s.unreal_lod_prepare_materials=False
 col=fixture()
 shared=cube('Backup_Retopo_Shared',col)
 outside=bpy.data.collections.new('Shared');ctx.scene.collection.children.link(outside);outside.objects.link(shared)
 assert bpy.ops.object.polygroups_batch_finalization(asset='Export Test',name_index='01',version_index='01')=={'FINISHED'}
 assert 'Generated.001' not in bpy.data.collections and shared.name in bpy.data.objects
 assert 'SM_Export_Test_01_01_MID' in bpy.data.objects
 fixture();s.unreal_lod_prepare_materials=True
 try:
  with patch.object(unreal_lod_rename,'prepare_materials',side_effect=RuntimeError('Injected failure')):
   bpy.ops.object.polygroups_batch_finalization(asset='Fail Test',name_index='01',version_index='01')
 except RuntimeError:pass
 assert 'Generated.001' in bpy.data.collections
 from polygroups_generator.custom_ui.schema import capture
 assert not capture(ctx,1).errors
print('PHASE2_PREPARED_EXPORT_AND_GENERATED_CLEANUP_PASSED')
