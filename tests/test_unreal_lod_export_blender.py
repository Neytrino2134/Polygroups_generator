"""Real Unreal LOD FBX/GLB/GLTF output, High separation and versioned JSON."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import struct
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator import ui

s = bpy.context.scene.polygroups_mesh_finalization_settings
s.mesh_export_sort = 'LODS'
s.mesh_export_fbx = s.mesh_export_glb = s.mesh_export_gltf = True
s.mesh_export_info_format = 'JSON'
assert s.unreal_glb_mode == 'COMBINED'
meshes = []
with TemporaryDirectory() as temp:
    root = Path(temp)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'LODExport.blend'))
    image = bpy.data.images.new('Shared_BaseColor', width=4, height=4)
    image.pixels[:] = [.2, .6, .9, 1] * 16
    image.file_format = 'PNG'
    image.save(filepath=str(root / 'Shared.png'))
    image.filepath_raw = str(root / 'Shared.png')
    image.source = 'FILE'
    original_path = image.filepath_raw
    mat = bpy.data.materials.new('LODMaterial')
    mat.use_nodes = True
    node = mat.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    shader = mat.node_tree.nodes.get('Principled BSDF')
    mat.node_tree.links.new(node.outputs['Color'], shader.inputs['Base Color'])
    mask = bpy.data.images.new('Tree_ArtifactMask', width=4, height=4)
    mask_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
    mask_node.image = mask
    mat.node_tree.links.new(mask_node.outputs['Color'], shader.inputs['Alpha'])
    for number in (1, 2):
        base = f'Tree_19_{number:02d}'
        for index in (-1, 0, 1):
            bpy.ops.mesh.primitive_cube_add(location=(number * 4, index * 3, 1))
            obj = bpy.context.object
            obj.name = f'SM_{base}_' + ('Original' if index == -1 else f'LOD{index}')
            obj['unreal_lod_asset'] = base
            obj['unreal_lod_index'] = index
            obj.data.materials.append(mat)
            meshes.append(obj)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    matrices = {obj: obj.matrix_world.copy() for obj in meshes}
    assert bpy.ops.object.polygroups_export_selected_meshes() == {'FINISHED'}
    output = root / '!Unreal'
    report = json.loads((output / 'MeshInfo.json').read_text())
    assert report['schema_version'] == 2 and len(report['assets']) == 2
    assert report['Engine'] == 'Unreal'
    assert report['totals'] == dict(meshes=6, vertices=48, triangles=72)
    for number in (1, 2):
        base = f'Tree_19_{number:02d}'
        combined = json.loads((output / base / 'GLTF' / (base + '.gltf')).read_text())
        assert len(combined['nodes']) == 2
        assert all('LOD' in entry['name'] for entry in combined['nodes'])
        assert all('ArtifactMask' not in entry.get('name', '') for entry in combined.get('images', []))
        glb = (output / base / 'GLB' / (base + '.glb')).read_bytes()
        assert glb[:4] == b'glTF'
        length, kind = struct.unpack_from('<II', glb, 12)
        assert kind == 0x4e4f534a
        packed = json.loads(glb[20:20 + length])
        assert len(packed['nodes']) == 2
        assert all('LOD' in item['name'] for item in packed['nodes'])
        assert all('uri' not in item for item in packed.get('images', []))
        assert all('uri' not in item for item in packed.get('buffers', []))
        assert (output / base / 'GLB' / f'SM_{base}_Original.glb').is_file()
        assert (output / base / 'GLTF' / (f'SM_{base}_Original.gltf')).is_file()
        entries = [item for item in report['meshes'] if item['asset'] == base]
        assert {item['lod'] for item in entries} == {'HIGH', 'LOD0', 'LOD1'}
        assert all(set(item['files']) == {'FBX', 'GLB', 'GLTF'} for item in entries)
        assert all((output / path).is_file() for item in entries for path in item['files'].values())
        lods = [item for item in entries if item['role'] == 'LOD']
        assert lods[0]['files']['GLTF'] == lods[1]['files']['GLTF']
        assert lods[0]['files']['GLB'] == lods[1]['files']['GLB']
        local = json.loads((output / base / 'MeshInfo.json').read_text())
        assert local['Engine'] == 'Unreal'
        assert all((output / base / path).is_file() for item in local['meshes'] for path in item['files'].values())
    assert all(obj.matrix_world == matrices[obj] for obj in meshes)
    assert set(bpy.context.selected_objects) == set(meshes)
    assert image.filepath_raw == original_path and mask_node.image == mask
    assert shader.inputs['Alpha'].is_linked
    output.rename(root / 'CombinedOutputs')
    s.unreal_gltf_mode = 'SHARED'
    s.unreal_glb_mode = 'SEPARATE'
    s.mesh_export_fbx = False
    assert bpy.ops.object.polygroups_export_selected_meshes() == {'FINISHED'}
    uris = []
    for index in (0, 1):
        path = output / 'Tree_19_01' / 'GLTF' / f'SM_Tree_19_01_LOD{index}.gltf'
        document = json.loads(path.read_text())
        assert len(document['nodes']) == 1
        glb_path = output / 'Tree_19_01' / 'GLB' / f'SM_Tree_19_01_LOD{index}.glb'
        raw = glb_path.read_bytes()
        length = struct.unpack_from('<I', raw, 12)[0]
        assert len(json.loads(raw[20:20 + length])['nodes']) == 1
        uri = document['images'][0]['uri']
        assert uri.startswith('Textures/') and (path.parent / uri).is_file()
        uris.append(uri)
    assert uris[0] == uris[1]
    report = json.loads((output / 'MeshInfo.json').read_text())
    assert report['totals']['meshes'] == 6
    assert all(set(item['files']) == {'GLTF', 'GLB'} for item in report['meshes'])
    model = capture(bpy.context, ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_mesh_finalization))
    assert not model.errors, model.errors
    for name in ('mesh_export_fbx', 'mesh_export_glb', 'mesh_export_gltf', 'unreal_gltf_mode', 'unreal_glb_mode'):
        assert any(b[0] == 'property' and b[2] == name for b in model.bindings.values())
    from polygroups_generator.operators import unreal_lod_export
    with patch.object(unreal_lod_export, '_export_gltf_asset', side_effect=RuntimeError('Injected GLTF failure')):
        assert unreal_lod_export.export_lods(bpy.context, s, lambda *args: None) == {'CANCELLED'}
    assert all(obj.matrix_world == matrices[obj] for obj in meshes)
    assert set(bpy.context.selected_objects) == set(meshes)
    assert image.filepath_raw == original_path and mask_node.image == mask
    assert shader.inputs['Alpha'].is_linked
    # Legacy HIGH/MID/LOW supports multiple format switches too.
    bpy.ops.object.select_all(action='DESELECT')
    legacy = []
    for role in ('HIGH', 'MID', 'LOW'):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        obj.name = f'SM_Legacy_01_{role}'
        legacy.append(obj)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in legacy:
        obj.select_set(True)
    s.mesh_export_sort = 'VARIANT'
    s.mesh_export_fbx = True
    s.mesh_export_glb = False
    assert bpy.ops.object.polygroups_export_selected_meshes() == {'FINISHED'}
    legacy_info = json.loads((output / 'MeshInfo.json').read_text())
    assert legacy_info['Engine'] == 'Unreal'
    assert legacy_info['totals']['meshes'] == 3
    assert all(set(item['files']) == {'FBX', 'GLTF'} for item in legacy_info['meshes'])
    s.mesh_export_fbx = s.mesh_export_gltf = False
    try:
        result = bpy.ops.object.polygroups_export_selected_meshes()
    except RuntimeError as error:
        assert 'Enable at least one' in str(error)
    else:
        assert result == {'CANCELLED'}
print('UNREAL_LOD_EXPORT_PASSED')
