"""Select Current Folder sets the batch import folder to the saved blend's folder."""
import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)

p = bpy.context.scene.polygroups_model_preparation_settings
bpy.ops.wm.read_homefile(use_empty=True) if False else None
if not bpy.data.filepath:
    try:
        result = bpy.ops.object.polygroups_select_current_import_folder()
        assert result == {'CANCELLED'}
    except RuntimeError as error:
        assert 'Save the blend file first' in str(error)
with tempfile.TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'a.blend'))
    assert bpy.ops.object.polygroups_select_current_import_folder() == {'FINISHED'}
    assert Path(bpy.path.abspath(p.batch_import_directory)).resolve() == Path(directory).resolve(), p.batch_import_directory
print('select current import folder ok')
