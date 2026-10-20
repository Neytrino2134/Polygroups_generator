"""Independent Unreal LOD names, polygon ordering, materials, and UI groups."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.unreal_lod_rename import image_nodes
from polygroups_generator.custom_ui.schema import capture, walk
from polygroups_generator import ui

s = bpy.context.scene.polygroups_mesh_finalization_settings
s.unreal_lod_asset_name = 'Tree_Tropic'
s.unreal_lod_name_index = '19'
s.unreal_lod_version_index = '1'
unity_before = (s.unity_asset_name, s.unity_name_index, s.unity_asset_index)
fab_before = (s.fab_asset_name, s.fab_asset_index)
mat = bpy.data.materials.new('SourceMaterial')
mat.use_nodes = True
image = bpy.data.images.new('Source_BaseColor', width=4, height=4)
image.pixels[:] = [.1, .8, .3, 1] * 16
node = mat.node_tree.nodes.new('ShaderNodeTexImage')
node.image = image
mat.node_tree.links.new(node.outputs['Color'], mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
outside = bpy.data.objects['Cube']
outside.data.materials.clear()
outside.data.materials.append(mat)
meshes = []
for segments in (8, 16, 12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=8)
    obj = bpy.context.object
    obj.data.materials.append(mat)
    meshes.append(obj)
meshes.sort(key=lambda obj: -len(obj.data.polygons))
geometry = {obj: (len(obj.data.vertices), len(obj.data.polygons), obj.matrix_world.copy()) for obj in meshes}
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[1]
with TemporaryDirectory() as temp:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(temp) / 'Test.blend'))
    assert bpy.ops.object.polygroups_unreal_lod_rename() == {'FINISHED'}
    base = 'Tree_Tropic_19_01'
    collection = bpy.data.collections[base + '_Collection']
    assert set(collection.objects) == set(meshes)
    for index, obj in enumerate(meshes):
        assert obj.name == obj.data.name == f'SM_{base}_LOD{index}'
        assert tuple(obj.users_collection) == (collection,)
        vertices, polygons, matrix = geometry[obj]
        assert (len(obj.data.vertices), len(obj.data.polygons), obj.matrix_world) == (vertices, polygons, matrix)
    assert outside.active_material == mat and mat.name == 'SourceMaterial'
    assert node.image == image and image.name == 'Source_BaseColor'
    assert meshes[0].active_material.name == 'M_' + base
    prepared = next(image_nodes(meshes[0].active_material.node_tree)).image
    assert prepared.name == 'T_' + base + '_BaseColor'
    assert prepared.pixels[1] > .7 and Path(prepared.filepath_raw).is_file()
    before = tuple(set(ids) for ids in (bpy.data.objects, bpy.data.materials, bpy.data.images, bpy.data.collections))
    # Migrate an asset prepared before render-compatible collection suffixes.
    collection.name = base
    assert bpy.ops.object.polygroups_unreal_lod_rename() == {'FINISHED'}
    assert collection.name == base + '_Collection'
    assert tuple(set(ids) for ids in (bpy.data.objects, bpy.data.materials, bpy.data.images, bpy.data.collections)) == before
    assert unity_before == (s.unity_asset_name, s.unity_name_index, s.unity_asset_index)
    assert fab_before == (s.fab_asset_name, s.fab_asset_index)
    model = capture(bpy.context, ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_mesh_finalization))
    assert not model.errors, model.errors
    groups = [n['id'] for n in walk(model.node) if n['kind'] == 'group']
    assert any(key.endswith('.show_fab_variant_rename') for key in groups)
    assert any(key.endswith('.show_unreal_lod_rename') for key in groups)
    assert any(b[0] == 'operator' and b[1] == 'object.polygroups_unreal_lod_rename' for b in model.bindings.values())
    # A name owned by an unselected object must fail before any changes.
    blocker = bpy.data.objects.new('SM_Tree_Tropic_19_02_LOD0', bpy.data.meshes.new('Blocker'))
    bpy.context.scene.collection.objects.link(blocker)
    s.unreal_lod_version_index = '02'
    original_names = {obj: obj.name for obj in meshes}
    try:
        result = bpy.ops.object.polygroups_unreal_lod_rename()
    except RuntimeError as error:
        assert 'outside selection' in str(error)
    else:
        assert result == {'CANCELLED'}
    assert {obj: obj.name for obj in meshes} == original_names
    assert set(collection.objects) == set(meshes)
print('UNREAL_LOD_RENAME_PASSED')
