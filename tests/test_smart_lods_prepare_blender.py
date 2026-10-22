import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
s = bpy.context.scene.polygroups_mesh_finalization_settings
assert s.smart_lods_target_1 == 2900
assert s.unity_name_index == '00'
s.unity_asset_name = 'Tree'
s.unity_asset_index = '01'
s.unreal_lod_asset_name = 'Tree'
s.unreal_lod_name_index = '00'
s.unreal_lod_version_index = '01'
s.unreal_lod_prepare_materials = False
s.unity_auto_increment_index = False
s.smart_lods_count = 2
s.smart_lods_target_1 = 80
s.smart_lods_target_2 = 40
s.smart_lods_target_3 = 20
s.smart_lods_create_text = False
with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory)/'Test.blend'))
    for mode in ('UNITY','UNREAL'):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6)
        source = bpy.context.object
        source.name = 'Source' + mode
        source_count = len(source.data.polygons)
        s.smart_lods_prepare_mode = mode
        assert bpy.ops.object.polygroups_smart_lods_prepare() == {'FINISHED'}
        meshes = list(bpy.context.selected_objects)
        assert source not in meshes
        assert len(source.data.polygons) == source_count
        assert source.name == 'Source' + mode
        assert all(o.type == 'MESH' for o in meshes)
        assert s.smart_lods_count == 2
        if mode == 'UNITY':
            assert {o.name for o in meshes} == {'Tree_00_01','Tree_00_01.LOD1'}
        else:
            assert {o.name for o in meshes} == {'SM_Tree_00_01_LOD0','SM_Tree_00_01_LOD1'}
print('SMART_LODS_PREPARE_PASSED')
