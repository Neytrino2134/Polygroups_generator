"""Registration cycles and .blend persistence after splitting RNA modules."""
from pathlib import Path
import sys
import tempfile

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = addon_utils.enable(ROOT.name, default_set=False)
assert addon is not None
from polygroups_generator import properties
from polygroups_generator.settings import preparation

assert properties.POLYGROUPS_PG_model_preparation_settings is preparation.POLYGROUPS_PG_model_preparation_settings
names = tuple(cls.__name__ for cls in properties.CLASSES)
for _ in range(2):
    addon.unregister()
    assert not hasattr(bpy.types.Scene, 'polygroups_model_preparation_settings')
    addon.register()
    assert tuple(cls.__name__ for cls in properties.CLASSES) == names

scene = bpy.context.scene
scene.polygroups_model_preparation_settings.batch_voxel_size = 0.017
scene.polygroups_object_seam_cutter_settings.cutter_draw_stabilize_radius = 37
scene.polygroups_render_settings.image_format = 'JPEG'
with tempfile.TemporaryDirectory(prefix='polygroups_settings_') as directory:
    path = str(Path(directory) / 'settings.blend')
    bpy.ops.wm.save_as_mainfile(filepath=path)
    scene.polygroups_model_preparation_settings.batch_voxel_size = 0.003
    scene.polygroups_object_seam_cutter_settings.cutter_draw_stabilize_radius = 25
    scene.polygroups_render_settings.image_format = 'PNG'
    bpy.ops.wm.open_mainfile(filepath=path)
    scene = bpy.context.scene
    assert abs(scene.polygroups_model_preparation_settings.batch_voxel_size - 0.017) < 1e-7
    assert scene.polygroups_object_seam_cutter_settings.cutter_draw_stabilize_radius == 37
    assert scene.polygroups_render_settings.image_format == 'JPEG'

addon_utils.disable(ROOT.name, default_set=False)
print('REFACTOR_SETTINGS_LIFECYCLE_PASSED')
