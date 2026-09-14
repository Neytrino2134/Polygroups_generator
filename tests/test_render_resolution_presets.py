"""Run with Blender --background --factory-startup --python-exit-code 1."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)

scene = bpy.context.scene
settings = scene.polygroups_render_settings
assert (settings.resolution_x, settings.resolution_y) == (1024, 1024)

expected = {
    "SQUARE": ((1024, 1024), (2048, 2048), (4096, 4096)),
    "WIDE": ((1024, 576), (2048, 1152), (4096, 2304)),
    "PORTRAIT": ((768, 1024), (1536, 2048), (3072, 4096)),
}
for aspect, dimensions in expected.items():
    settings.resolution_aspect_preset = aspect
    for size, pair in zip(("1K", "2K", "4K"), dimensions):
        settings.resolution_size_preset = size
        assert (settings.resolution_x, settings.resolution_y) == pair

# The Apply action uses the current fields, including a custom resolution.
settings.resolution_x = 1200
settings.resolution_y = 1600
settings.resolution_scale = 75
scene.render.pixel_aspect_x = 2.0
scene.render.pixel_aspect_y = 1.0
assert bpy.ops.render.polygroups_apply_resolution() == {"FINISHED"}
assert (scene.render.resolution_x, scene.render.resolution_y) == (1200, 1600)
assert scene.render.resolution_percentage == 75
assert (scene.render.pixel_aspect_x, scene.render.pixel_aspect_y) == (1.0, 1.0)

bpy.ops.object.camera_add()
camera = bpy.context.object
scene.camera = camera
frame = camera.data.view_frame(scene=scene)
width = max(vertex.x for vertex in frame) - min(vertex.x for vertex in frame)
height = max(vertex.y for vertex in frame) - min(vertex.y for vertex in frame)
assert abs(width / height - 0.75) < 1e-5

print("RENDER_RESOLUTION_PRESETS_OK")
