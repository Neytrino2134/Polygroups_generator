"""FBX exports write smoothing groups (Face) by default so Unreal does not warn about missing smoothing groups."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import mesh_export

settings = bpy.context.scene.polygroups_mesh_finalization_settings
assert settings.unreal_fbx_smoothing == 'FACE'
assert 'mesh_smooth_type' in bpy.ops.export_scene.fbx.get_rna_type().properties.keys()
sent = []
fake_ops = SimpleNamespace(export_scene=SimpleNamespace(fbx=lambda **kwargs: sent.append(kwargs) or {'FINISHED'}))
with patch.object(mesh_export.bpy, 'ops', fake_ops):
    for mode in ('FACE', 'EDGE', 'OFF'):
        settings.unreal_fbx_smoothing = mode
        mesh_export._export_selected_object('a.fbx', 'FBX')
        assert sent[-1]['mesh_smooth_type'] == mode
print('fbx smoothing ok')
