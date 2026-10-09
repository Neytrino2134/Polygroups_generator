import sys
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
settings = bpy.context.scene.polygroups_mesh_finalization_settings
settings.unity_asset_name = 'Tree_12'
settings.unity_asset_index = '01'
groups = {}
for index in (1, 2, 3):
    groups[index] = []
    for lod in (0, 1, 2):
        col = bpy.data.collections.new(f'Tree_12_{index:02d}_LOD{lod}_Collection')
        bpy.context.scene.collection.children.link(col)
        mesh = bpy.data.meshes.new('Mesh')
        obj = bpy.data.objects.new(f'Tree_12_{index:02d}' + (f'.LOD{lod}' if lod else ''), mesh)
        col.objects.link(obj)
        groups[index].append(col)
unrelated = bpy.data.collections.new('Other_01_LOD0_Collection')
bpy.context.scene.collection.children.link(unrelated)
def check(index):
    assert settings.unity_asset_index == f'{index:02d}'
    for key, collections in groups.items():
        assert all(col.hide_viewport == (key != index) for col in collections)
    assert not unrelated.hide_viewport
    assert bpy.context.active_object.name == f'Tree_12_{index:02d}'
assert bpy.ops.object.polygroups_unity_collection_step(delta=1) == {'FINISHED'}
check(2)
assert bpy.ops.object.polygroups_unity_collection_step(delta=1) == {'FINISHED'}
check(3)
assert bpy.ops.object.polygroups_unity_collection_step(delta=1) == {'FINISHED'}
check(3)
assert bpy.ops.object.polygroups_unity_collection_step(delta=-1) == {'FINISHED'}
check(2)
assert bpy.ops.object.polygroups_unity_collection_step(delta=-1) == {'FINISHED'}
check(1)
print('UNITY_COLLECTION_NAVIGATION_PASSED')
