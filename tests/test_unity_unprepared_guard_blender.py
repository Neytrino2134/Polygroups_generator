"""Export Unity Assets refuses unprepared meshes up front, with a clear message, in every invocation."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import unity_preparation as up, turnaround_animation as ta

settings = bpy.context.scene.polygroups_mesh_finalization_settings
bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.object
assert 'not prepared' in up.unprepared_meshes_error(bpy.context) and cube.name in up.unprepared_meshes_error(bpy.context)
for all_renders in (False, True):
    settings.unity_export_all_renders = all_renders
    for invocation in ('EXEC_DEFAULT', 'INVOKE_DEFAULT'):
        try:
            result = bpy.ops.object.polygroups_export_unity(invocation)
            assert result == {'CANCELLED'}, result
        except RuntimeError as error:
            assert 'not prepared' in str(error), error
        assert 'not prepared' in settings.unity_export_status
        assert ta._ACTIVE_RENDER_TASK is None and not bpy.context.scene.polygroups_render_settings.is_running
cube['unity_prepared'] = True
assert up.unprepared_meshes_error(bpy.context) is None
print('unity unprepared guard ok')
