"""Blender smoke tests for opaque bake backgrounds and dedicated merge masks."""
from array import array
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

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

# Normal maps always use the flat tangent-space normal outside coverage,
# including partially covered pixels at antialiased edges.
normal_background = baking._fill_normal_background(
    array("f", [1, 0.5, 0.5, 1, 0, 0, 0, 0, 1, 0.5, 0.5, 1]),
    array("f", [1, 0, 0.5]),
)
assert close(tuple(normal_background[0:4]), (1, 0.5, 0.5, 1))
assert close(tuple(normal_background[4:8]), (0.5, 0.5, 1, 1))
assert close(tuple(normal_background[8:12]), (0.75, 0.5, 0.75, 1))

merged_normal = baking._fill_normal_background(normal, coverage)
assert close(tuple(merged_normal[4:8]), (0.5, 0.5, 1, 1))

settings = bpy.context.scene.polygroups_baking_settings
assert settings.bake_background_mode == "EXTEND"
assert settings.merge_duplicate_meshes

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

# Reprocess a raw normal-only bake with both background settings. Neither
# setting may turn the uncovered normal pixel black or extend the red edge.
settings.bake_base_color = False
settings.bake_normal = True
normal_image = target.active_material.node_tree.nodes[baking.BAKE_NORMAL_NODE].image
raw_normal = array("f", [0.0]) * (16 * 16 * 4)
raw_normal[0:4] = array("f", [1.0, 0.5, 0.5, 1.0])
for mode in ("BLACK", "EXTEND"):
    settings.bake_background_mode = mode
    baking._write_pixels(normal_image, raw_normal)
    baking._finalize_bake_images(target, settings)
    final_normal = baking._read_image_pixels(normal_image, (16, 16))
    assert close(tuple(final_normal[0:4]), (1.0, 0.5, 0.5, 1.0))
    assert close(tuple(final_normal[4:8]), (0.5, 0.5, 1.0, 1.0))

