"""Phase 2 file manager: recursive move, collisions, exclusions, Save Cleanup."""
import sys,tempfile
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
s=bpy.context.scene.polygroups_model_preparation_settings
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_phase2_files_') as folder:
 root=Path(folder)
 bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
 (root/'sub').mkdir();(root/'!Blend').mkdir()
 (root/'A.blend').write_bytes(b'a');(root/'sub'/'A.blend').write_bytes(b'b')
 (root/'Conflict.blend').write_bytes(b'original')
 (root/'!Blend'/'Conflict.blend').write_bytes(b'existing')
 (root/'A.blend1').write_bytes(b'backup')
 (root/'sub'/'A.blendAutosave23').write_bytes(b'backup')
 (root/'notes.txt').write_bytes(b'safe')
 assert bpy.ops.object.polygroups_phase2_files_scan()=={'FINISHED'}
 assert s.phase2_files_found==3,s.phase2_files_status
 s.phase2_files_cleanup=True
 assert bpy.ops.object.polygroups_phase2_files_move()=={'FINISHED'}
 assert s.phase2_files_status=='2 files moved / 1 errors',s.phase2_files_status
 assert (root/'Working.blend').is_file()
 assert (root/'!Blend'/'A.blend').read_bytes()==b'a'
 assert (root/'!Blend'/'sub'/'A.blend').read_bytes()==b'b'
 assert (root/'Conflict.blend').read_bytes()==b'original'
 assert (root/'!Blend'/'Conflict.blend').read_bytes()==b'existing'
 assert not (root/'A.blend1').exists()
 assert not (root/'sub'/'A.blendAutosave23').exists()
 assert (root/'notes.txt').exists()
 assert s.phase2_scan_subfolders
 assert bpy.ops.object.polygroups_phase2_files_scan()=={'FINISHED'}
 assert s.phase2_files_found==1
 # Changed-after-scan sources remain in place.
 (root/'Conflict.blend').write_bytes(b'changed')
 s.phase2_files_cleanup=False
 assert bpy.ops.object.polygroups_phase2_files_move()=={'FINISHED'}
 assert s.phase2_files_status=='0 files moved / 1 errors'
 from polygroups_generator.custom_ui.schema import capture,walk
 for opened in (False,True):
  s.phase2_show_files=s.phase2_show_restore=s.phase2_show_status=opened
  model=capture(bpy.context,1)
  assert not model.errors,model.errors
print('PHASE2_BLEND_FILE_MANAGER_PASSED')
