"""Both engines, both commands, Generated and prepared HIGH/MID inputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.lod_naming import lod_name, lod_index
from polygroups_generator.operators.smart_lods import LOD_SOURCE

s = bpy.context.scene.polygroups_mesh_finalization_settings
s.smart_lods_count = 3
s.smart_lods_create_text = True
s.smart_lods_auto_arrange = False
s.unity_copy_textures = False
s.unity_auto_increment_index = False
s.unreal_lod_prepare_materials = False
s.unreal_lod_copy_textures = False
for index, target in enumerate((80, 40, 20), 1):
    setattr(s, f'smart_lods_target_{index}', target)


def reset():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)


def source(name, collection):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6)
    obj = bpy.context.object
    obj.name = name
    for owner in tuple(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'Naming.blend'))
    for engine in ('UNITY', 'UNREAL'):
        for prepared in (False, True) if engine == 'UNREAL' else (False,):
            for variant in ('MID', 'HIGH') if prepared else ('MID',):
                for combined in (False, True):
                    reset()
                    s.smart_lods_prepare_mode = engine
                    s.unity_asset_name = s.unreal_lod_asset_name = 'GraveStones'
                    s.unity_name_index = s.unreal_lod_name_index = '02'
                    s.unity_asset_index = s.unreal_lod_version_index = '01'
                    collection = bpy.data.collections.new('GraveStones_02_01_Collection' if prepared else 'Generated.001')
                    bpy.context.scene.collection.children.link(collection)
                    obj = source(f'SM_GraveStones_02_01_{variant}' if prepared else 'Retopo_12_Highpoly_Generated.001', collection)
                    if prepared:
                        other = source(f'SM_GraveStones_02_01_{"HIGH" if variant == "MID" else "MID"}', collection)
                        # Asset identity is inferred from the source, not stale UI fields.
                        s.unreal_lod_asset_name = 'Unrelated'
                        other.select_set(False)
                    bpy.context.view_layer.objects.active = obj
                    obj.select_set(True)
                    original_name, original_mesh = obj.name, obj.data
                    original_vertices = tuple(tuple(vertex.co) for vertex in obj.data.vertices)
                    if combined:
                        assert bpy.ops.object.polygroups_smart_lods_prepare() == {'FINISHED'}
                        expected = ({'GraveStones_02_01', 'GraveStones_02_01.LOD1', 'GraveStones_02_01.LOD2'}
                                    if engine == 'UNITY' else {f'SM_GraveStones_02_01_LOD{i}' for i in range(3)})
                        assert {item.name for item in bpy.context.selected_objects} == expected
                    else:
                        assert bpy.ops.object.polygroups_generate_smart_lods() == {'FINISHED'}
                        expected = {lod_name(original_name, i, engine) for i in range(3)}
                        assert expected <= set(bpy.data.objects.keys())
                        before = set(bpy.data.objects)
                        assert bpy.ops.object.polygroups_generate_smart_lods() == {'CANCELLED'}
                        assert before == set(bpy.data.objects)
                    meshes = [item for item in bpy.data.objects if item.type == 'MESH' and item.get(LOD_SOURCE) == original_name]
                    assert len(meshes) == 3 and {lod_index(item) for item in meshes} == {0, 1, 2}
                    assert obj.name == original_name and obj.data == original_mesh
                    assert tuple(tuple(vertex.co) for vertex in obj.data.vertices) == original_vertices
                    if prepared:
                        assert set(meshes) <= set(collection.objects)
                        assert other.name.startswith('SM_GraveStones_02_01_')
                        assert s.unreal_lod_asset_name == 'Unrelated'
    # Two quality variants of the same asset must not partially generate one pack.
    reset()
    s.smart_lods_prepare_mode = 'UNREAL'
    collection = bpy.data.collections.new('GraveStones_02_01_Collection')
    bpy.context.scene.collection.children.link(collection)
    high = source('SM_GraveStones_02_01_HIGH', collection)
    mid = source('SM_GraveStones_02_01_MID', collection)
    high.select_set(True)
    before = set(bpy.data.objects)
    assert bpy.ops.object.polygroups_generate_smart_lods() == {'CANCELLED'}
    assert before == set(bpy.data.objects)

    # A legacy Unity pack is retained rather than duplicated under new names.
    reset()
    s.smart_lods_prepare_mode = 'UNITY'
    collection = bpy.data.collections.new('Generated.001')
    bpy.context.scene.collection.children.link(collection)
    original = source('Legacy', collection)
    old = source('Legacy.LOD.1', collection)
    old.select_set(False)
    original.select_set(True)
    bpy.context.view_layer.objects.active = original
    before = set(bpy.data.objects)
    assert bpy.ops.object.polygroups_generate_smart_lods() == {'CANCELLED'}
    assert before == set(bpy.data.objects)

    # Shared UI: engine choice precedes generation, budget labels start at 0.
    from polygroups_generator import ui
    from polygroups_generator.custom_ui.schema import capture, walk
    section = ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_mesh_finalization)
    for engine in ('UNITY', 'UNREAL'):
        s.smart_lods_prepare_mode = engine
        model = capture(bpy.context, section)
        assert not model.errors, model.errors
        bindings = list(model.bindings.values())
        engine_position = next(i for i, binding in enumerate(bindings)
                               if binding[0] == 'property' and binding[2] == 'smart_lods_prepare_mode')
        generate_position = next(i for i, binding in enumerate(bindings)
                                 if binding[0] == 'operator' and binding[1] == 'object.polygroups_generate_smart_lods')
        assert engine_position < generate_position
        assert any(node.get('text') == 'LOD0 Tris' for node in walk(model.node))

print('LOD_ENGINE_NAMING_PASSED')
