"""Stage texture files and bind the requested tangent-space normals for Unreal FBX."""
import os
import re
import struct
import tempfile
import zlib
from contextlib import contextmanager
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper

from .fab_preparation import _fab_image_source, _texture_suffix, _write_fab_image_source
from .mesh_export import _copy_export_textures, _safe_path_token


CONVENTION_SUFFIX = re.compile(r'_(OpenGL|DirectX|GL|DX)$', re.I)
MASK_ROLES = {'AlphaMap', 'MergeMask', 'ArtifactMask'}
FBX_SOCKET_ROLES = {
    'base_color_texture': 'BaseColor', 'alpha_texture': 'Opacity',
    'emission_strength_texture': 'Emissive', 'emission_color_texture': 'Emissive',
    'normalmap_texture': 'Normal', 'specular_texture': 'Specular',
    'roughness_texture': 'Roughness', 'metallic_texture': 'Metallic',
}


def _bindings(obj):
    for slot, material in enumerate(obj.data.materials):
        if not material or not material.use_nodes:
            continue
        shader = PrincipledBSDFWrapper(material, is_readonly=True)
        fbx_roles = {}
        for socket, role in FBX_SOCKET_ROLES.items():
            texture = getattr(shader, socket)
            if texture is not None and texture.node_image is not None:
                fbx_roles[texture.node_image] = role
        trees = [material.node_tree]
        seen = set()
        while trees:
            tree = trees.pop()
            if tree in seen:
                continue
            seen.add(tree)
            for node in tree.nodes:
                if node.type == 'GROUP' and node.node_tree:
                    trees.append(node.node_tree)
                elif node.type == 'TEX_IMAGE' and node.image:
                    role = _texture_suffix(node.image, node)
                    if role in MASK_ROLES:
                        continue
                    normal_nodes = [link.to_node for link in node.outputs['Color'].links
                                    if link.to_node.type == 'NORMAL_MAP']
                    if any(target.space != 'TANGENT' for target in normal_nodes):
                        raise ValueError(f'Unreal FBX requires tangent-space normals: {node.image.name}')
                    role = 'Normal' if normal_nodes else fbx_roles.get(node, role)
                    yield slot, material.name, role, node.image, node, node in fbx_roles


def _source_convention(image):
    for name in (Path(image.filepath).stem, image.name):
        match = CONVENTION_SUFFIX.search(name)
        if match:
            return 'DirectX' if match[1].lower() in {'directx', 'dx'} else 'OpenGL'
    return 'OpenGL'


def _normal_paths(image, source, folder, conventions):
    name = image.name
    if Path(name).suffix.lower() == source[2]:
        name = Path(name).stem
    stem = CONVENTION_SUFFIX.sub('', _safe_path_token(name))
    convention = _source_convention(image)
    return {target: Path(folder) / 'Textures' /
            (f'{stem}_{target}' + (source[2] if target == convention else '.png'))
            for target in sorted(conventions)}


def _fbx_conventions(mode):
    preferred = 'OpenGL' if mode == 'OPENGL' else 'DirectX'
    return preferred, ('OpenGL', 'DirectX') if mode == 'BOTH' else (preferred,)


def _manifest(bindings, paths, common, normal_mode):
    preferred, conventions = _fbx_conventions(normal_mode)
    rows = []
    references = {}
    for slot, material, role, image, _, connected in bindings:
        key = (slot, material, role, image)
        references[key] = references.get(key, False) or connected
    for (slot, material, role, image), connected in references.items():
        entry = dict(material_slot=slot, material=material, role=role)
        if role == 'Normal' and image in paths:
            for convention in conventions:
                path = paths[image][convention]
                if path.is_file():
                    rows.append(dict(entry, role='Normal', path=str(path), convention=convention,
                        preferred=convention == preferred,
                        fbx_reference=connected and convention == preferred,
                        unreal=dict(srgb=False, compression_settings='TC_NORMALMAP',
                                    flip_green_channel=convention == 'OpenGL')))
        elif image in common and common[image].is_file():
            rows.append(dict(entry, path=str(common[image]), fbx_reference=connected))
    return rows


def exported_fbx_texture_manifest(obj, folder, normal_mode):
    """Recover the binding list for the aggregate JSON after a successful ReLOD export."""
    bindings = list(_bindings(obj))
    normals = {image for _, _, role, image, _, _ in bindings if role == 'Normal'}
    _, conventions = _fbx_conventions(normal_mode)
    paths, common = {}, {}
    for image in dict.fromkeys(row[3] for row in bindings):
        source = _fab_image_source(image)
        if source is None:
            continue
        if image in normals:
            paths[image] = _normal_paths(image, source, folder, conventions)
        common[image] = Path(folder) / 'Textures' / (_safe_path_token(image.name) + source[2])
    return _manifest(bindings, paths, common, normal_mode)


