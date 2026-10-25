"""Independent Unreal LOD naming and material preparation (no Unity settings)."""
from array import array
from pathlib import Path
import re
import random
from ..core.asset_names import asset_name
import bpy
from .mesh_export import _safe_path_token
from .fab_preparation import _texture_suffix


def image_nodes(tree, seen=None):
    seen = set() if seen is None else seen
    if tree is None or tree in seen:
        return
    seen.add(tree)
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            yield node
        elif node.type == 'GROUP':
            yield from image_nodes(node.node_tree, seen)


def isolate_groups(tree):
    if tree:
        for node in tree.nodes:
            if node.type == 'GROUP' and node.node_tree:
                node.node_tree = node.node_tree.copy()
                isolate_groups(node.node_tree)


def polygon_count(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return len(mesh.polygons)
    finally:
        evaluated.to_mesh_clear()


def prepare_materials(meshes, base, copy_textures):
    """Preserve slots and share copies only where the source materials were shared."""
    sources = {mat for obj in meshes for mat in obj.data.materials if mat}
    external_materials = {mat for obj in bpy.data.objects if obj.type == 'MESH' and obj not in meshes
                          for mat in obj.data.materials if mat}
    external_images = {node.image for mat in external_materials for node in image_nodes(mat.node_tree)}
    materials, images, suffix_counts = {}, {}, {}
    for index, source in enumerate(sorted(sources, key=lambda mat: mat.name)):
        own = source.get('unreal_lod_asset') == base and source not in external_materials
        mat = source if own else source.copy()
        if not own:
            isolate_groups(mat.node_tree)
        mat.name = f'M_{base}' + (f'_{index + 1}' if index else '')
        mat['unreal_lod_asset'] = base
        materials[source] = mat
        for node in image_nodes(mat.node_tree):
            source_image = node.image
            if _texture_suffix(source_image, node) in {'AlphaMap', 'MergeMask', 'ArtifactMask'}:
                continue
            if source_image not in images:
                suffix = _texture_suffix(source_image, node)
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
                name = f'T_{base}_{suffix}' + (f'_{suffix_counts[suffix]}' if suffix_counts[suffix] > 1 else '')
                if source_image.get('unreal_lod_asset') == base and source_image not in external_images:
                    image = source_image
                else:
                    pixels = array('f', [0.0]) * len(source_image.pixels)
                    source_image.pixels.foreach_get(pixels)
                    image = bpy.data.images.new(name, width=source_image.size[0], height=source_image.size[1],
                        alpha=source_image.channels == 4, float_buffer=source_image.is_float)
                    image.colorspace_settings.name = source_image.colorspace_settings.name
                    image.alpha_mode = source_image.alpha_mode
                    image.pixels.foreach_set(pixels)
                    image.update()
                image.name = name
                image['unreal_lod_asset'] = base
                images[source_image] = image
            node.image = images[source_image]
    for obj in meshes:
        for index, source in enumerate(tuple(obj.data.materials)):
            if source:
                obj.data.materials[index] = materials[source]
    if copy_textures:
        directory = Path(bpy.data.filepath).parent / 'Textures' / base
        directory.mkdir(parents=True, exist_ok=True)
        for image in set(images.values()):
            path = directory / (_safe_path_token(image.name) + '.png')
            image.file_format = 'PNG'
            image.save(filepath=str(path))
            image.filepath_raw = bpy.path.relpath(str(path))
            if image.source == 'GENERATED':
                image.source = 'FILE'


def collection_packs(context):
    """Keep selected meshes in their own Generated.N/asset collection packs."""
    selected = {obj for obj in context.selected_objects if obj.type == 'MESH'}
    generated = [(collection, set(collection.all_objects) & selected)
                 for collection in bpy.data.collections
                 if re.fullmatch(r'Generated\.\d+', collection.name)]
    generated = [(collection, objects) for collection, objects in generated if objects]
    groups = {}
    if generated:
        assigned = set()
        for collection, objects in generated:
            if assigned & objects:
                raise ValueError('A selected mesh belongs to multiple Generated collections')
            groups[collection] = objects
            assigned.update(objects)
        if assigned != selected:
            raise ValueError('Select meshes from Generated collections only, without unrelated meshes')
    else:
        for obj in selected:
            owners = list(obj.users_collection)
            if len(owners) != 1:
                raise ValueError(f'Select an unambiguous asset collection for {obj.name}')
            groups.setdefault(owners[0], set()).add(obj)
    def natural(collection):
        return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                     for part in re.split(r'(\d+)', collection.name))
    return [(collection, groups[collection]) for collection in sorted(groups, key=natural)]


