"""Reshape: Setup Resculpting + Multires Apply Base into a 'Reshape' shape key (0 = before, 1 = after)."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
ctx = bpy.context
settings = ctx.scene.polygroups_resculpting_settings
settings.multires_levels = 1


def make(name, subdivisions, radius, collection):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


collection = bpy.data.collections.new('Generated.001')
ctx.scene.collection.children.link(collection)
high = make('Highpoly_Generated.001', 4, 1.5, collection)      # the surface the lowpoly reshapes to
low = make('Retopo_01_Highpoly_Generated.001', 2, 1.0, collection)
before = [tuple(v.co) for v in low.data.vertices]
for obj in bpy.context.selected_objects:
    obj.select_set(False)
low.select_set(True)
ctx.view_layer.objects.active = low

assert bpy.ops.object.polygroups_reshape() == {'FINISHED'}
assert low.name == 'Retopo_01_Highpoly_Generated.001', low.name           # not renamed to Resculpting_
assert not low.modifiers, [m.type for m in low.modifiers]                  # Multires is gone
keys = low.data.shape_keys.key_blocks
assert [k.name for k in keys] == ['Basis', 'Reshape'] and keys['Reshape'].value == 1.0
# Basis is the shape before; the base mesh itself still shows it.
assert [tuple(k.co) for k in keys['Basis'].data] == before
assert [tuple(v.co) for v in low.data.vertices] == before
# Reshape moved the surface towards the highpoly (radius 1.5 sphere).
moved = max((Vector(a.co) - Vector(b)).length for a, b in zip(keys['Reshape'].data, before))
assert moved > 0.05, moved
assert abs(sum(k.co.length for k in keys['Reshape'].data) / len(before) - 1.5) < abs(1.0 - 1.5)

# Show / Hide switches the slider between 1 and 0.
assert bpy.ops.object.polygroups_toggle_reshape() == {'FINISHED'} and keys['Reshape'].value == 0.0
assert bpy.ops.object.polygroups_toggle_reshape() == {'FINISHED'} and keys['Reshape'].value == 1.0

# A mesh with shape keys is refused (Multires would conflict); no damage is done.
try:
    result = bpy.ops.object.polygroups_reshape()
except RuntimeError:
    result = {'CANCELLED'}
assert result == {'CANCELLED'} and [k.name for k in keys] == ['Basis', 'Reshape']
print('reshape ok')
