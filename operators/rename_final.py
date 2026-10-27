"""Rename prepared assets without regenerating geometry, UVs or materials."""
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import os
import re
import shutil
import tempfile
import uuid

import bpy
from ..core.asset_names import asset_name
from ..services.fab_media import natural, _evaluation_visibility
from .phase2_blend_export import asset_collections, export_selected_collection_blend
from .unreal_lod_rename import image_nodes
from .fab_preparation import _texture_suffix
from .phase2_processing import available


def identity(obj, old, new):
    """Keep prepared Unreal/Unity suffixes instead of reassigning LOD indices."""
    name = obj.name
    if re.fullmatch(r'SM_' + re.escape(old) + r'_(?:MID|LOW|HIGH|LOD\d+)', name, re.I):
        return 'SM_' + new + name[len('SM_' + old):]
    if re.fullmatch(re.escape(old) + r'(?:\.LOD\d+)?', name, re.I) and obj.get('unity_prepared'):
        return new + name[len(old):]
    if name.upper().startswith(('UCX_', 'UBX_', 'USP_', 'UCP_')) and old in name:
        return name.replace(old, new, 1)
    raise ValueError('Unrecognized final mesh identity: ' + name)


def plan_rename(context):
    p = context.scene.polygroups_model_preparation_settings
    name = asset_name(p.phase2_rename_asset)
    ni, vi = p.phase2_rename_name_index.strip(), p.phase2_rename_version_index.strip()
    if not name or not re.fullmatch(r'[\w]+', name) or not re.fullmatch(r'[0-9]+', ni) or not re.fullmatch(r'[0-9]+', vi):
        raise ValueError('Enter an Asset Name and numeric Name / Version Index')
    groups = defaultdict(list)
    for col in sorted(asset_collections(context.scene), key=lambda c: natural(c.name)):
        match = re.fullmatch(r'(.+_\d+_\d+)(?:_LOD\d+)?_Collection', col.name, re.I)
        if not match:
            continue
        old = match[1]
        if any(obj.type == 'MESH' and (re.search(r'_(?:MID|LOW|HIGH|LOD\d+)$', obj.name, re.I)
                                      or obj.get('unity_prepared')) for obj in col.all_objects):
            groups[old].append(col)
    packs = sorted(groups.items(), key=lambda item: natural(item[0]))
    if not packs:
        raise ValueError('No prepared Asset_XX_NN_Collection assets in the current scene')
    plans, owned = [], set()
    for offset, (old, collections) in enumerate(packs):
        col = collections[0]
        asset_objects = {obj for collection in collections for obj in collection.all_objects}
        new = f'{name}_{ni.zfill(2)}_{str(int(vi)+offset).zfill(max(2, len(vi)))}'
        if any(collection.library for collection in collections) or any(obj.library for obj in asset_objects):
            raise ValueError('Make linked assets local before renaming: ' + col.name)
        objects = {}
        for obj in sorted(asset_objects, key=lambda o: natural(o.name)):
            if obj.type == 'MESH' and not obj.get('polygroups_render_multiview') and not obj.get('polygroups_texture_plane'):
                if obj in owned or any(scene != context.scene for scene in obj.users_scene):
                    raise ValueError('Mesh is shared by multiple assets or scenes: ' + obj.name)
                objects[obj] = identity(obj, old, new)
                owned.add(obj)
        materials = {slot.material for obj in objects for slot in obj.material_slots if slot.material}
        images = {}
        suffixes = defaultdict(int)
        for material in sorted(materials, key=lambda m: m.name):
            for node in image_nodes(material.node_tree):
                image = node.image
                if image in images:
                    continue
                if image.source not in {'FILE', 'GENERATED'}:
                    raise ValueError('Unsupported texture source (use single images): ' + image.name)
                suffix = _texture_suffix(image, node)
                suffixes[suffix] += 1
                target = f'T_{new}_{suffix}' + (f'_{suffixes[suffix]}' if suffixes[suffix] > 1 else '')
                source = Path(bpy.path.abspath(image.filepath, library=image.library)) if image.filepath else None
                extension = source.suffix.lower() if source and source.suffix else '.png'
                if image.source == 'GENERATED':
                    extension = '.exr' if image.is_float else '.png'
                destination = Path(bpy.data.filepath).parent / 'Textures' / new / (target + extension)
                if not image.packed_file and not image.is_dirty and image.source == 'FILE' and (source is None or not source.is_file()):
                    raise ValueError('Texture file is missing: ' + image.name)
                images[image] = (target, source, destination)
        mats = {mat: f'M_{new}' + (f'_{i+1}' if i else '') for i, mat in enumerate(sorted(materials, key=lambda m: m.name))}
        plans.append(dict(collection=col, collections={c: new + c.name[len(old):] for c in collections},
                          old=old, new=new, objects=objects, materials=mats, images=images))
    # Copy shared resources per asset. Unrelated users retain their existing IDs and paths.
    mat_packs, image_packs = defaultdict(set), defaultdict(set)
    for index, plan in enumerate(plans):
        for mat in plan['materials']:
            mat_packs[mat].add(index)
        for image in plan['images']:
            image_packs[image].add(index)
    external_mats = {slot.material for obj in bpy.data.objects if obj not in owned and obj.type == 'MESH'
                     for slot in obj.material_slots if slot.material}
    all_mats = set(mat_packs)
    external_images = {node.image for mat in bpy.data.materials if mat not in all_mats or mat in external_mats
                       for node in image_nodes(mat.node_tree)}
    # World/compositor/nonmaterial users also make an image shared.
    nodes = defaultdict(set)
    for mat in bpy.data.materials:
        for node in image_nodes(mat.node_tree):
            nodes[node.image].add(node.as_pointer())
    for plan in plans:
        plan['copy_materials'] = {m for m in plan['materials'] if len(mat_packs[m]) > 1 or m in external_mats or m.library or m.use_fake_user}
        plan['copy_images'] = {i for i in plan['images'] if len(image_packs[i]) > 1 or i in external_images
                               or i.library or i.users > len(nodes[i]) or i.use_fake_user}
    changed = [p for p in plans if p['old'] != p['new']]
    movable_images = {image for p in changed for image in p['images'] if image not in p['copy_images']}
    movable_paths = {data[1].resolve() for p in changed for image, data in p['images'].items()
                     if image in movable_images and data[1] is not None}
    for image in bpy.data.images:
        if image not in movable_images and image.filepath:
            movable_paths.discard(Path(bpy.path.abspath(image.filepath, library=image.library)).resolve())
    for p in changed:
        for image, (target, source, destination) in p['images'].items():
            if (destination.exists() and (source is None or destination.resolve() != source.resolve())
                    and destination.resolve() not in movable_paths):
                raise ValueError('Texture destination belongs to another asset: ' + str(destination))
    targets = [(bpy.data.collections, [(col, name, False) for p in changed for col, name in p['collections'].items()]),
               (bpy.data.objects, [(o, n, False) for p in changed for o, n in p['objects'].items()]),
               (bpy.data.materials, [(m, n, m in p['copy_materials']) for p in changed for m, n in p['materials'].items()]),
               (bpy.data.images, [(i, data[0], i in p['copy_images']) for p in changed for i, data in p['images'].items()])]
    for ids, entries in targets:
        movable = {item for item, _, copied in entries if not copied}
        names = [name.casefold() for _, name, _ in entries]
        if len(names) != len(set(names)):
            raise ValueError('Target datablock names collide')
        for item, target, copied in entries:
            other = next((id for id in ids if id.name.casefold() == target.casefold()), None)
            if other is not None and other not in movable:
                raise ValueError('Target name belongs to another datablock: ' + target)
    return plans


