"""Multi-mesh move naming, indexed name preservation and single-mesh compatibility."""
import sys
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)

def create(name):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj

def move(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    assert bpy.ops.object.polygroups_move_to_new_generated_collection() == {'FINISHED'}
    col = objects[0].users_collection[0]
    assert all(tuple(obj.users_collection) == (col,) for obj in objects)
    return col

a, b = create('Alpha'), create('Beta')
col = move([b, a])
assert a.name == f'Mesh_01_{col.name}' and b.name == f'Mesh_02_{col.name}'
single = create('Keep single name')
move([single]); assert single.name == 'Keep single name'
indexed, plain = create('Retopo_01_Highpoly_Generated.099'), create('Zeta')
col = move([plain, indexed])
assert indexed.name == f'Retopo_01_Highpoly_{col.name}'
assert plain.name == f'Mesh_02_{col.name}'
print('MOVE_GENERATED_COLLECTION_NUMBERED_MESHES_PASSED')
