"""Move a saved project, remove its source directory and reload all prepared textures."""
import sys,tempfile,shutil
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import unity_preparation as unity,unreal_lod_rename as unreal
from polygroups_generator.operators.bake_images import _save_image_as_png
from polygroups_generator.operators.fab_preparation import _copy_and_rename_material_textures
ctx=bpy.context
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_portable_textures_') as folder:
 original=Path(folder)/'Original';original.mkdir()
 moved=Path(folder)/'Moved'
 bpy.ops.wm.save_as_mainfile(filepath=str(original/'Asset.blend'))
 for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
 expected={}
 for pipeline in ('AutoBake','Unity','Unreal','FAB'):
  bpy.ops.mesh.primitive_cube_add();obj=ctx.object;obj.name=pipeline
  mat=bpy.data.materials.new(pipeline);mat.use_nodes=True;obj.data.materials.append(mat)
  image=bpy.data.images.new(pipeline+'_BaseColor',width=4,height=4)
  image.pixels[:]=[.2,.4,.6,1]*16
  node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
  mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
  if pipeline=='AutoBake':
   output=original/'Bakes';output.mkdir();_save_image_as_png(image,str(output/'Normal.png'))
  elif pipeline=='Unity':unity.save_textures(obj,str(original/'Textures'/'Unity'))
  elif pipeline=='Unreal':unreal.prepare_materials([obj],'Unreal',True)
  else:
   _save_image_as_png(image,str(original/'Source.png'))
   s=ctx.scene.polygroups_mesh_finalization_settings;s.fab_copy_textures=True
   _copy_and_rename_material_textures(mat,s,'FAB','01','MID')
  image=next(n.image for n in obj.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE' and n.image)
  assert image.filepath.startswith('//'),(pipeline,image.filepath)
  assert Path(bpy.path.abspath(image.filepath)).is_file(),(pipeline,image.filepath)
  expected[image.name]=image.filepath
 bpy.ops.wm.save_as_mainfile(filepath=str(original/'Asset.blend'))
 shutil.move(str(original),str(moved))
 assert not original.exists()
 bpy.ops.wm.open_mainfile(filepath=str(moved/'Asset.blend'))
 for name,path in expected.items():
  image=bpy.data.images[name]
  assert image.filepath==path
  assert Path(bpy.path.abspath(path)).is_file(),(name,path)
  image.reload()
  assert tuple(image.size)==(4,4) and image.has_data,(name,image.size[:])
  assert max(image.pixels[:])>.5,name
print('AUTObAKE_UNITY_UNREAL_FAB_MOVED_TEXTURES_PASSED')
