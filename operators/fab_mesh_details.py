"""Measurements for the Technical Details section of a Fab listing."""
import json
import re
import struct
from base64 import b64decode
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

import numpy as np


def collect_mesh_details(obj, depsgraph, unit_scale):
    from .mesh_export import _export_texture_images

    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        counts = [len(poly.vertices) for poly in mesh.polygons]
        dimensions = [0., 0., 0.]
        if mesh.vertices:
            coordinates = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get('co', coordinates)
            matrix = np.asarray(evaluated.matrix_world.to_3x3())
            points = coordinates.reshape(-1, 3) @ matrix.T
            dimensions = ((points.max(axis=0) - points.min(axis=0)) * unit_scale).tolist()
        used_slots = {poly.material_index for poly in mesh.polygons}
        materials = [slot.material.name for index, slot in enumerate(evaluated.material_slots)
                     if index in used_slots and slot.material]
        details = dict(
            triangles=counts.count(3), quads=counts.count(4),
            polygons=sum(count > 4 for count in counts), dimensions=dimensions,
            materials=materials, uv_channels=len(mesh.uv_layers),
            vertex_colors=bool(mesh.color_attributes),
            shape_keys=bool(obj.data.shape_keys and len(obj.data.shape_keys.key_blocks) > 1),
        )
        vertices, triangles = len(mesh.vertices), sum(max(0, count - 2) for count in counts)
    finally:
        evaluated.to_mesh_clear()
    details['image_sizes'] = {image.name: list(image.size) for image in _export_texture_images([obj])}
    return vertices, triangles, details


def _gltf_document(path):
    if path.suffix.lower() == '.gltf':
        with path.open(encoding='utf-8') as stream:
            return json.load(stream), None
    with path.open('rb') as stream:
        header = stream.read(20)
        if len(header) != 20:
            raise ValueError(f'Incomplete GLB header: {path.name}')
        magic, version, _, length, kind = struct.unpack('<4sIII4s', header)
        if magic != b'glTF' or version != 2 or kind != b'JSON':
            raise ValueError(f'Invalid GLB header: {path.name}')
        return json.loads(stream.read(length)), 28 + length


def _png_size(path, document, image, binary_offset):
    """Read the PNG header from a data URI, external file or GLB buffer."""
    uri = image.get('uri')
    try:
        if uri and uri.startswith('data:'):
            header = b64decode(uri.split(',', 1)[1][:32])
        elif uri:
            with (path.parent / unquote(uri)).open('rb') as stream:
                header = stream.read(24)
        elif binary_offset is not None and 'bufferView' in image:
            view = document['bufferViews'][image['bufferView']]
            with path.open('rb') as stream:
                stream.seek(binary_offset + view.get('byteOffset', 0))
                header = stream.read(min(24, view['byteLength']))
        else:
            return None
    except (OSError, ValueError):
        return None
    if len(header) == 24 and header.startswith(b'\x89PNG\r\n\x1a\n') and header[12:16] == b'IHDR':
        return list(struct.unpack('>II', header[16:24]))
    return None


def _material_texture_indices(material):
    """Visit standard and extension material texture slots."""
    for key, value in material.items():
        if not isinstance(value, dict):
            continue
        if key.endswith('Texture') and 'index' in value:
            yield value['index']
        else:
            yield from _material_texture_indices(value)


