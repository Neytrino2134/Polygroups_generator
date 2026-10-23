"""Integration test: exact backup matching, recursive scan and scanned-only cleanup."""
import sys,tempfile
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
s=bpy.context.window_manager.airetopo_save_cleanup
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_save_cleanup_') as directory:
 root=Path(directory);(root/'sub').mkdir()
 backups=['A.blend1','A.blend22','A.blendAutosave1','A.blendAutosave123','sub/B.blend9']
 safe=['A.blend','A.blendAutosave','A.blend0','A.blend1.txt','A.blendAutosave2.txt','notes.txt']
 for name in backups+safe:(root/name).write_bytes(b'12345')
 s.directory=str(root)
 assert bpy.ops.wm.airetopo_scan_save_cleanup()=={'FINISHED'}
 assert s.file_count==5 and s.total_bytes==25
 bpy.ops.wm.save_as_mainfile(filepath=str(root/'Current.blend'))
 s.directory=str(root/'sub')
 assert s.file_count==0
 assert bpy.ops.wm.airetopo_scan_current_save_folder()=={'FINISHED'}
 assert Path(s.directory)==root
 assert s.file_count==5 and s.total_bytes==25
 (root/'new.blend3').write_bytes(b'new')
 (root/'A.blend22').write_bytes(b'changed')
 assert bpy.ops.wm.airetopo_clean_backup_saves()=={'FINISHED'}
 assert all((root/name).exists() for name in safe)
 assert (root/'new.blend3').exists() and (root/'A.blend22').exists()
 assert not (root/'A.blend1').exists() and not (root/'sub/B.blend9').exists()
 assert 'skipped: 1' in s.status,s.status
 assert bpy.ops.wm.airetopo_scan_save_cleanup()=={'FINISHED'}
 assert s.file_count==2
 assert bpy.ops.wm.airetopo_clean_backup_saves()=={'FINISHED'}
 assert all((root/name).exists() for name in safe)
 assert bpy.ops.wm.airetopo_scan_save_cleanup()=={'FINISHED'} and s.file_count==0
from types import SimpleNamespace
from polygroups_generator import ui
from polygroups_generator.custom_ui.schema import Layout
prefs=bpy.context.preferences.addons[ROOT.name].preferences
prefs.show_panel_session_status=True
prefs.show_panel_save_cleanup=True
window=bpy.context.window_manager.windows[0]
area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')
with bpy.context.temp_override(window=window,area=area,region=region):
 model=Layout(key='save-cleanup')
 ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=model),bpy.context)
 assert not model.errors,model.errors
 ops={b[1] for b in model.bindings.values() if b[0]=='operator'}
 assert {'wm.airetopo_scan_save_cleanup','wm.airetopo_scan_current_save_folder','wm.airetopo_clean_backup_saves'} <= ops,ops
addon_utils.disable(ROOT.name,default_set=False)
print('SAVE_CLEANUP_TEST_PASSED')
