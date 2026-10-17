"""Rename complete FAB collections as a pack, preserving their triplets."""

import filecmp
import os
import re
import uuid

import bpy

from .fab_preparation import (
    _collection_name, _fab_image_source, _material_name, _name_parts,
    _object_name, _safe_asset_token, _safe_index_token, _texture_base_name,
    _write_fab_image_source,
)


COLLECTION_PATTERN = re.compile(r'^(.+?)_(\d+)_Collection$')
TEXTURE_CHANNEL = re.compile(
    r'_(AlphaMap|MergeMask|ArtifactMask|BaseColor|Normal|Roughness|Metallic|AO|Emissive|Opacity|Height|Map)(?:_\d+)?$')


def fab_triplet(collection):
    """Return a complete, consistently named set or None."""
    match = COLLECTION_PATTERN.fullmatch(collection.name)
    if not match or len(collection.objects) != 3:
        return None
    base = f'{match.group(1)}_{match.group(2)}'
    roles = {}
    for obj in collection.objects:
        role_match = re.fullmatch(r'SM_' + re.escape(base) + r'_(HIGH|MID|LOW)', obj.name)
        if obj.type != 'MESH' or not role_match:
            return None
        roles[role_match.group(1)] = obj
    return roles if len(roles) == 3 else None


def _images_for_material(material):
    if not material or not material.use_nodes or not material.node_tree:
        return []
    return [node.image for node in material.node_tree.nodes
            if node.type == 'TEX_IMAGE' and node.image is not None]


def _same_texture_file(source, destination):
    if not os.path.isfile(destination):
        return False
    if source[0] == 'FILE':
        return filecmp.cmp(source[1], destination, shallow=False)
    with open(destination, 'rb') as existing:
        return existing.read() == source[1]


def _check_names(mapping, datablocks, label):
    targets = list(mapping.values())
    if len(targets) != len(set(targets)):
        raise ValueError(f'Duplicate target {label} names in FAB pack')
    for datablock, target in mapping.items():
        existing = datablocks.get(target)
        if existing is not None and existing not in mapping:
            raise ValueError(f'{label} already exists outside FAB pack: {target}')