with tempfile.TemporaryDirectory() as directory:
    project = Path(directory) / "alpha_bake_test.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(project))
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    assert bpy.ops.object.polygroups_save_bake_textures() == {"FINISHED"}
    output_name = baking._safe_path_name(baking.bake_output_name(target))
    output_dir = Path(directory) / "Bakes" / output_name
    assert (output_dir / f"{output_name}_Bake_BaseColor.png").is_file()
    assert (output_dir / f"{output_name}_Bake_Normal.png").is_file()
    assert (output_dir / f"{output_name}_Bake_MergeMask.png").is_file()

    def baked_material(name, base_image, mask_image):
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        for node_name, texture in ((baking.BAKE_BASE_COLOR_NODE, base_image), (baking.BAKE_ALPHA_NODE, mask_image)):
            node = material.node_tree.nodes.new("ShaderNodeTexImage")
            node.name = node_name
            node.image = texture
        return material

    def mesh_with_material(name, material, shared_mesh=None):
        data = shared_mesh
        if data is None:
            data = bpy.data.meshes.new(name)
            data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
            data.materials.append(material)
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        return obj

    half_left = image("Half Left", [0.5, 0.5, 0.5, 1, 0, 0, 0, 1, 0, 0, 0, 1])
    mat_a = baked_material("MatA", opaque_red, half_left)
    mat_b = baked_material("MatB", opaque_green, mask_right)
    mat_c = baked_material("MatC", opaque_green, mask_left)

    settings.merge_duplicate_meshes = False

    def run_merge(materials, material_name, mesh_name, folder_name):
        bpy.ops.object.select_all(action="DESELECT")
        first = mesh_with_material("First", materials[0])
        repeat = mesh_with_material("Repeat", materials[0], first.data)
        outsider = mesh_with_material("Unselected", materials[0], first.data)
        selected = [first, repeat, *(mesh_with_material("Additional", material) for material in materials[1:])]
        for obj in selected:
            obj.select_set(True)
        selected[2].name = mesh_name
        bpy.context.view_layer.objects.active = selected[2]
        assert bpy.ops.object.polygroups_merge_bake_textures() == {"FINISHED"}
        merged = selected[2].active_material
        assert merged.name == material_name
        assert all(obj.active_material == merged for obj in selected)
        assert outsider.active_material == materials[0]
        folder = Path(directory) / "Bakes" / folder_name
        for channel, node_name in (
            ("BaseColor", baking.BAKE_BASE_COLOR_NODE), ("Normal", baking.BAKE_NORMAL_NODE),
            ("MergeMask", baking.BAKE_ALPHA_NODE),
        ):
            path = folder / f"{folder_name}_Bake_{channel}.png"
            assert path.is_file()
            texture = merged.node_tree.nodes[node_name].image
            assert Path(bpy.path.abspath(texture.filepath)) == path
            assert texture.source == "FILE"
        assert bpy.ops.object.polygroups_save_bake_textures() == {"FINISHED"}
        selected[2].name = "Previously Merged"
        return merged.node_tree.nodes[baking.BAKE_ALPHA_NODE].image

    mask = run_merge([mat_a, mat_b], "MatB+MatA", "MergeMesh", "MergeMesh_Merged")
    assert abs(mask.pixels[0] - 0.5) < 0.01, mask.pixels[0]  # Shared material contributes only once.
    run_merge([mat_a, mat_b, mat_c], "MatB+3_Materials", "MeshMore", "MeshMore_Merged")
    run_merge([mat_a, mat_b], "MatB+MatA.001", "MergeMesh", "MergeMesh_Merged.001")

    bpy.ops.object.select_all(action="DESELECT")
    fail_a = mesh_with_material("Save Failure A", mat_a)
    fail_b = mesh_with_material("MergeMesh", mat_b)
    for obj in (fail_a, fail_b):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = fail_b
    save_png = baking._save_image_as_png

    def fail_normal(texture, path):
        if path.endswith("_Normal.png"):
            raise OSError("test PNG write failure")
        save_png(texture, path)

    with patch.object(baking, "_save_image_as_png", fail_normal):
        try:
            result = bpy.ops.object.polygroups_merge_bake_textures()
        except RuntimeError as error:
            assert "test PNG write failure" in str(error)
        else:
            assert result == {"CANCELLED"}
    assert fail_a.active_material == mat_a and fail_b.active_material == mat_b
    assert not (Path(directory) / "Bakes" / "MergeMesh_Merged.002").exists()

    settings.merge_duplicate_meshes = True
    bpy.ops.object.select_all(action="DESELECT")
    red = baked_material("Source_Long_Material_Red001", opaque_red, mask_left)
    blue = baked_material("Active_Long_Material_Blue02", opaque_green, mask_right)
    original_a = mesh_with_material("Long source mesh", red)
    original_b = mesh_with_material("ABCDEF_long_mesh_UVWXYZ", blue)
    originals = [original_a, original_b]
    for obj in originals:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = original_b
    props = [dict(obj.items()) for obj in originals]
    assert bpy.ops.object.polygroups_merge_bake_textures() == {"FINISHED"}
    copies = list(bpy.context.selected_objects)
    assert len(copies) == 2 and all(obj not in originals for obj in copies)
    assert all(obj.users_collection[0].name == "Generated.001" for obj in copies)
    assert all(obj.data not in {source.data for source in originals} for obj in copies)
    assert original_a.active_material == red and original_b.active_material == blue
    assert [dict(obj.items()) for obj in originals] == props
    merged = bpy.context.active_object.active_material
    assert merged.name == "Active___Blue02+Source___Red001"
    assert all(obj.active_material == merged for obj in copies)
    folder = Path(directory) / "Bakes" / "ABCDEF___UVWXYZ_Merged"
    assert (folder / "ABCDEF___UVWXYZ_Merged_Bake_BaseColor.png").is_file()
    assert Path(bpy.path.abspath(merged.node_tree.nodes[baking.BAKE_BASE_COLOR_NODE].image.filepath)).parent == folder

print("BAKE ALPHA MERGE PASSED")
