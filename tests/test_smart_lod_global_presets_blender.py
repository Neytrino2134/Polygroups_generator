"""Global preset persistence across file loads, legacy migration and failed writes."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import smart_lod_presets as presets
from polygroups_generator.operators.smart_lod_presets import seed_presets

with TemporaryDirectory() as directory:
    root = Path(directory)
    path = root / 'config' / 'smart_lod_presets.json'
    with patch.object(presets, 'preset_path', return_value=path):
        settings = bpy.context.scene.polygroups_mesh_finalization_settings
        presets.seed(settings)
        presets.write(settings.smart_lods_presets.add(), 'Legacy', 2, [170] * 10)
        seed_presets()
        assert presets.find(settings, 'Legacy')
        bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Old.blend'))
        settings.smart_lods_count = 3
        settings.smart_lods_target_1 = 321
        assert bpy.ops.object.polygroups_smart_lods_preset(action='ADD', name='Global Mobile') == {'FINISHED'}
        settings.smart_lods_target_1 = 654
        assert bpy.ops.object.polygroups_smart_lods_preset(action='SAVE') == {'FINISHED'}
        assert json.loads(path.read_text())['presets'][-1]['targets'][0] == 654
        # Loading a blend created before the custom preset must keep the global library.
        bpy.ops.wm.open_mainfile(filepath=str(root / 'Old.blend'))
        settings = bpy.context.scene.polygroups_mesh_finalization_settings
        assert presets.find(settings, 'Global Mobile').targets[0] == 654
        settings.smart_lods_preset_active = 'Global Mobile'
        assert settings.smart_lods_count == 3 and settings.smart_lods_target_1 == 654
        assert bpy.ops.object.polygroups_smart_lods_preset(action='REMOVE') == {'FINISHED'}
        settings.smart_lods_preset_active = 'Legacy'
        assert bpy.ops.object.polygroups_smart_lods_preset(action='REMOVE') == {'FINISHED'}
        # Old blend still contains Legacy, but must not resurrect a deleted preset.
        bpy.ops.wm.open_mainfile(filepath=str(root / 'Old.blend'))
        settings = bpy.context.scene.polygroups_mesh_finalization_settings
        assert presets.find(settings, 'Legacy') is None
        assert presets.find(settings, 'Global Mobile') is None
        # New files and scenes receive globally customized engine budgets.
        settings.smart_lods_preset_active = 'Unreal'
        settings.smart_lods_target_1 = 777
        assert bpy.ops.object.polygroups_smart_lods_preset(action='SAVE') == {'FINISHED'}
        bpy.ops.wm.read_factory_settings(use_empty=True)
        addon_utils.enable(ROOT.name, default_set=False)
        settings = bpy.context.scene.polygroups_mesh_finalization_settings
        current = presets.read_current(settings)
        seed_presets()
        assert presets.find(settings, 'Unreal').targets[0] == 777
        assert presets.read_current(settings) == current
        settings.smart_lods_preset_active = 'Unreal'
        assert settings.smart_lods_target_1 == 777
        # Read-only storage failures must not publish an unsaved change.
        before = path.read_bytes()
        settings.smart_lods_target_1 = 999
        with patch.object(presets.os, 'replace', side_effect=PermissionError('read only')):
            try:
                result = bpy.ops.object.polygroups_smart_lods_preset(action='SAVE')
            except RuntimeError:
                result = {'CANCELLED'}
        assert result == {'CANCELLED'} and path.read_bytes() == before
        assert presets.find(settings, 'Unreal').targets[0] == 777
        # Invalid global content is preserved, and local presets remain usable.
        path.write_text('invalid JSON', encoding='utf-8')
        seed_presets()
        assert path.read_text() == 'invalid JSON' and presets.find(settings, 'Unreal')
print('GLOBAL_SMART_LOD_PRESETS_FILE_LOAD_MIGRATION_AND_FAILURES_OK')