class OBJECT_OT_polygroups_unreal_lod_rename(bpy.types.Operator):
    bl_idname = 'object.polygroups_unreal_lod_rename'
    bl_label = 'Prepare / Rename LOD Meshes'
    bl_description = 'Prepare one Unreal LOD asset per selected collection, increasing Version Index for each pack'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        s = context.scene.polygroups_mesh_finalization_settings
        name = asset_name(s.unreal_lod_asset_name)
        s.unreal_lod_asset_name = name
        if not name or _safe_path_token(name) != name or not s.unreal_lod_name_index.isdigit() or not s.unreal_lod_version_index.isdigit():
            self.report({'ERROR'}, 'Enter a valid asset name and numeric Name Index / Version Index')
            return {'CANCELLED'}
        suffix = s.unreal_lod_high_suffix.strip()
        if s.unreal_lod_keep_high and (not suffix or _safe_path_token('Mesh' + suffix) != 'Mesh' + suffix
                                      or re.fullmatch(r'_LOD[0-9]+', suffix, re.IGNORECASE)):
            self.report({'ERROR'}, 'Enter a valid High suffix distinct from _LODN')
            return {'CANCELLED'}
        try:
            groups = collection_packs(context)
            plans = []
            depsgraph = context.evaluated_depsgraph_get()
            width = max(2, len(s.unreal_lod_version_index))
            all_selected = {obj for _, meshes in groups for obj in meshes}
            for offset, (source_collection, objects) in enumerate(groups):
                version = str(int(s.unreal_lod_version_index) + offset).zfill(width)
                base = f'{name}_{s.unreal_lod_name_index.zfill(2)}_{version}'
                meshes = sorted(objects, key=lambda obj: (-polygon_count(obj, depsgraph),
                    obj.get('unreal_lod_index', 0), obj.name))
                names = [f'SM_{base}' + (suffix if s.unreal_lod_keep_high and index == 0
                         else f'_LOD{index - int(s.unreal_lod_keep_high)}') for index in range(len(meshes))]
                for target in names:
                    existing = bpy.data.objects.get(target)
                    if existing is not None and existing not in all_selected:
                        raise ValueError(f'Object exists outside selection: {target}')
                collection = bpy.data.collections.get(base + "_Collection")
                outside = set(collection.all_objects) - all_selected if collection else set()
                # Rebuilding from a prepared HIGH/MID/LOW keeps those originals
                # in their asset collection. Only generated LODs are renamed.
                sources = {obj.get('polygroups_lod_source') for obj in objects}
                rebuilding = any(re.fullmatch(re.escape(f'SM_{base}') + r'_(?:HIGH|MID|LOW)', source or '', re.I)
                                 for source in sources)
                permitted = {obj for obj in outside if obj.type == 'FONT' and obj.parent in objects}
                if rebuilding:
                    permitted.update(obj for obj in outside if re.fullmatch(
                        re.escape(f'SM_{base}') + r'_(?:HIGH|MID|LOW)', obj.name, re.I))
                if outside - permitted:
                    raise ValueError(f'Collection contains unselected objects: {base}')
                plans.append((base, meshes, names))
            if s.unreal_lod_prepare_materials:
                if s.unreal_lod_copy_textures and not bpy.data.filepath:
                    raise ValueError('Save the blend file before copying textures')
                for obj in all_selected:
                    for mat in obj.data.materials:
                        if mat:
                            for node in image_nodes(mat.node_tree):
                                if _texture_suffix(node.image, node) not in {'AlphaMap', 'MergeMask', 'ArtifactMask'} and (
                                        node.image.source not in {'FILE', 'GENERATED'} or not len(node.image.pixels)):
                                    raise ValueError(f'Texture has no supported pixels: {node.image.name}')
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        # Resolve all name swaps only after every pack has passed preflight.
        for obj in all_selected:
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            obj.name = '__Unreal_LOD_Rename__'
        for base, meshes, names in plans:
            collection = bpy.data.collections.get(base + "_Collection")
            if collection is None:
                legacy = bpy.data.collections.get(base)
                if legacy is not None and set(legacy.all_objects).issubset(set(meshes)):
                    collection = legacy
                    collection.name = base + '_Collection'
                else:
                    collection = bpy.data.collections.new(base + '_Collection')
            if collection.name not in context.scene.collection.children:
                context.scene.collection.children.link(collection)
            collection.color_tag = (random.choice([f"COLOR_{i:02d}" for i in range(1, 9)])
                if s.unreal_lod_random_collection_color else s.unreal_lod_collection_color)
            collection['unreal_lod_asset'] = base
            for index, (obj, target) in enumerate(zip(meshes, names)):
                obj.name = obj.data.name = target
                obj['unreal_lod_asset'] = base
                obj['unreal_lod_index'] = index - int(s.unreal_lod_keep_high)
                if obj.name not in collection.objects:
                    collection.objects.link(obj)
                for old in list(obj.users_collection):
                    if old != collection:
                        old.objects.unlink(obj)
            try:
                if s.unreal_lod_prepare_materials:
                    prepare_materials(meshes, base, s.unreal_lod_copy_textures)
            except (RuntimeError, ValueError, OSError) as error:
                self.report({'ERROR'}, f'Unreal material preparation failed for {base}: {error}')
                return {'CANCELLED'}
        self.report({'INFO'}, f'Prepared {len(plans)} Unreal asset pack(s), {len(all_selected)} meshes')
        return {'FINISHED'}
