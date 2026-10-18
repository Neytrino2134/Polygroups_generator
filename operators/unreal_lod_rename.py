"""Independent Unreal LOD naming and material preparation (no Unity settings)."""
from array import array
from pathlib import Path
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
            image.filepath_raw = str(path)
            if image.source == 'GENERATED':
                image.source = 'FILE'


class OBJECT_OT_polygroups_unreal_lod_rename(bpy.types.Operator):
    bl_idname = 'object.polygroups_unreal_lod_rename'
    bl_label = 'Prepare / Rename LOD Meshes'
    bl_description = 'Sort selected meshes by polygon count, assign LOD0 onward, and move them into one Unreal asset collection'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        s = context.scene.polygroups_mesh_finalization_settings
        name = s.unreal_lod_asset_name.strip()
        if not name or _safe_path_token(name) != name or not s.unreal_lod_name_index.isdigit() or not s.unreal_lod_version_index.isdigit():
            self.report({'ERROR'}, 'Enter a valid asset name and numeric Name Index / Version Index')
            return {'CANCELLED'}
        base = f'{name}_{s.unreal_lod_name_index.zfill(2)}_{s.unreal_lod_version_index.zfill(2)}'
        meshes = sorted((obj for obj in context.selected_objects if obj.type == 'MESH'),
                        key=lambda obj: (-polygon_count(obj, context.evaluated_depsgraph_get()), obj.name))
        names = [f'SM_{base}_LOD{index}' for index in range(len(meshes))]
        for target in names:
            existing = bpy.data.objects.get(target)
            if existing is not None and existing not in meshes:
                self.report({'ERROR'}, f'Object exists outside selection: {target}')
                return {'CANCELLED'}
        if s.unreal_lod_prepare_materials:
            if s.unreal_lod_copy_textures and not bpy.data.filepath:
                self.report({'ERROR'}, 'Save the blend file before copying textures')
                return {'CANCELLED'}
            for obj in meshes:
                for mat in obj.data.materials:
                    if mat:
                        for node in image_nodes(mat.node_tree):
                            if _texture_suffix(node.image, node) not in {'AlphaMap', 'MergeMask', 'ArtifactMask'} and (
                                    node.image.source not in {'FILE', 'GENERATED'} or not len(node.image.pixels)):
                                self.report({'ERROR'}, f'Texture has no supported pixels: {node.image.name}')
                                return {'CANCELLED'}
        collection = bpy.data.collections.get(base)
        if collection is None:
            collection = bpy.data.collections.new(base)
        if base not in context.scene.collection.children:
            context.scene.collection.children.link(collection)
        collection.color_tag = s.unreal_lod_collection_color
        for obj in meshes:
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            obj.name = '__Unreal_LOD_Rename__'
        for index, (obj, name) in enumerate(zip(meshes, names)):
            obj.name = obj.data.name = name
            obj['unreal_lod_asset'] = base
            obj['unreal_lod_index'] = index
            if obj.name not in collection.objects:
                collection.objects.link(obj)
            for old in list(obj.users_collection):
                if old != collection:
                    old.objects.unlink(obj)
        try:
            if s.unreal_lod_prepare_materials:
                prepare_materials(meshes, base, s.unreal_lod_copy_textures)
        except (RuntimeError, ValueError, OSError) as error:
            self.report({'ERROR'}, f'Unreal material preparation failed: {error}')
            return {'FINISHED'}  # Keep an undo entry for already applied naming.
        self.report({'INFO'}, f'Prepared {len(meshes)} Unreal LOD meshes in {base}')
        return {'FINISHED'}
