"""Remove Unused Slots cleans every selected mesh and leaves unselected ones alone."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)


def mesh_with_slots(count):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    for index in range(count):
        obj.data.materials.append(bpy.data.materials.new(f'{obj.name}_m{index}'))
    for polygon in obj.data.polygons:
        polygon.material_index = 0          # only slot 0 is used
    return obj


a, b, c = mesh_with_slots(4), mesh_with_slots(3), mesh_with_slots(5)
bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
b.select_set(True)
bpy.context.view_layer.objects.active = a
assert bpy.ops.object.polygroups_remove_unused_slots() == {'FINISHED'}
assert len(a.material_slots) == 1 and len(b.material_slots) == 1, (len(a.material_slots), len(b.material_slots))
assert len(c.material_slots) == 5
assert a.material_slots[0].material.name.endswith('_m0')
print('remove unused slots ok')
