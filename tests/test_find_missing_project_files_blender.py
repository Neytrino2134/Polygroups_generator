"""Native recursive find, relative relink, unresolved count and both UI entries."""
import sys,tempfile
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
s=bpy.context.window_manager.airetopo_save_cleanup
assert bpy.ops.wm.airetopo_find_missing_project_files()=={'CANCELLED'}
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_find_missing_') as folder:
 root=Path(folder);textures=root/'Textures'/'Nested';textures.mkdir(parents=True)
 bpy.ops.wm.save_as_mainfile(filepath=str(root/'Project.blend'))
 image=bpy.data.images.new('Recover Me',width=4,height=4);image.pixels[:]=[.1,.4,.6,1]*16
 real=textures/'Recovered.png';image.filepath_raw=str(real);image.file_format='PNG';image.save();image.source='FILE'
 image.use_fake_user=True
 image.filepath='C:/OldComputer/Textures/Recovered.png'
 missing=bpy.data.images.new('Unresolved',width=1,height=1);missing.source='FILE';missing.filepath='//Absent.png'
 valid=bpy.data.images.load(str(real),check_existing=False);old=valid.filepath
 assert bpy.ops.wm.airetopo_find_missing_project_files()=={'FINISHED'}
 assert image.filepath.startswith('//'),image.filepath
 assert Path(bpy.path.abspath(image.filepath))==real
 assert tuple(image.size)==(4,4) and image.has_data
 assert valid.filepath==old
 assert s.missing_status=='Relinked 1 | Missing 1 | Errors 0',s.missing_status
 bpy.ops.wm.save_as_mainfile(filepath=str(root/'Project.blend'))
 bpy.ops.wm.open_mainfile(filepath=str(root/'Project.blend'))
 assert bpy.data.images['Recover Me'].filepath.startswith('//')
 # Shared draw helper is present in each destination.
 from polygroups_generator.custom_ui.schema import Layout,capture
 from polygroups_generator.save_cleanup import draw_cleanup
 model=Layout(key='cleanup');draw_cleanup(model,bpy.context)
 assert not model.errors,model.errors
 assert any(v[0]=='operator' and v[1]=='wm.airetopo_find_missing_project_files' for v in model.bindings.values())
 p=bpy.context.scene.polygroups_model_preparation_settings
 p.phase2_show_restore=True;p.phase2_show_manual_cleanup=True
 model=capture(bpy.context,1);assert not model.errors,model.errors
 assert any(v[0]=='operator' and v[1]=='wm.airetopo_find_missing_project_files' for v in model.bindings.values())
print('FIND_MISSING_PROJECT_FILES_RECURSIVE_RELATIVE_AND_UI_PASSED')

