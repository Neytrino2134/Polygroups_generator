"""Convert all local image paths without changing file destinations or pixels."""
import sys,tempfile
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
assert bpy.ops.wm.airetopo_make_texture_paths_relative()=={'CANCELLED'}
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_relative_images_') as folder:
 root=Path(folder);bpy.ops.wm.save_as_mainfile(filepath=str(root/'Project.blend'))
 images=[]
 for name in ('Existing','Missing','Packed','AlreadyRelative'):
  image=bpy.data.images.new(name,width=2,height=2);image.use_fake_user=True
  image.pixels[:]=[.2,.4,.6,1]*4
  image.filepath_raw=str(root/(name+'.png'));image.file_format='PNG'
  if name!='Missing':image.save()
  if name=='Packed':image.pack()
  if name=='AlreadyRelative':image.filepath=bpy.path.relpath(image.filepath)
  images.append(image)
 expected={image.name:bpy.path.abspath(image.filepath) for image in images}
 assert bpy.ops.wm.airetopo_make_texture_paths_relative()=={'FINISHED'}
 for image in images:
  assert image.filepath.startswith('//')
  assert bpy.path.abspath(image.filepath)==expected[image.name]
 assert images[2].packed_file
 assert not (root/'Missing.png').exists()
 status=bpy.context.window_manager.airetopo_save_cleanup.relative_status
 assert 'Relative: 3' in status and 'Already relative: 1' in status and 'Errors: 0' in status,status
 bpy.ops.wm.save_as_mainfile(filepath=str(root/'Project.blend'))
 bpy.ops.wm.open_mainfile(filepath=str(root/'Project.blend'))
 assert all(bpy.data.images[name].filepath.startswith('//') for name in expected)
 from polygroups_generator.custom_ui.schema import Layout,capture
 from polygroups_generator.save_cleanup import draw_cleanup
 layout=Layout(key='cleanup');draw_cleanup(layout,bpy.context)
 p=bpy.context.scene.polygroups_model_preparation_settings
 p.phase2_show_restore=True;p.phase2_show_manual_cleanup=True
 for model in (layout,capture(bpy.context,1)):
  assert not model.errors,model.errors
  assert any(v[0]=='operator' and v[1]=='wm.airetopo_make_texture_paths_relative' for v in model.bindings.values())
print('ALL_TEXTURE_PATHS_RELATIVE_AND_BOTH_UI_PASSED')
