"""Blender smoke tests for opaque bake backgrounds and dedicated merge masks."""
from array import array
from pathlib import Path
import sys
import tempfile

import addon_utils
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)

from polygroups_generator.operators import baking


def image(name, pixels):
    result = bpy.data.images.new(name, width=3, height=1, alpha=True)
    result.pixels.foreach_set(array("f", pixels))
    result.update()
    return result


def close(actual, expected, tolerance=0.003):
    return all(abs(value - target) <= tolerance for value, target in zip(actual, expected))


opaque_red = image("Test Base Red", [1, 0, 0, 1] * 3)
opaque_green = image("Test Base Green", [0, 1, 0, 1] * 3)
normal_x = image("Test Normal X", [1, 0.5, 0.5, 1] * 3)
normal_y = image("Test Normal Y", [0.5, 1, 0.5, 1] * 3)
mask_left = image("Test Mask Left", [1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1])
mask_right = image("Test Mask Right", [0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1])
packs = [
    {"base": opaque_red, "normal": normal_x, "alpha": mask_left},
    {"base": opaque_green, "normal": normal_y, "alpha": mask_right},
]
resolution = (3, 1)

base = baking._merge_base_color_pixels(packs, resolution)
assert tuple(round(base[index], 4) for index in (0, 1, 2, 3)) == (1.0, 0.0, 0.0, 1.0)
assert tuple(round(base[index], 4) for index in (4, 5, 6, 7)) == (0.0, 0.0, 0.0, 0.0)
assert tuple(round(base[index], 4) for index in (8, 9, 10, 11)) == (0.0, 1.0, 0.0, 1.0)

normal = baking._merge_normal_pixels(packs, resolution)
assert close(tuple(normal[index] for index in (0, 1, 2, 3)), (1.0, 0.5, 0.5, 1.0))
assert normal[7] == 0.0
assert close(tuple(normal[index] for index in (8, 9, 10, 11)), (0.5, 1.0, 0.5, 1.0))

coverage = baking._merge_pack_coverage(packs, resolution)
assert tuple(coverage) == (1.0, 0.0, 1.0)
black = baking._apply_bake_background(base, coverage, resolution, "BLACK")
assert tuple(black[4:8]) == (0.0, 0.0, 0.0, 1.0)

center_blue = array("f", [0, 0, 0, 0, 0.2, 0.4, 0.8, 1, 0, 0, 0, 0])
extended = baking._apply_bake_background(
    center_blue, array("f", [0, 1, 0]), resolution, "EXTEND",
)
for index in range(0, len(extended), 4):
    assert close(tuple(extended[index:index + 4]), (0.2, 0.4, 0.8, 1.0))

settings = bpy.context.scene.polygroups_baking_settings
assert settings.bake_background_mode == "EXTEND"

# Simulate a raw Base Color bake and verify that finalization creates a separate
# opaque grayscale Alpha image before making the color image opaque.
mesh = bpy.data.meshes.new("Bake Alpha Target Mesh")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
mesh.uv_layers.new(name="UVMap")
target = bpy.data.objects.new("Bake Alpha Target", mesh)
bpy.context.scene.collection.objects.link(target)
settings.bake_resolution = 16
settings.bake_base_color = True
settings.bake_normal = False
settings.bake_background_mode = "BLACK"
_material, base_node, _normal_node = baking._ensure_bake_material(target, settings)
raw_pixels = array("f", [0.0]) * (16 * 16 * 4)
raw_pixels[0:4] = array("f", [0.8, 0.4, 0.2, 1.0])
baking._write_pixels(base_node.image, raw_pixels)

alpha_image = baking._finalize_bake_images(target, settings)
assert alpha_image is not None
assert target[baking.BAKE_ALPHA_IMAGE_PROP] == alpha_image.name
assert target[baking.BAKE_SOURCE_ALPHA_IMAGE_PROP] == alpha_image.name
assert target.active_material.node_tree.nodes[baking.BAKE_ALPHA_NODE].image == alpha_image
alpha_pixels = baking._read_image_pixels(alpha_image, (16, 16))
assert close(tuple(alpha_pixels[0:4]), (1.0, 1.0, 1.0, 1.0))
assert close(tuple(alpha_pixels[4:8]), (0.0, 0.0, 0.0, 1.0))
final_base = baking._read_image_pixels(base_node.image, (16, 16))
assert close(tuple(final_base[4:8]), (0.0, 0.0, 0.0, 1.0))

with tempfile.TemporaryDirectory() as directory:
    project = Path(directory) / "alpha_bake_test.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(project))
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    assert bpy.ops.object.polygroups_save_bake_textures() == {"FINISHED"}
    output_name = baking._safe_path_name(baking.bake_collection_name(target) or target.name)
    output_dir = Path(directory) / "Bakes" / output_name
    assert (output_dir / f"{output_name}_Bake_BaseColor.png").is_file()
    assert (output_dir / f"{output_name}_Bake_Normal.png").is_file()
    assert (output_dir / f"{output_name}_Bake_Alpha.png").is_file()

print("BAKE ALPHA MERGE PASSED")
