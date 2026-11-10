"""Verify FBX references, normal pixels and per-mesh import metadata."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.unreal_export_textures import export_texture_scope
settings = bpy.context.scene.polygroups_mesh_finalization_settings
settings.mesh_export_fbx = True
settings.mesh_export_glb = settings.mesh_export_gltf = False
settings.mesh_export_info_format = 'JSON'
mesh = bpy.context.object
material = bpy.data.materials.new('Rock')
material.use_nodes = True
mesh.data.materials.clear()
mesh.data.materials.append(material)
tree = material.node_tree
bsdf = tree.nodes.get('Principled BSDF')


def pixel(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = 'Non-Color'
        image.alpha_mode = 'CHANNEL_PACKED'
        return tuple(image.pixels[:4])
    finally:
        bpy.data.images.remove(image)


with TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / 'Rock_Normal.png'
    image = bpy.data.images.new('Rock_Normal', width=4, height=4, alpha=True)
    image.colorspace_settings.name = 'Non-Color'
    image.alpha_mode = 'CHANNEL_PACKED'
    image.pixels[:] = [.2, .3, .9, .65] * 16
    image.filepath_raw = str(source)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    image = bpy.data.images.load(str(source), check_existing=False)
    image.colorspace_settings.name = 'Non-Color'
    normal = tree.nodes.new('ShaderNodeNormalMap')
    node = tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    tree.links.new(node.outputs['Color'], normal.inputs['Color'])
    tree.links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    base = tree.nodes.new('ShaderNodeTexImage')
    base.image = bpy.data.images.load(str(source), check_existing=False)
    base.image.name = 'Rock_BaseColor'
    tree.links.new(base.outputs['Color'], bsdf.inputs['Base Color'])
    before = source.read_bytes()
    original_pixel = pixel(source)
    for mode, sort, suffix, conventions in (
        ('OPENGL', 'VARIANT', 'MID', {'OpenGL'}),
        ('DIRECTX', 'LODS_FORMAT', 'LOD0', {'DirectX'}),
        ('BOTH', 'LODS', 'LOD0', {'OpenGL', 'DirectX'}),
    ):
        mesh.name = 'SM_Rock_01_01_' + suffix
        settings.mesh_export_sort = sort
        settings.unreal_fbx_normal_maps = mode
        folder = root / mode
        folder.mkdir()
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'Scene.blend'))
        original_paths = image.filepath, image.filepath_raw
        assert bpy.ops.object.polygroups_export_selected_meshes() == {'FINISHED'}
        output = folder / '!Unreal'
        info = json.loads((output / 'MeshInfo.json').read_text())
        record = info['meshes'][0]
        textures = [texture for texture in record['textures'] if texture['role'] == 'Normal']
        color, = [texture for texture in record['textures'] if texture['role'] == 'BaseColor']
        assert color['fbx_reference'] and (output / color['path']).is_file()
        assert {texture['convention'] for texture in textures} == conventions
        preferred = 'OpenGL' if mode == 'OPENGL' else 'DirectX'
        fbx = (output / record['files']['FBX']).read_bytes()
        for texture in textures:
            convention = texture['convention']
            path = output / texture['path']
            assert path.stem.endswith('_' + convention)
            assert texture['fbx_reference'] == (convention == preferred)
            assert (path.name.encode() in fbx) == (convention == preferred)
            assert texture['unreal']['flip_green_channel'] == (convention == 'OpenGL')
            assert texture['material_slot'] == 0 and texture['material'] == material.name
            rgba = pixel(path)
            expected = list(original_pixel)
            if convention == 'DirectX':
                assert path.read_bytes()[24] == 8  # PNG IHDR bit depth per channel.
                expected[1] = 1.0 - expected[1]
            assert max(abs(a - b) for a, b in zip(rgba, expected)) < .005, (rgba, expected)
        for local_info in output.rglob('MeshInfo*.json'):
            document = json.loads(local_info.read_text())
            for item in document['meshes']:
                assert all((local_info.parent / texture['path']).is_file() for texture in item['textures'])
            if document.get('Format') == 'FBX':
                surface = document['fab_technical_details']['materials_and_textures']
                assert surface['normal_map_orientation'] == preferred
                assert surface['texture_dimensions'] == [[4, 4]]
                assert surface['textures'] == 2  # Count the bound normal, not the alternate file.
        assert (image.filepath, image.filepath_raw) == original_paths
        assert node.image == image and source.read_bytes() == before

    directx = output / next(texture['path'] for texture in textures if texture['preferred'])
    tagged = bpy.data.images.load(str(directx), check_existing=False)
    node.image = tagged
    with export_texture_scope([mesh], root / 'Mixed', ['FBX', 'GLB'], 'BOTH') as (bind, manifest):
        bind('FBX')
        assert Path(node.image.filepath).read_bytes() == directx.read_bytes()
        bind('GLB')
        assert node.image != tagged and node.image.colorspace_settings.name == 'Non-Color'
        assert max(abs(a - b) for a, b in zip(pixel(node.image.filepath), original_pixel)) < .005
    assert node.image == tagged and Path(tagged.filepath) == directx
print('UNREAL_NORMAL_EXPORT_PIXELS_FBX_AND_MANIFEST_OK')