def _write_normal_png(path, pixels, width, height):
    # PNG rows start at the top. Write raw 16-bit samples so the render
    # pipeline cannot apply a display transform or unpremultiply RGB.
    def chunk(stream, kind, data):
        stream.write(struct.pack('>I', len(data)))
        stream.write(kind)
        stream.write(data)
        stream.write(struct.pack('>I', zlib.crc32(data, zlib.crc32(kind))))

    compressor = zlib.compressobj()
    with path.open('wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')
        chunk(stream, b'IHDR', struct.pack('>IIBBBBB', width, height, 16, 6, 0, 0, 0))
        for row in pixels.reshape(height, width, 4)[::-1]:
            samples = np.rint(np.clip(row, 0., 1.) * 65535.).astype('>u2')
            data = compressor.compress(b'\0' + samples.tobytes())
            if data:
                chunk(stream, b'IDAT', data)
        chunk(stream, b'IDAT', compressor.flush())
        chunk(stream, b'IEND', b'')


def _write_flipped_green(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.normal-export-', dir=destination.parent) as folder:
        source_path = Path(folder) / ('source' + source[2])
        _write_fab_image_source(source, str(source_path))
        image = bpy.data.images.load(str(source_path), check_existing=False)
        try:
            image.colorspace_settings.name = 'Non-Color'
            image.alpha_mode = 'CHANNEL_PACKED'
            width, height = image.size
            length = len(image.pixels)
            if not width or not height or length != width * height * 4:
                raise ValueError(f'Cannot read normal map: {destination.name}')
            pixels = np.empty(length, dtype=np.float32)
            image.pixels.foreach_get(pixels)
            pixels[1::4] = 1.0 - pixels[1::4]
            staged = Path(folder) / 'normal.png'
            _write_normal_png(staged, pixels, width, height)
            os.replace(staged, destination)
        finally:
            bpy.data.images.remove(image)


@contextmanager
def export_texture_scope(objects, folder, formats, normal_mode=None):
    """Share staged files across a scope and restore image paths on every exit."""
    bindings = {obj: list(dict.fromkeys(_bindings(obj))) for obj in objects} if normal_mode and 'FBX' in formats else {}
    nodes = {node: image for rows in bindings.values() for _, _, role, image, node, _ in rows if role == 'Normal'}
    normals = set(nodes.values())
    other_images = {image for rows in bindings.values() for _, _, role, image, _, _ in rows if role != 'Normal'}
    preferred, fbx_variants = _fbx_conventions(normal_mode)
    conventions = set(fbx_variants)
    if any(format != 'FBX' for format in formats):
        conventions.add('OpenGL')
    specifications = {}
    for image in sorted(normals, key=lambda item: item.name):
        source = _fab_image_source(image)
        if image.source != 'FILE' or source is None:
            raise ValueError(f'Save the normal map before exporting FBX: {image.name}')
        specifications[image] = (source, _source_convention(image), _normal_paths(image, source, folder, conventions))
    originals = _copy_export_textures(objects, str(folder), skip_images=normals - other_images)
    common = {image: Path(image.filepath) for image in originals}
    paths = {}
    export_images = {}
    try:
        reserved = {Path(image.filepath).resolve().as_posix().casefold() for image in originals}
        for image, (source, convention, variants) in specifications.items():
            for target, destination in variants.items():
                key = destination.resolve().as_posix().casefold()
                if key in reserved:
                    raise ValueError(f'Duplicate normal export filename: {destination.name}')
                reserved.add(key)
                if target == convention:
                    _write_fab_image_source(source, str(destination))
                else:
                    _write_flipped_green(source, destination)
            paths[image] = variants

        def bind(format):
            convention = preferred if format == 'FBX' else 'OpenGL'
            for node, image in nodes.items():
                key = (image, convention)
                if key not in export_images:
                    copy = bpy.data.images.load(str(paths[image][convention]), check_existing=False)
                    export_images[key] = copy
                    copy.colorspace_settings.name = 'Non-Color'
                node.image = export_images[key]

        def manifest(obj):
            return _manifest(bindings.get(obj, ()), paths, common, normal_mode)

        yield bind, manifest
    finally:
        for node, image in nodes.items():
            if node.image != image:
                node.image = image
        for image in export_images.values():
            bpy.data.images.remove(image)
        for image, (filepath, raw) in originals.items():
            image.filepath = filepath
            image.filepath_raw = raw