class OBJECT_OT_polygroups_rename_existing_fab(bpy.types.Operator):
    bl_idname = 'object.polygroups_rename_existing_fab'
    bl_label = 'Rename Existing FAB Pack'
    bl_description = 'Rename all complete numbered FAB collections in the scene, or only selected sets'
    bl_options = {'REGISTER', 'UNDO'}

    selected_only: bpy.props.BoolProperty(name='Selected Sets Only', default=False)

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        return context.mode == 'OBJECT' and not settings.fab_prepare_is_running

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        asset = _safe_asset_token(settings.fab_asset_name)
        start_token = _safe_index_token(settings.fab_asset_index)
        if not start_token.isdigit():
            self.report({'ERROR'}, 'FAB Index must be numeric for pack renaming')
            return {'CANCELLED'}
        selected = set(context.selected_objects)
        candidates = []
        for collection in context.scene.collection.children_recursive:
            match = COLLECTION_PATTERN.fullmatch(collection.name)
            if not match:
                continue
            if self.selected_only and not any(obj in selected for obj in collection.objects):
                continue
            roles = fab_triplet(collection)
            if roles is None:
                self.report({'ERROR'}, f'Incomplete FAB triplet: {collection.name}')
                return {'CANCELLED'}
            candidates.append((int(match.group(2)), collection.name.lower(), collection, roles))
        if not candidates:
            self.report({'WARNING'}, 'No complete numbered FAB collections found')
            return {'CANCELLED'}
        candidates.sort(key=lambda item: (item[0], item[1]))

        collection_names, object_names, mesh_names = {}, {}, {}
        material_names, image_names = {}, {}
        image_sources = {}
        files = []
        blend_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ''
        if settings.fab_copy_textures and not blend_dir:
            self.report({'ERROR'}, 'Save the blend file before relocating FAB textures')
            return {'CANCELLED'}
        try:
            for offset, (_old_index, _old_name, collection, roles) in enumerate(candidates):
                index = f'{int(start_token) + offset:0{len(start_token)}d}'
                collection_names[collection] = _collection_name(asset, index)
                materials = {}
                for role, obj in roles.items():
                    object_names[obj] = _object_name(asset, index, role)
                    if obj.data.users == 1:
                        mesh_names[obj.data] = object_names[obj]
                    for slot in obj.material_slots:
                        if slot.material:
                            materials.setdefault(slot.material, set()).add(role)
                for material, used_roles in materials.items():
                    if material in material_names:
                        raise ValueError(f'Material shared by two FAB sets: {material.name}')
                    role = 'HIGH' if used_roles == {'HIGH'} else 'MID'
                    material_names[material] = _material_name(asset, index, role)
                images = {}
                for material, used_roles in materials.items():
                    for image in _images_for_material(material):
                        images.setdefault(image, set()).update(used_roles)
                for image, used_roles in images.items():
                    if image in image_names:
                        raise ValueError(f'Texture shared by two FAB sets: {image.name}')
                    channel = TEXTURE_CHANNEL.search(image.name)
                    suffix = channel.group(0) if channel else '_Map'
                    role = 'HIGH' if used_roles == {'HIGH'} else 'MID'
                    target_name = _texture_base_name(asset, index, role) + suffix
                    image_names[image] = target_name
                    if settings.fab_copy_textures and image.source == 'FILE':
                        source = _fab_image_source(image)
                        if source is None:
                            raise ValueError(f'Missing texture: {image.name}')
                        destination = os.path.join(blend_dir, 'Textures',
                                                   _name_parts(asset, index), target_name + source[2])
                        same = (source[0] == 'FILE' and
                                os.path.normcase(os.path.abspath(source[1])) ==
                                os.path.normcase(os.path.abspath(destination)))
                        files.append((image, source, destination, same))

            _check_names(collection_names, bpy.data.collections, 'Collection')
            _check_names(object_names, bpy.data.objects, 'Object')
            _check_names(mesh_names, bpy.data.meshes, 'Mesh')
            _check_names(material_names, bpy.data.materials, 'Material')
            _check_names(image_names, bpy.data.images, 'Texture')
            source_paths = {os.path.normcase(os.path.abspath(source[1]))
                            for _image, source, _destination, _same in files
                            if source[0] == 'FILE'}
            destinations = set()
            for _image, source, destination, same in files:
                target_path = os.path.normcase(os.path.abspath(destination))
                if target_path in destinations:
                    raise ValueError(f'Duplicate texture destination: {destination}')
                destinations.add(target_path)
                if (os.path.exists(destination) and not same and
                        target_path not in source_paths and
                        not _same_texture_file(source, destination)):
                    raise ValueError(f'Different texture file already exists: {destination}')
            for material in bpy.data.materials:
                if material not in material_names and any(
                        image in image_names for image in _images_for_material(material)):
                    raise ValueError(f'Texture shared with material outside pack: {material.name}')
        except (ValueError, OSError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        # Stage all sources before replacing any destination. A destination may
        # be another set's old source when indices move within the same pack.
        staged = []
        try:
            for _image, source, destination, same in files:
                if not same:
                    temporary = destination + '.fab-' + uuid.uuid4().hex + '.tmp'
                    _write_fab_image_source(source, temporary)
                    staged.append((temporary, destination))
            for temporary, destination in staged:
                os.replace(temporary, destination)
        except OSError as error:
            for temporary, _destination in staged:
                if os.path.exists(temporary):
                    os.remove(temporary)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        # Temporary names permit shifts such as old 03 -> new 02 without Blender
        # assigning a .001 suffix while the old 02 still exists.
        for mapping in (collection_names, object_names, mesh_names, material_names, image_names):
            for datablock in mapping:
                datablock.name = '__FAB_TMP_' + uuid.uuid4().hex
        for mapping in (collection_names, object_names, mesh_names, material_names, image_names):
            for datablock, target in mapping.items():
                datablock.name = target
        for image, _source, destination, _same in files:
            image.filepath = bpy.path.relpath(destination)
            image.filepath_raw = image.filepath
            if image.packed_file is not None:
                image.unpack(method='REMOVE')

        self.report({'INFO'}, f'Renamed {len(candidates)} FAB collections ({len(object_names)} meshes)')
        return {'FINISHED'}


class OBJECT_OT_polygroups_fab_variant_visibility(bpy.types.Operator):
    bl_idname = 'object.polygroups_fab_variant_visibility'
    bl_label = 'FAB Variant Visibility'
    bl_description = 'Show or hide this FAB mesh type in all collections in the scene'
    bl_options = {'REGISTER', 'UNDO'}

    variant: bpy.props.EnumProperty(items=[(role, role, role) for role in ('LOW', 'MID', 'HIGH')])
    hidden: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        count = 0
        for obj in context.scene.objects:
            if obj.type == 'MESH' and re.fullmatch(r'SM_.+_' + self.variant, obj.name):
                obj.hide_viewport = self.hidden
                count += 1
        self.report({'INFO'}, f'{self.variant}: {count} mesh(es)')
        return {'FINISHED'}
