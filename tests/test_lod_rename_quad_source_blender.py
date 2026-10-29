"""A quad MID with fewer polygons than its triangulated LOD0 must stay the source.

Small Lava Rocks 01_01/07/10/11: ~2755-quad MIDs ranked below 2900-triangle
LOD0s by polygon count, so the rename swapped _MID and _LOD0.
"""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)

c = bpy.context
s = c.scene.polygroups_mesh_finalization_settings
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)


def grid(name, cuts, triangulate=False, lod=None):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=cuts, y_subdivisions=cuts)
    obj = c.object
    obj.name = name
    if triangulate:
        obj.modifiers.new('T', 'TRIANGULATE')
        bpy.ops.object.modifier_apply(modifier='T')
    if lod is not None:
        obj['polygroups_lod_source'] = 'Rock_MID'
        obj['polygroups_lod_index'] = lod
    return obj


source = grid('Rock_MID', 21)                     # 400 quads = 800 triangles
lods = [grid('Rock_LOD0', 17, True, 0),           # 512 triangles > 400 quads
        grid('Rock_LOD1', 9, True, 1)]
assert len(source.data.polygons) < len(lods[0].data.polygons)
s.unreal_lod_prepare_materials = s.unity_copy_textures = False
for engine in ('UNREAL', 'UNITY'):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [source] + lods:
        obj.select_set(True)
    c.view_layer.objects.active = source
    if engine == 'UNREAL':
        s.unreal_lod_asset_name, s.unreal_lod_name_index, s.unreal_lod_version_index = 'Rock', '01', '01'
        s.unreal_lod_keep_high, s.unreal_lod_high_suffix = True, '_MID'
        assert bpy.ops.object.polygroups_unreal_lod_rename('EXEC_DEFAULT') == {'FINISHED'}
        assert source.name == 'SM_Rock_01_01_MID', source.name
        assert [obj.name for obj in lods] == ['SM_Rock_01_01_LOD0', 'SM_Rock_01_01_LOD1']
    else:
        # Unity numbers the whole selection: the quad source must be LOD0.
        s.unity_asset_name, s.unity_name_index, s.unity_asset_index = 'Rock', '01', '01'
        assert bpy.ops.object.polygroups_prepare_unity('EXEC_DEFAULT', auto_lods=True) == {'FINISHED'}
        order = sorted([source] + lods, key=lambda obj: obj.name)
        assert order[0] == source, [obj.name for obj in order]
print('LOD_RENAME_QUAD_SOURCE_OK', flush=True)
