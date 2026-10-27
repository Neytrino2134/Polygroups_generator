"""Actual mesh/resource renaming, shared data, rollback, FBX/Blend and gallery JSON."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
assert addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import rename_final as rename
from polygroups_generator.services import fab_media as media

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings
gallery = ctx.scene.airetopo_fab_media_settings
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)


def cube(col, name):
    bpy.ops.mesh.primitive_cube_add()
    obj = ctx.object
    obj.name = obj.data.name = name
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    col.objects.link(obj)
    return obj


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    image = bpy.data.images.new('Old_BaseColor', width=8, height=8)
    image.filepath_raw = str(root / 'Old_BaseColor.png')
    image.file_format = 'PNG'
    image.save()
    image.source = 'FILE'
    image.reload()
    old_bytes = (root / 'Old_BaseColor.png').read_bytes()
    material = bpy.data.materials.new('Shared_Material')
    material.use_nodes = True
    material.node_tree.nodes.new('ShaderNodeTexImage').image = image
    packs = []
    for index in (2, 10):
        base = f'Old_00_{index:02}'
        col = bpy.data.collections.new(base + '_Collection')
        ctx.scene.collection.children.link(col)
        meshes = [cube(col, 'SM_' + base + '_' + suffix) for suffix in ('MID', 'LOD0', 'LOD1')]
        for obj in meshes:
            obj.data.materials.append(material)
            obj['unreal_lod_asset'] = base
        for obj in meshes[1:]:
            obj['polygroups_lod_source'] = meshes[0].name
        label = bpy.data.curves.new('Label', 'FONT')
        label.body = meshes[0].name + ' | LOD 0'
        text = bpy.data.objects.new('Label', label)
        text.parent = meshes[1]
        col.objects.link(text)
        packs.append((col, meshes, text))
    external = cube(ctx.scene.collection, 'Outside')
    external.data.materials.append(material)
    # Linked mesh data must be isolated too.
    external_data = cube(ctx.scene.collection, 'OutsideSharedData')
    external_data.data = packs[0][1][0].data
    original_mesh = external_data.data
    original_data_name = original_mesh.name
    initial = media.template()
    initial['fields']['assetHeadline'] = 'Old'
    initial['fields']['description'] = 'Stylized Old collection with textures'
    gallery.result_text = bpy.data.texts.new('Gallery.json')
    gallery.result_text.write(media.dumps(initial))
    gallery.saved_filepath = str(root / 'gallery.json')
    (root / 'gallery.json').write_text(media.dumps(initial), encoding='utf-8')
    p.phase2_rename_asset = 'New Stone'
    p.phase2_rename_name_index = '03'
    p.phase2_rename_version_index = '05'
    p.phase2_rename_fbx = p.phase2_rename_blend = p.phase2_rename_json = True
    p.phase2_run_engine = 'FAB'
    # Restore scene visibility, selection and active object after exports.
    bpy.ops.object.select_all(action='DESELECT')
    external.select_set(True)
    ctx.view_layer.objects.active = external
    layer = ctx.view_layer.layer_collection.children[packs[1][0].name]
    layer.exclude = True
    result = bpy.ops.object.polygroups_rename_final_meshes()
    assert result == {'FINISHED'}, p.phase2_rename_status
    assert 'follow-up' not in p.phase2_rename_status, p.phase2_rename_status
    assert layer.exclude
    assert ctx.active_object == external and set(ctx.selected_objects) == {external}
    assert external.data.materials[0] == material and image.name == 'Old_BaseColor'
    assert image.filepath_raw == str(root / 'Old_BaseColor.png')
    assert (root / 'Old_BaseColor.png').read_bytes() == old_bytes
    assert external_data.data == original_mesh and original_mesh.name == original_data_name
    for offset, (col, meshes, label) in enumerate(packs):
        base = f'New_Stone_03_{5+offset:02}'
        assert col.name == base + '_Collection'
        assert [o.name for o in meshes] == ['SM_' + base + '_' + suffix for suffix in ('MID', 'LOD0', 'LOD1')]
        assert all(o.data.name == o.name for o in meshes)
        assert all(o['unreal_lod_asset'] == base for o in meshes)
        assert meshes[1]['polygroups_lod_source'] == meshes[0].name
        assert base in label.data.body and 'Old_' not in label.data.body
        mats = {o.data.materials[0] for o in meshes}
        assert len(mats) == 1
        mat = mats.pop()
        assert mat.name == 'M_' + base and mat != material
        img = next(rename.image_nodes(mat.node_tree)).image
        assert img.name == 'T_' + base + '_BaseColor'
        path = Path(bpy.path.abspath(img.filepath_raw))
        assert path.parent == root / 'Textures' / base and path.read_bytes() == old_bytes
        assert img.filepath_raw.startswith('//')
        assert (root / '!Blend' / (base + '.blend')).is_file()
    exported = list((root / '!Unreal').rglob('*.fbx'))
    assert len(exported) == 6 and all('New_Stone' in file.name for file in exported)
    info = json.loads((root / '!Unreal/MeshInfo.json').read_text(encoding='utf-8'))
    assert len(info['meshes']) == 6 and all('New_Stone' in item['name'] for item in info['meshes'])
    document = json.loads((root / 'gallery.json').read_text(encoding='utf-8'))
    assert document['fields']['fileNameMID01'] == 'SM_New_Stone_03_05_MID.fbx'
    assert document['fields']['fileNameLOW02'] == 'SM_New_Stone_03_06_LOD0.fbx'
    assert document['fields']['assetsQuantityLine2'] == '4 STATIC MESHES'
    assert document['fields']['assetHeadline'] == 'New Stone'
    assert 'Old' not in document['fields']['description']
    # Same identity is safe and can be reexported repeatedly.
    assert bpy.ops.object.polygroups_rename_final_meshes() == {'FINISHED'}
    assert 'follow-up' not in p.phase2_rename_status, p.phase2_rename_status
    # Names and textures are restored if filesystem installation fails mid-rename.
    p.phase2_rename_asset = 'Rollback'
    before_names = [col.name for col, _, _ in packs]
    old_install = rename.RenameTransaction.install
    installed = []
    def fail_install(tx, staged, destination):
        if installed:
            raise OSError('Simulated texture write failure')
        old_install(tx, staged, destination)
        installed.append(destination)
    with patch.object(rename.RenameTransaction, 'install', fail_install):
        assert bpy.ops.object.polygroups_rename_final_meshes() == {'CANCELLED'}
    assert [col.name for col, _, _ in packs] == before_names
    assert not any(path.exists() for path in installed)
    assert all(obj.name.startswith('SM_New_Stone') for _, meshes, _ in packs for obj in meshes)
    assert all(next(rename.image_nodes(meshes[0].data.materials[0].node_tree)).image.name.startswith('T_New_Stone') for _, meshes, _ in packs)
    # A failure after ID names have started changing restores them too.
    original_rename = rename.RenameTransaction.rename
    renamed_ids = []
    def fail_names(tx, obj, name):
        if len(renamed_ids) == 2:
            raise ValueError('Simulated datablock rename failure')
        original_rename(tx, obj, name)
        renamed_ids.append(obj)
    with patch.object(rename.RenameTransaction, 'rename', fail_names):
        assert bpy.ops.object.polygroups_rename_final_meshes() == {'CANCELLED'}
    assert [col.name for col, _, _ in packs] == before_names
    assert all(obj.data.name == obj.name and obj.name.startswith('SM_New_Stone') for _, meshes, _ in packs for obj in meshes)
    assert not any(image.name.startswith('__FinalRename') for image in bpy.data.images)
    # Preflight prevents unrelated ID collisions before writing files.
    p.phase2_rename_asset = 'Collision'
    conflict = bpy.data.collections.new('Collision_03_05_Collection')
    assert bpy.ops.object.polygroups_rename_final_meshes() == {'CANCELLED'}
    assert [col.name for col, _, _ in packs] == before_names
    bpy.data.collections.remove(conflict)
    # The upper Unity switch controls export parameters and target directory.
    p.phase2_rename_asset = 'UnityTest'
    p.phase2_run_engine = 'UNITY'
    assert bpy.ops.object.polygroups_rename_final_meshes() == {'FINISHED'}
    assert 'follow-up' not in p.phase2_rename_status, p.phase2_rename_status
    unity_info = json.loads((root / '!Unity/MeshInfo.json').read_text(encoding='utf-8'))
    assert unity_info['Engine'] == 'Unity' and len(list((root / '!Unity').rglob('*.fbx'))) == 6
    assert all('UnityTest' in item['name'] for item in unity_info['meshes'])
    # Exported blend libraries contain the renamed collection, not its old identity.
    with bpy.data.libraries.load(str(root / '!Blend/UnityTest_03_05.blend')) as (source, target):
        assert 'UnityTest_03_05_Collection' in source.collections
        assert 'SM_UnityTest_03_05_MID' in source.objects
    # Shift into existing names/paths. All source bytes are staged before swaps.
    second_image = next(rename.image_nodes(packs[1][1][0].data.materials[0].node_tree)).image
    second_image.pixels[0] = .8
    second_image.save()
    expected_textures = [Path(bpy.path.abspath(next(rename.image_nodes(meshes[0].data.materials[0].node_tree)).image.filepath)).read_bytes()
                         for col, meshes, text in packs]
    p.phase2_rename_version_index = '06'
    assert bpy.ops.object.polygroups_rename_final_meshes() == {'FINISHED'}
    assert 'follow-up' not in p.phase2_rename_status, p.phase2_rename_status
    for offset, (col, meshes, text) in enumerate(packs):
        assert col.name == f'UnityTest_03_{6+offset:02}_Collection'
        img = next(rename.image_nodes(meshes[0].data.materials[0].node_tree)).image
        assert Path(bpy.path.abspath(img.filepath)).read_bytes() == expected_textures[offset]
        assert f'UnityTest_03_{6+offset:02}' in text.data.body
    # Object-linked material overrides and generated images also get renamed.
    override = bpy.data.materials.new('ObjectOverride')
    override.use_nodes = True
    generated_image = bpy.data.images.new('Generated_Normal', width=8, height=8)
    override.node_tree.nodes.new('ShaderNodeTexImage').image = generated_image
    packs[0][1][0].material_slots[0].link = 'OBJECT'
    packs[0][1][0].material_slots[0].material = override
    p.phase2_rename_asset = 'OverrideTest'
    p.phase2_rename_fbx = p.phase2_rename_blend = False
    assert bpy.ops.object.polygroups_rename_final_meshes() == {'FINISHED'}
    assert 'follow-up' not in p.phase2_rename_status, p.phase2_rename_status
    assert packs[0][1][0].material_slots[0].link == 'OBJECT'
    assert packs[0][1][0].material_slots[0].material.name.startswith('M_OverrideTest_03_06')
    assert generated_image.name.startswith('T_OverrideTest_03_06')
    assert Path(bpy.path.abspath(generated_image.filepath)).is_file()
    final_info = json.loads((root / '!Unity/MeshInfo.json').read_text(encoding='utf-8'))
    assert all('OverrideTest' in mesh['name'] for mesh in final_info['meshes'])
    assert not list(root.glob('.final-rename-*'))
print('RENAME_FINAL_INTEGRATION_PASSED')