def _gltf_measurements(folder, entries):
    """Read exported mesh streams and actual animation channels once per file."""
    groups = defaultdict(list)
    for row in entries:
        groups[row['file']].append(row)
    measurements = {}
    animation_tracks = 0
    animation_paths = set()
    rigged = solid = skins = False
    for relative, rows in groups.items():
        path = folder / relative
        document, binary_offset = _gltf_document(path)
        accessors = document.get('accessors', [])
        materials = document.get('materials', [])
        textures = document.get('textures', [])
        images = document.get('images', [])
        nodes = {node.get('name'): node for node in document.get('nodes', []) if 'mesh' in node}
        animations = document.get('animations', [])
        animation_tracks += len(animations)
        paths = {channel.get('target', {}).get('path') for animation in animations
                 for channel in animation.get('channels', [])}
        animation_paths.update(paths)
        skin_nodes = {joint for skin in document.get('skins', []) for joint in skin.get('joints', [])}
        skins |= bool(skin_nodes)
        rigged |= any(channel.get('target', {}).get('node') in skin_nodes
                      for animation in animations for channel in animation.get('channels', []))
        solid |= any(channel.get('target', {}).get('node') not in skin_nodes
                     and channel.get('target', {}).get('path') in {'translation', 'rotation', 'scale'}
                     for animation in animations for channel in animation.get('channels', []))
        exported_sizes = {}
        for row in rows:
            node = nodes.get(row['name'])
            if node is None:
                continue
            primitives = document['meshes'][node['mesh']]['primitives']
            position_ids = {primitive['attributes']['POSITION'] for primitive in primitives}
            triangle_count = 0
            uv_count = 0
            material_ids = set()
            vertex_colors = False
            morphs = False
            for primitive in primitives:
                attributes = primitive['attributes']
                count = accessors[primitive.get('indices', attributes['POSITION'])]['count']
                mode = primitive.get('mode', 4)
                if mode == 4:
                    triangle_count += count // 3
                elif mode in (5, 6):
                    triangle_count += max(0, count - 2)
                uv_count = max(uv_count, sum(key.startswith('TEXCOORD_') for key in attributes))
                vertex_colors |= any(key.startswith('COLOR_') for key in attributes)
                morphs |= bool(primitive.get('targets'))
                if 'material' in primitive:
                    material_ids.add(primitive['material'])
            image_ids = set()
            material_names = set()
            normal = False
            for index in material_ids:
                material = materials[index]
                material_names.add(material.get('name') or (relative, index))
                normal |= 'normalTexture' in material
                for texture_index in _material_texture_indices(material):
                    texture = textures[texture_index]
                    if 'source' in texture:
                        image_ids.add(texture['source'])
                    for extension in texture.get('extensions', {}).values():
                        if 'source' in extension:
                            image_ids.add(extension['source'])
            image_sizes = row['_fab_details']['image_sizes']
            known_sizes = {Path(name).stem: size for name, size in image_sizes.items()}
            texture_sizes = {}
            for index in image_ids:
                image = images[index]
                name = image.get('name')
                key = name or (relative, index)
                if index not in exported_sizes:
                    exported_sizes[index] = _png_size(path, document, image, binary_offset)
                texture_sizes[key] = exported_sizes[index] or image_sizes.get(name) or known_sizes.get(name)
            measurements[row['name']] = dict(
                vertices=sum(accessors[index]['count'] for index in position_ids),
                total_triangles=triangle_count, triangles=triangle_count, quads=0, polygons=0,
                materials=material_names, textures=texture_sizes, uv_channels=uv_count,
                vertex_colors=vertex_colors, morphs=morphs, normal=normal,
            )
    return measurements, animation_tracks, animation_paths, rigged, solid, skins


