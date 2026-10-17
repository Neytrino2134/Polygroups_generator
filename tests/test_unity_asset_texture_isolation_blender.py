"""Reused asset indices must prepare fresh source textures, not stale materials."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import unity_preparation as up

def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    image = bpy.data.images.new(name + '_BaseColor', width=4, height=4)
    image.pixels[:] = list(color) * 16
    node = mat.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    mat.node_tree.links.new(node.outputs['Color'], mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    return mat, image

with TemporaryDirectory() as temp:
    root = Path(temp)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    s = bpy.context.scene.polygroups_mesh_finalization_settings
    s.unity_export_directory = str(root / 'Unity')
    s.unity_export_fbx = s.unity_export_gltf = True
    s.unity_export_all_renders = False
    s.unity_export_clear_asset_folder = True
    s.unity_auto_increment_index = False
    s.unity_generate_text_labels = False
    s.unity_copy_textures = True
    old_mat, old_image = material('Asset_19_01', (0, 0, 1, 1))
    old_mat['unity_asset_name'] = 'Asset_19_01'
    old_obj = bpy.data.objects['Cube']
    old_obj.name = 'Asset_19_01'
    old_obj.data.materials.clear()
    old_obj.data.materials.append(old_mat)
    stale_mat, stale_image = material('Stale02', (1, 0, 0, 1))
    stale_mat['unity_asset_name'] = 'Asset_19_02'
    incoming_mat, incoming_image = material('Incoming', (0, 1, 0, 1))
    folder = root / 'Unity' / 'Asset_19_02'
    folder.mkdir(parents=True)
    marker = folder / 'stale_render.txt'
    marker.write_text('old render')
    incoming_image.file_format = 'PNG'
    incoming_image.save(filepath=str(folder / 'incoming.png'))
    # Source pixels may themselves be stored in the directory being cleared.
    loaded = bpy.data.images.load(str(folder / 'incoming.png'), check_existing=False)
    next(up.texture_nodes(incoming_mat.node_tree)).image = loaded
    sibling = root / 'Unity' / 'Asset_19_01'
    sibling.mkdir()
    (sibling / 'keep.txt').write_text('preserve')
    meshes = []
    for segments in (12, 8):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=6)
        obj = bpy.context.object
        obj.data.materials.append(incoming_mat)
        meshes.append(obj)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    original = up.prepare_unity
    def checked(*args, **kwargs):
        assert not marker.exists(), 'Cleanup must precede Prepare'
        return original(*args, **kwargs)
    with patch.object(up, 'prepare_unity', side_effect=checked):
        assert bpy.ops.object.polygroups_prepare_and_export_unity(
            asset_name='Asset', name_index='19', version_index='02', skip_lods=True,
        ) == {'FINISHED'}
    prepared = meshes[0].active_material
    assert prepared != stale_mat and prepared != old_mat
    assert meshes[1].active_material == prepared
    image = next(up.texture_nodes(prepared.node_tree)).image
    assert image.pixels[1] > .9 and image.pixels[0] < .1
    texture = next((folder / 'FBX').glob('*.png'))
    exported = bpy.data.images.load(str(texture), check_existing=False)
    assert exported.pixels[1] > .9 and exported.pixels[0] < .1
    assert old_obj.active_material == old_mat
    assert old_image.pixels[2] > .9 and old_image.pixels[1] < .1
    assert stale_image.pixels[0] > .9
    assert (sibling / 'keep.txt').read_text() == 'preserve'
    assert not marker.exists()
    assert list(folder.rglob('*.fbx')) and list(folder.rglob('*.gltf'))
    # Same-index reexport stages even disconnected material images and keeps
    # existing mesh/material/image datablocks, regardless of Auto Increment.
    extra = bpy.data.images.new('UnconnectedDetail', width=4, height=4)
    extra.pixels[:] = [.2, .4, .6, 1] * 16
    node = prepared.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = extra
    texture_folder = root / 'Textures' / 'Asset_19_02'
    (texture_folder / 'obsolete.png').write_bytes(b'obsolete')
    marker.write_text('old render')
    image.filepath_raw = str(texture)  # Source can point inside the export being deleted.
    before = tuple(set(ids) for ids in (bpy.data.objects, bpy.data.materials, bpy.data.images))
    s.unity_auto_increment_index = True
    assert bpy.ops.object.polygroups_prepare_and_export_unity(
        asset_name='Asset', name_index='19', version_index='02', skip_lods=False,
    ) == {'FINISHED'}
    assert tuple(set(ids) for ids in (bpy.data.objects, bpy.data.materials, bpy.data.images)) == before
    assert s.unity_asset_index == '02'
    assert not (texture_folder / 'obsolete.png').exists() and not marker.exists()
    assert Path(extra.filepath_raw).parent == texture_folder
    assert Path(extra.filepath_raw).is_file()
    assert extra.pixels[2] > .5
    s.unity_auto_increment_index = False
    # A restore failure must recover both old directories before returning.
    from polygroups_generator.operators import unity_reexport
    texture_marker = texture_folder / 'recovery.txt'
    texture_marker.write_text('source survives')
    marker.write_text('export survives')
    original_copy = unity_reexport.shutil.copy2
    def fail_restore(source, destination, *args, **kwargs):
        if Path(destination).parent == texture_folder:
            raise OSError('Injected texture restore failure')
        return original_copy(source, destination, *args, **kwargs)
    with patch.object(unity_reexport.shutil, 'copy2', side_effect=fail_restore):
        try:
            unity_reexport.refresh_asset_textures(meshes, 'Asset_19_02', root / 'Unity')
        except OSError:
            pass
        else:
            raise AssertionError('Expected restore failure')
    assert texture_marker.read_text() == 'source survives'
    assert marker.read_text() == 'export survives'
    # Reusing the same index must refresh the material even without directory cleanup.
    s.unity_export_clear_asset_folder = False
    s.unity_export_overwrite = True
    marker.write_text('keep when cleanup disabled')
    replacement, _ = material('Replacement', (1, 1, 0, 1))
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(replacement)
    assert bpy.ops.object.polygroups_prepare_and_export_unity(
        asset_name='Asset', name_index='19', version_index='02', skip_lods=True,
    ) == {'FINISHED'}
    assert meshes[0].active_material != prepared
    refreshed = next(up.texture_nodes(meshes[0].active_material.node_tree)).image
    assert refreshed.pixels[0] > .9 and refreshed.pixels[1] > .9
    assert marker.is_file()
    assert old_obj.active_material == old_mat
    bpy.ops.wm.open_mainfile(filepath=str(root / 'Working.blend'))
    reopened = bpy.data.objects['Asset_19_02']
    reopened_image = next(up.texture_nodes(reopened.active_material.node_tree)).image
    assert reopened_image.pixels[0] > .9 and reopened_image.pixels[1] > .9
print('UNITY_ASSET_TEXTURE_ISOLATION_PASSED')
