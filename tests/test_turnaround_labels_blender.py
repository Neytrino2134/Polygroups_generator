"""Check caption visibility through real operators with only rendering mocked."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import turnaround_animation as ta

scene = bpy.context.scene
settings = scene.polygroups_render_settings
settings.animation_frame_count = 2
bpy.ops.mesh.primitive_cube_add()
source = bpy.context.object
source.name = 'Caption Test Mesh'
assert bpy.ops.object.polygroups_prepare_turnaround_animation() == {'FINISHED'}
collection = bpy.data.collections[settings.animation_collection_name]
labels = {obj[ta.TURNAROUND_LABEL_PROP]: obj for obj in collection.objects
          if ta.TURNAROUND_LABEL_PROP in obj}
assert set(labels) == {'name', '0', '90', '180', '270'}
assert labels['name'].data.body == source.name
assert {key: labels[str(key)].data.body for key in ta.VIEW_LABELS} == ta.VIEW_LABELS
calls = []

def render(*args, **kwargs):
    visible = {key for key, obj in labels.items() if not obj.hide_render}
    if kwargs.get('animation'):
        assert visible == {'name'}
        calls.append('animation')
    else:
        angle = (0, 90, 180, 270)[len(calls)]
        assert visible == {'name', str(angle)}
        calls.append(angle)
    for key in visible:
        assert labels[key].parent == scene.camera
        assert labels[key].location.z < 0
    return {'FINISHED'}

class BlenderProxy:
    ops = SimpleNamespace(render=SimpleNamespace(render=render))

    def __getattr__(self, name):
        return getattr(bpy, name)

with TemporaryDirectory() as directory:
    settings.output_directory = directory
    with patch.object(ta, 'bpy', BlenderProxy()):
        assert bpy.ops.object.polygroups_render_turnaround_views() == {'FINISHED'}
        assert bpy.ops.object.polygroups_render_turnaround_animation() == {'FINISHED'}
assert calls == [0, 90, 180, 270, 'animation']
assert not labels['name'].hide_render
assert all(labels[str(angle)].hide_render for angle in ta.VIEW_LABELS)
print('TURNAROUND_LABELS_TEST_PASSED')
