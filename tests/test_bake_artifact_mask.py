"""Blender background regression for the geometric bake artifact mask."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.baking import (
    _generate_legacy_geometric_artifact_mask as _generate_bake_artifact_mask,
    _save_image_as_png,
)

context = bpy.context
settings = context.scene.polygroups_baking_settings
settings.bake_artifact_mask = True
settings.bake_artifact_resolution = 128
settings.bake_artifact_radius = 0
settings.cage_extrusion = 0.0

bpy.ops.mesh.primitive_cube_add()
target = context.active_object
assert target.data.uv_layers.active is not None
bpy.ops.mesh.primitive_cube_add(location=(0.5, 0.0, 0.0))
source = context.active_object

image, flagged = _generate_bake_artifact_mask(context, target, [source], settings)
assert flagged > 0
white_pixels = sum(image.pixels[index] > 0.5 for index in range(0, len(image.pixels), 4))
assert white_pixels > 20  # The intersecting interior is filled even with no line width.
with TemporaryDirectory() as directory:
    path = str(Path(directory) / "ArtifactMask.png")
    _save_image_as_png(image, path)
    assert Path(path).is_file()

source.location.x = 5.0
context.view_layer.update()
image, flagged = _generate_bake_artifact_mask(context, target, [source], settings)
assert flagged == 0
assert max(image.pixels[index] for index in range(0, len(image.pixels), 4)) == 0.0

# An explicit Smart Cage, rather than the original lowpoly, drives the map.
source.location.x = 0.5
cage = target.copy()
cage.data = target.data.copy()
context.collection.objects.link(cage)
cage.location.x = 5.0
settings.smart_cage_object = cage
settings.autogenerate_smart_cage = True
context.view_layer.update()
image, flagged = _generate_bake_artifact_mask(context, target, [source], settings)
assert flagged == 0
cage.location.x = 0.0
context.view_layer.update()
image, flagged = _generate_bake_artifact_mask(context, target, [source], settings)
assert flagged > 0

addon_utils.disable(ROOT.name, default_set=True)
print("BAKE_ARTIFACT_MASK_OK", flush=True)