class RenameTransaction:
    def __init__(self, directory):
        self.temp = tempfile.TemporaryDirectory(prefix='.final-rename-', dir=directory)
        self.undo = []
        self.names = {}
        self.created = []
        self.files = []

    def attr(self, obj, name, value):
        old = getattr(obj, name)
        self.undo.append(lambda: setattr(obj, name, old))
        setattr(obj, name, value)

    def prop(self, obj, key, value):
        exists, old = key in obj, obj.get(key)
        def undo():
            if exists:
                obj[key] = old
            elif key in obj:
                del obj[key]
        self.undo.append(undo)
        obj[key] = value

    def rename(self, obj, name):
        self.names.setdefault(obj, obj.name)
        obj.name = name
        if obj.name != name:
            raise ValueError('Blender name collision: ' + name)

    def copy(self, ids, obj):
        result = obj.copy()
        self.created.append((ids, result))
        return result

    def groups(self, tree):
        if tree:
            for node in tree.nodes:
                if node.type == 'GROUP' and node.node_tree:
                    group = self.copy(bpy.data.node_groups, node.node_tree)
                    self.attr(node, 'node_tree', group)
                    self.groups(group)

    def install(self, staged, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if destination.exists():
            backup = Path(self.temp.name) / f'backup-{len(self.files)}'
            shutil.copy2(destination, backup)
        self.files.append((destination, backup))
        os.replace(staged, destination)

    def finish(self, success):
        if not success:
            for undo in reversed(self.undo):
                undo()
            for obj in self.names:
                obj.name = '__RenameRollback_' + uuid.uuid4().hex
            for obj, name in self.names.items():
                obj.name = name
            for ids, obj in reversed(self.created):
                ids.remove(obj)
            for destination, backup in reversed(self.files):
                if backup:
                    os.replace(backup, destination)
                else:
                    destination.unlink(missing_ok=True)
        self.temp.cleanup()


def apply_rename(context, plans):
    plans = [plan for plan in plans if plan['old'] != plan['new']]
    if not plans:
        return {}
    tx = RenameTransaction(Path(bpy.data.filepath).parent)
    success = False
    try:
        resolved, targets, replacements, texture_files = [], [], {}, []
        for plan in plans:
            col, old, new = plan['collection'], plan['old'], plan['new']
            replacements[old] = new
            targets.extend(plan['collections'].items())
            materials = {m: tx.copy(bpy.data.materials, m) if m in plan['copy_materials'] else m for m in plan['materials']}
            images = {i: tx.copy(bpy.data.images, i) if i in plan['copy_images'] else i for i in plan['images']}
            for source, mat in materials.items():
                tx.groups(mat.node_tree)
                targets.append((mat, plan['materials'][source]))
                for node in image_nodes(mat.node_tree):
                    tx.attr(node, 'image', images[node.image])
            for obj, target in plan['objects'].items():
                replacements[obj.name] = target
                targets.append((obj, target))
                if obj.data.users > 1 or obj.data.library:
                    tx.attr(obj, 'data', tx.copy(bpy.data.meshes, obj.data))
                # Mesh datablocks may also have exact names referenced by other objects.
                other = bpy.data.meshes.get(target)
                if other and other != obj.data and not any(o.data == other for p in plans for o in p['objects']):
                    raise ValueError('Mesh datablock target exists: ' + target)
                targets.append((obj.data, target))
                for index, slot in enumerate(obj.material_slots):
                    material = slot.material
                    if material:
                        tx.undo.append(lambda obj=obj, index=index, material=material: setattr(obj.material_slots[index], 'material', material))
                        slot.material = materials[material]
            for source, image in images.items():
                target, path, destination = plan['images'][source]
                targets.append((image, target))
                staged = Path(tx.temp.name) / (uuid.uuid4().hex + destination.suffix)
                if source.packed_file and not source.is_dirty:
                    staged.write_bytes(source.packed_file.data)
                elif source.source == 'FILE' and not source.is_dirty:
                    shutil.copy2(path, staged)
                else:
                    if source.source == 'GENERATED':
                        tx.attr(image, 'file_format', 'OPEN_EXR' if image.is_float else 'PNG')
                    previous = image.filepath_raw
                    try:
                        image.save(filepath=str(staged))
                    finally:
                        image.filepath_raw = previous
                texture_files.append((staged, destination))
                tx.attr(image, 'filepath_raw', bpy.path.relpath(str(destination)))
                if image.source == 'GENERATED':
                    tx.attr(image, 'source', 'FILE')
            resolved.append((plan, materials, images))
        # Read every source before installing anything: index shifts may swap paths.
        for staged, destination in texture_files:
            tx.install(staged, destination)
        # Reserve names before applying swaps, so Blender never adds .001 suffixes.
        for obj, _ in targets:
            tx.names.setdefault(obj, obj.name)
            obj.name = '__FinalRename_' + uuid.uuid4().hex
        for obj, name in targets:
            tx.rename(obj, name)
        for plan, materials, images in resolved:
            for item in (*plan['collections'], *plan['objects'], *(obj.data for obj in plan['objects']), *materials.values(), *images.values()):
                for key in ('unreal_lod_asset', 'unity_asset_name'):
                    if key in item:
                        tx.prop(item, key, plan['new'])
            for obj in {obj for collection in plan['collections'] for obj in collection.all_objects}:
                for key in ('polygroups_lod_source', 'polygroups_lod_label'):
                    if isinstance(obj.get(key), str) and obj[key] in replacements:
                        tx.prop(obj, key, replacements[obj[key]])
                if obj.type == 'FONT' and obj.parent in plan['objects']:
                    pattern = '|'.join(re.escape(before) for before in sorted(replacements, key=len, reverse=True))
                    body = re.sub(pattern, lambda match: replacements[match[0]], obj.data.body)
                    if obj.data.users > 1:
                        tx.attr(obj, 'data', tx.copy(bpy.data.curves, obj.data))
                    tx.attr(obj.data, 'body', body)
        success = True
    finally:
        tx.finish(success)
    return replacements


def reexport(context, plans, report):
    from .mesh_export import _evaluated_mesh_counts, _write_export_mesh_info
    from .unreal_lod_export import export_lods, lod_identity
    p = context.scene.polygroups_model_preparation_settings
    s = context.scene.polygroups_mesh_finalization_settings
    unity = p.phase2_run_engine == 'UNITY'
    engine = 'Unity' if unity else 'Unreal'
    root = Path(bpy.path.abspath(s.unity_export_directory)) if unity else Path(bpy.data.filepath).parent / '!Unreal'
    meshes = [obj for plan in plans for obj in plan['objects']
              if not obj.name.upper().startswith(('UCX_', 'UBX_', 'USP_', 'UCP_'))
              and not (obj.name.upper().endswith('_LOW') and any(re.search(r'[._]LOD[._]?0$', other.name, re.I)
                                                                for other in plan['objects']))]
    selected, active = list(context.selected_objects), context.view_layer.objects.active
    locks = [(obj, obj.hide_select) for obj in meshes]
    try:
        with _evaluation_visibility(context):
            bpy.ops.object.select_all(action='DESELECT')
            for obj in meshes:
                obj.hide_select = False
                obj.hide_set(False)
                obj.select_set(True)
            context.view_layer.objects.active = meshes[0]
            if p.phase2_rename_fbx:
                options = SimpleNamespace(mesh_export_fbx=True, mesh_export_glb=False, mesh_export_gltf=False,
                    mesh_export_sort=p.phase2_export_sort, mesh_export_info_format='JSON' if p.phase2_rename_json else 'NONE',
                    unreal_glb_mode='SEPARATE', unreal_gltf_mode='SEPARATE', is_property_set=lambda name: True)
                if 'FINISHED' not in export_lods(context, options, report, engine=engine, output_root=root, overwrite=True):
                    raise RuntimeError('FBX / MeshInfo export failed')
            elif p.phase2_rename_json:
                entries = []
                for obj in meshes:
                    base, role, index = lod_identity(obj, engine)
                    vertices, triangles = _evaluated_mesh_counts(obj, context.evaluated_depsgraph_get())
                    entries.append(dict(name=obj.name, asset=base, role=role, lod_index=index,
                        lod=f'LOD{index}' if role == 'LOD' else 'HIGH', vertices=vertices, triangles=triangles,
                        collections=[col.name for col in obj.users_collection], files={}))
                root.mkdir(parents=True, exist_ok=True)
                _write_export_mesh_info(str(root), 'JSON', entries, engine)
            if p.phase2_rename_blend:
                folder = Path(bpy.data.filepath).parent / '!Blend'
                folder.mkdir(exist_ok=True)
                for plan in plans:
                    export_selected_collection_blend(plan['collection'], list(plan['objects']),
                        folder / (plan['new'] + '.blend'), p.phase2_blend_export_pack,
                        reset_y=p.phase2_blend_export_reset_y)
    finally:
        for obj, locked in locks:
            obj.hide_select = locked
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            if obj.name in context.view_layer.objects:
                obj.select_set(True)
        context.view_layer.objects.active = active


def update_gallery(context, plans):
    from ..services import fab_media as media
    s = context.scene.airetopo_fab_media_settings
    if s.result_text is None:
        return
    document = media.validate(s.result_text.as_string())
    document['fields'].update(media.measured_fields(media.inventory(context)))
    old_words = {re.sub(r'_\d+_\d+$', '', plan['old']) for plan in plans}
    new = asset_name(context.scene.polygroups_model_preparation_settings.phase2_rename_asset)
    previous_headline = document['fields']['assetHeadline']
    joined_headline = ' '.join(document['fields'][key] for key in ('mainHeadline1', 'mainHeadline2')).strip()
    normalize = lambda value: re.sub(r'[ _]+', '', value).casefold()
    if normalize(joined_headline) in {normalize(word) for word in (*old_words, previous_headline)}:
        words = new.replace('_', ' ').split()
        split = max(1, len(words)//2)
        document['fields']['mainHeadline1'] = ' '.join(words[:split])
        document['fields']['mainHeadline2'] = ' '.join(words[split:])
    for key in ('assetHeadline', 'mainHeadline1', 'mainHeadline2', 'description'):
        value = document['fields'][key]
        for old in sorted(old_words, key=len, reverse=True):
            value = re.sub(r'(?<!\w)' + re.escape(old).replace('_', '[ _]') + r'(?!\w)',
                           lambda match: new.replace('_', ' '), value, flags=re.I)
        document['fields'][key] = value
    document['fields']['assetHeadline'] = new.replace('_', ' ')
    content = media.dumps(document)
    if context.scene.polygroups_model_preparation_settings.phase2_rename_json:
        path = Path(bpy.path.abspath(s.saved_filepath)) if s.saved_filepath else Path(bpy.data.filepath).parent / 'texflow-fab-media.json'
        path.write_text(content, encoding='utf-8')
        s.saved_filepath = str(path)
    s.result_text.clear()
    s.result_text.write(content)
    for key in (*media.MEASURED, 'assetHeadline', 'mainHeadline1', 'mainHeadline2', 'description'):
        setattr(s, key, document['fields'][key])
    s.last_status = 'Updated after Rename Final Mesh'


class OBJECT_OT_polygroups_rename_final_meshes(bpy.types.Operator):
    bl_idname = 'object.polygroups_rename_final_meshes'
    bl_label = 'Rename Final Meshes'
    bl_description = 'Rename all prepared scene assets, materials and texture files; optionally reexport FBX, Blend and JSON'

    @classmethod
    def poll(cls, context):
        p = context.scene.polygroups_model_preparation_settings
        return context.mode == 'OBJECT' and available(context) and not p.phase2_rebake_queue_running

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        renamed = False
        try:
            plans = plan_rename(context)
            # Validate the existing gallery document before touching any asset or file.
            gallery = context.scene.airetopo_fab_media_settings
            if gallery.is_generating:
                raise ValueError('Wait for FAB JSON generation to finish')
            if gallery.result_text:
                from ..services.fab_media import validate, inventory
                validate(gallery.result_text.as_string())
                inventory(context)
            apply_rename(context, plans)
            renamed = True
            update_gallery(context, plans)
            reexport(context, plans, self.report)
            p.phase2_rename_status = f'Renamed {len(plans)} assets | {p.phase2_run_engine}'
            self.report({'INFO'}, p.phase2_rename_status)
            return {'FINISHED'}
        except (ValueError, RuntimeError, OSError) as error:
            p.phase2_rename_status = ('Renamed; follow-up export failed: ' if renamed else 'Rename failed: ') + str(error)
            self.report({'WARNING'}, p.phase2_rename_status)
            return {'FINISHED'} if renamed else {'CANCELLED'}