def technical_details(folder, file_format, entries):
    """Aggregate an individual format, with ranges measured per asset family."""
    gltf = file_format in {'GLB', 'GLTF'}
    actual, tracks, animation_paths, rigged, solid, skins = (
        _gltf_measurements(folder, entries) if gltf else ({}, 0, set(), False, False, False)
    )
    assets = defaultdict(list)
    normal_conventions = set()
    for row in entries:
        source = row['_fab_details']
        metrics = actual.get(row['name'])
        if metrics is None:
            texture_sizes = {texture['path']: texture.get('resolution') for texture in row.get('textures', [])
                             if texture.get('fbx_reference')}
            metrics = dict(vertices=row['vertices'], total_triangles=row['triangles'],
                           triangles=row['triangles'] if gltf else source['triangles'],
                           quads=0 if gltf else source['quads'], polygons=0 if gltf else source['polygons'],
                           materials=source['materials'], textures=texture_sizes, uv_channels=source['uv_channels'],
                           vertex_colors=source['vertex_colors'],
                           morphs=None if source['shape_keys'] else False)
        if metrics.get('normal'):
            normal_conventions.add('OpenGL')
        normal_conventions.update(texture['convention'] for texture in row.get('textures', [])
                                  if texture.get('fbx_reference') and texture.get('convention'))
        name = row['name']
        lod = re.search(r'[._]LOD[._]?(\d+)$', name, re.I)
        base = row.get('asset') or re.sub(r'^SM_', '', re.sub(r'_(MID|HIGH|LOW|LOD\d+)$', '', name, flags=re.I), flags=re.I)
        assets[base].append((metrics, source['dimensions'], int(lod[1]) if lod else row.get('lod_index')))

    per_asset = []
    totals = dict.fromkeys(('total_triangles', 'triangles', 'quads', 'polygons', 'vertices'), 0)
    materials = set()
    textures = {}
    morphs = []
    has_vertex_colors = False
    for rows in assets.values():
        data = {key: sum(metrics[key] for metrics, _, _ in rows) for key in totals}
        for key, value in data.items():
            totals[key] += value
        size = [max(dimensions[axis] for _, dimensions, _ in rows) for axis in range(3)]
        asset_materials = {material for metrics, _, _ in rows for material in metrics['materials']}
        asset_textures = {name: resolution for metrics, _, _ in rows for name, resolution in metrics['textures'].items()}
        known_resolutions = [max(size) for size in asset_textures.values() if size and all(size)]
        materials.update(asset_materials)
        textures.update(asset_textures)
        morphs.extend(metrics['morphs'] for metrics, _, _ in rows)
        has_vertex_colors |= any(metrics['vertex_colors'] for metrics, _, _ in rows)
        data.update(
            bounding_box_size=max(size), bounding_box_size_x=size[0], bounding_box_size_y=size[1],
            bounding_box_size_z=size[2], unique_meshes=len(rows),
            lods=len({level for _, _, level in rows if level is not None}),
            materials=len(asset_materials), textures=len(asset_textures),
            texture_resolution=max(known_resolutions) if len(known_resolutions) == len(asset_textures) and known_resolutions else None,
            uv_channels=max(metrics['uv_channels'] for metrics, _, _ in rows),
        )
        per_asset.append(data)

    texture_data_complete = all(row['name'] in actual or 'textures' in row for row in entries)
    use_range = len(assets) > 1
    collision = file_format == 'FBX' and any(row['name'].upper().startswith(('UCX_', 'UBX_', 'UCP_', 'USP_')) for row in entries)
    geometry = dict(totals, assets=len(assets), pack_of_multiple_assets=use_range, unique_meshes=len(entries),
                    use_range_for_multiple_assets=use_range, bounding_box_unit='m', bounding_box_axes='Blender XYZ',
                    has_collision=collision, collision_type='Custom' if collision else None,
                    counts_source='Exported mesh streams' if len(actual) == len(entries) else 'Evaluated Blender meshes')
    for key in ('lods', 'bounding_box_size', 'bounding_box_size_x', 'bounding_box_size_y', 'bounding_box_size_z'):
        geometry[key] = max(data[key] for data in per_asset)
    geometry['includes_lods'] = geometry['lods'] > 0
    resolutions = {tuple(size) for size in textures.values() if size and all(size)}
    surface = dict(use_range_for_multiple_assets=use_range, materials=len(materials), textures=len(textures),
                   texture_resolution=max(map(max, resolutions)) if resolutions and all(size and all(size) for size in textures.values()) else None,
                   texture_dimensions=[list(size) for size in sorted(resolutions)],
                   custom_shaders=False, normal_map_orientation=next(iter(normal_conventions)) if len(normal_conventions) == 1 else None,
                   normal_map_orientations=sorted(normal_conventions), uv_channels=max(data['uv_channels'] for data in per_asset),
                   clean_uv=None, overlapping_uv=None, udim=False, udim_tiles=0, vertex_colors=has_vertex_colors, scanned=None)
    if not texture_data_complete:
        surface['textures'] = surface['texture_resolution'] = None
    if use_range:
        for section, keys in ((geometry, (*totals, 'unique_meshes', 'lods', 'bounding_box_size',
                                          'bounding_box_size_x', 'bounding_box_size_y', 'bounding_box_size_z')),
                              (surface, ('materials', 'textures', 'texture_resolution', 'uv_channels'))):
            section['ranges'] = {}
            for key in keys:
                if section is surface and key in {'textures', 'texture_resolution'} and not texture_data_complete:
                    continue
                values = [data[key] for data in per_asset]
                if None not in values:
                    section['ranges'][key] = dict(min=min(values), max=max(values))
    animation = dict(animated=tracks > 0, rigged_animation=rigged, animation_tracks=tracks,
                     solid_animation=solid, scale_animation='scale' in animation_paths,
                     morph_animation_blendshapes=True if any(morphs) else None if None in morphs else False,
                     baked_animation=None if tracks else False, ik_bones_included=None if skins else False,
                     characters=None)
    return dict(geometry=geometry, materials_and_textures=surface, rigging_and_animation=animation)
