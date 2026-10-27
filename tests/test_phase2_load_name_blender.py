"""Load filename identity into the selected Phase 2 pipeline, preserving Unity defaults."""
from pathlib import Path
import sys
import tempfile
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
assert addon_utils.enable(ROOT.name, default_set=False)
ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings
s = ctx.scene.polygroups_mesh_finalization_settings
with tempfile.TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'Grave_Stone_04_12.blend'))
    s.unity_asset_name = 'KeepUnity'
    p.phase2_run_engine = 'FAB'
    assert bpy.ops.object.polygroups_unity_load_from_file(target='PHASE2') == {'FINISHED'}
    assert (s.unreal_lod_asset_name, s.unreal_lod_name_index, s.unreal_lod_version_index) == ('Grave_Stone', '04', '12')
    assert s.unity_asset_name == 'KeepUnity'
    p.phase2_run_engine = 'UNITY'
    assert bpy.ops.object.polygroups_unity_load_from_file(target='PHASE2') == {'FINISHED'}
    assert (s.unity_asset_name, s.unity_name_index, s.unity_asset_index) == ('Grave_Stone', '04', '12')
    s.unity_asset_name = 'Changed'
    p.phase2_run_engine = 'FAB'
    assert bpy.ops.object.polygroups_unity_load_from_file() == {'FINISHED'}
    assert s.unity_asset_name == 'Grave_Stone'
    from polygroups_generator.custom_ui.schema import capture
    panel = capture(ctx, 1)
    assert not panel.errors, panel.errors
    assert any(binding[0] == 'operator' and binding[1] == 'object.polygroups_unity_load_from_file'
               and binding[2].target == 'PHASE2' for binding in panel.bindings.values())
print('PHASE2_LOAD_FILENAME_PASSED')
