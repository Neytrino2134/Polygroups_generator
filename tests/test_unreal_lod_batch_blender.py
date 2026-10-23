"""Collection-scoped Unreal LOD batches, version increments and custom High suffix."""
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
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator import ui

s = bpy.context.scene.polygroups_mesh_finalization_settings
s.unreal_lod_asset_name = 'Rock'
s.unreal_lod_name_index = '19'
s.unreal_lod_version_index = '09'
assert s.unreal_lod_high_suffix == '_MID' and s.unreal_lod_keep_high
s.unreal_lod_keep_high = False
mat = bpy.data.materials.new('SharedInput')
mat.use_nodes = True
image = bpy.data.images.new('Input_BaseColor', width=4, height=4)
image.pixels[:] = [.4, .7, .2, 1] * 16
node = mat.node_tree.nodes.new('ShaderNodeTexImage')
node.image = image
mat.node_tree.links.new(node.outputs['Color'], mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
packs = {}
for number in (10, 2, 1):
    collection = bpy.data.collections.new(f'Generated.{number:03d}')
    bpy.context.scene.collection.children.link(collection)
    meshes = []
    for segments in (8, 16, 12):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=8)
        obj = bpy.context.object
        obj.name = f'Input{number}_{segments}'
        obj.data.materials.append(mat)
        for previous in list(obj.users_collection):
            previous.objects.unlink(obj)
        collection.objects.link(obj)
        meshes.append(obj)
    packs[number] = sorted(meshes, key=lambda obj: -len(obj.data.polygons))
bpy.ops.object.select_all(action='DESELECT')
for meshes in packs.values():
    for obj in meshes:
        obj.select_set(True)
bpy.context.view_layer.objects.active = packs[2][0]
original = {obj: (len(obj.data.polygons), obj.matrix_world.copy()) for meshes in packs.values() for obj in meshes}
with TemporaryDirectory() as temp:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(temp) / 'Batch.blend'))
    assert bpy.ops.object.polygroups_unreal_lod_rename() == {'FINISHED'}
    for number, version in ((1, '09'), (2, '10'), (10, '11')):
        base = 'Rock_19_' + version
        assert set(bpy.data.collections[base + '_Collection'].objects) == set(packs[number])
        assert [obj.name for obj in packs[number]] == [f'SM_{base}_LOD{i}' for i in range(3)]
        assert not bpy.data.collections[f'Generated.{number:03d}'].objects
    s.unreal_lod_keep_high = True
    s.unreal_lod_high_suffix = '_HIGH'
    before = tuple(set(ids) for ids in (bpy.data.objects, bpy.data.materials, bpy.data.images, bpy.data.collections))
    assert bpy.ops.object.polygroups_unreal_lod_rename() == {'FINISHED'}
    for number, version in ((1, '09'), (2, '10'), (10, '11')):
        base = 'Rock_19_' + version
        assert [obj.name for obj in packs[number]] == [f'SM_{base}_HIGH', f'SM_{base}_LOD0', f'SM_{base}_LOD1']
        assert packs[number][0]['unreal_lod_index'] == -1
        for obj in packs[number]:
            assert (len(obj.data.polygons), obj.matrix_world) == original[obj]
            assert obj.active_material.get('unreal_lod_asset') == base
            texture = next(image_nodes(obj.active_material.node_tree)).image
            assert Path(texture.filepath_raw).parent.name == base
    assert bpy.ops.object.polygroups_unreal_lod_rename() == {'FINISHED'}
    assert tuple(set(ids) for ids in (bpy.data.objects, bpy.data.materials, bpy.data.images, bpy.data.collections)) == before
    model = capture(bpy.context, ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_mesh_finalization))
    assert not model.errors, model.errors
    assert any(b[0] == 'property' and b[2] == 'unreal_lod_high_suffix' for b in model.bindings.values())
    # A conflict in a later pack must stop the entire batch before renaming.
    blocker = bpy.data.objects.new('SM_Rock_19_21_LOD0', bpy.data.meshes.new('Conflict'))
    bpy.context.scene.collection.objects.link(blocker)
    s.unreal_lod_version_index = '20'
    names = {obj: obj.name for obj in original}
    try:
        result = bpy.ops.object.polygroups_unreal_lod_rename()
    except RuntimeError as error:
        assert 'outside selection' in str(error)
    else:
        assert result == {'CANCELLED'}
    assert {obj: obj.name for obj in original} == names
print('UNREAL_LOD_BATCH_PASSED')
