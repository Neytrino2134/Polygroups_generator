"""Auto Bake material preparation sets Principled Roughness to 0.8 (bake and merged materials)."""
import sys
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import bake_images, bake_merge  # noqa: E402

ctx = bpy.context
settings = ctx.scene.polygroups_baking_settings


def new_target(name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(name, mesh)
    ctx.scene.collection.objects.link(obj)
    return obj


def roughness_of(material):
    return bake_images._principled_bsdf(material).inputs['Roughness']


# Lowpoly bake material: default 0.8, reapplied on every preparation, textured roughness untouched.
target = new_target('Retopo_01')
material, _base, _normal = bake_images._ensure_bake_material(target, settings)
assert abs(roughness_of(material).default_value - 0.8) < 1e-6, roughness_of(material).default_value
roughness_of(material).default_value = 0.3
material, _base, _normal = bake_images._ensure_bake_material(target, settings)
assert abs(roughness_of(material).default_value - 0.8) < 1e-6
texture = material.node_tree.nodes.new('ShaderNodeTexImage')
material.node_tree.links.new(texture.outputs['Color'], roughness_of(material))
roughness_of(material).default_value = 0.3
bake_images._ensure_bake_material(target, settings)
assert roughness_of(material).is_linked and abs(roughness_of(material).default_value - 0.3) < 1e-6

# Prepare Lowpoly Bake Material operator (active mesh).
other = new_target('Retopo_02')
ctx.view_layer.objects.active = other
assert bpy.ops.object.polygroups_prepare_lowpoly_bake_material() == {'FINISHED'}
assert abs(roughness_of(other.active_material).default_value - 0.8) < 1e-6

# Merged material.
images = [bpy.data.images.new(f'Merge_{name}', 4, 4) for name in ('Base', 'Normal', 'Alpha')]
merged = bake_merge._ensure_merged_material('Pack', *images, [target, other])
assert abs(roughness_of(merged).default_value - 0.8) < 1e-6
print('bake material roughness ok')
