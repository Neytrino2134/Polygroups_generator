"""Write every prepared *_Collection asset as its own clean blend file in !Blend."""
import os
import re
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path

import bpy
from mathutils import Vector

from .phase2_processing import available
from .render_studio import TAG as STUDIO_TAG
from ..core.generated_index import GENERATED_INDEX_PATTERN

BLEND_FOLDER = '!Blend'
COLLECTION_SUFFIX = '_Collection'
PREPARED_NAME = re.compile(r'_(MID|HIGH|LOD\d+)$', re.IGNORECASE)


def asset_collections(scene):
    """Top-level *_Collection assets of the scene that contain objects."""
    result = []

    def visit(parent):
        for child in parent.children:
            if child.name.endswith(COLLECTION_SUFFIX):
                if child.all_objects:
                    result.append(child)
            else:
                visit(child)

    visit(scene.collection)
    return result


def generated_collections(scene):
    """Generated.N collections (Retopo / Resculpting meshes) that contain objects."""
    return [col for col in scene.collection.children_recursive
            if GENERATED_INDEX_PATTERN.match(col.name) and col.all_objects]


def blend_file_stem(collection):
    stem = collection.name
    if stem.endswith(COLLECTION_SUFFIX):
        stem = stem[:-len(COLLECTION_SUFFIX)]
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', stem).strip(' .')
    return stem or 'Asset'


def _node_tree_images(tree, seen):
    if tree is None or tree in seen:
        return
    seen.add(tree)
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            yield node.image
        elif node.type == 'GROUP':
            yield from _node_tree_images(node.node_tree, seen)


def collection_images(collection):
    """Images used by the materials of the collection's objects."""
    images, trees = set(), set()
    for obj in collection.all_objects:
        for slot in obj.material_slots:
            if slot.material:
                images.update(_node_tree_images(slot.material.node_tree, trees))
    return images


@contextmanager
def reserved_name(id_collection, name):
    """Temporarily move an existing datablock out of the way of a clean name."""
    existing = id_collection.get(name)
    if existing is not None:
        existing.name = f'{name}__airetopo_hold'
    try:
        yield
    finally:
        if existing is not None and existing.name != name:
            existing.name = name


def _frame_camera(camera_object, collection):
    points = [obj.matrix_world @ Vector(corner) for obj in collection.all_objects
              if obj.type == 'MESH' for corner in obj.bound_box]
    if not points:
        center, radius = Vector((0, 0, 0)), 1.0
    else:
        low = Vector((min(p[i] for p in points) for i in range(3)))
        high = Vector((max(p[i] for p in points) for i in range(3)))
        center, radius = (low + high) / 2, max((high - low).length / 2, 0.1)
    direction = Vector((1.0, -1.2, 0.8)).normalized()
    camera_object.location = center + direction * radius * 3.2
    camera_object.rotation_euler = (center - camera_object.location).to_track_quat('-Z', 'Y').to_euler()
    return center, radius


def studio_collections(scene):
    """Scene_Studio / Camera_Studio / Light_Studio of the source scene, in that order."""
    return [item for role in ('scene', 'camera', 'light')
            for item in scene.collection.children if item.get(STUDIO_TAG) == role]


def enable_layer_collections(layer_collection):
    """Tick the collection checkbox and show it in the exported view layer."""
    layer_collection.exclude = False
    layer_collection.hide_viewport = False
    for child in layer_collection.children:
        enable_layer_collections(child)


def build_clean_scene(collection):
    """Create a scene holding the studio collections (or a generated Camera and Light) plus the one collection.

    Returns the scene and the temporary generated objects and data to remove afterwards."""
    # bpy.data.scenes.new() crashes Blender 5.2 inside libraries.write, so derive the
    # scene from a copy of the active one and empty it.
    source = bpy.context.scene
    scene = source.copy()
    scene.name = 'Scene'
    for child in list(scene.collection.children):
        scene.collection.children.unlink(child)
    for obj in list(scene.collection.objects):
        scene.collection.objects.unlink(obj)
    scene.world = None
    studio = studio_collections(source)
    scene.collection.children.link(collection)
    for view_layer in scene.view_layers:
        enable_layer_collections(view_layer.layer_collection.children[collection.name])
        for obj in collection.all_objects:
            obj.hide_set(False, view_layer=view_layer)
    if studio:
        for item in studio:
            scene.collection.children.link(item)
        if scene.camera is None or not any(scene.camera.name in item.all_objects for item in studio):
            scene.camera = next((obj for item in studio for obj in item.all_objects if obj.type == 'CAMERA'), None)
        return scene, (), ()
    scene.camera = None
    camera_data = bpy.data.cameras.new('Camera')
    camera_object = bpy.data.objects.new('Camera', camera_data)
    scene.collection.objects.link(camera_object)
    scene.camera = camera_object
    center, radius = _frame_camera(camera_object, collection)
    light_data = bpy.data.lights.new('Light', 'POINT')
    light_data.energy = 1000.0
    light_object = bpy.data.objects.new('Light', light_data)
    light_object.location = center + Vector((0.8, -0.6, 1.2)) * radius * 2.5
    scene.collection.objects.link(light_object)
    return scene, (camera_object, light_object), (camera_data, light_data)


def prepared_asset_meshes(collection):
    """Unparented prepared MID/HIGH/LODN meshes of an asset collection."""
    return [obj for obj in collection.all_objects
            if obj.type == 'MESH' and obj.parent is None
            and (PREPARED_NAME.search(obj.name) or obj.get('unity_prepared'))]


def selected_asset_packs(context):
    """Group the exact mesh selection under its owning asset/file name."""
    assets = asset_collections(context.scene)
    generated = generated_collections(context.scene)
    scene_collections = {context.scene.collection, *context.scene.collection.children_recursive}
    packs = {}
    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue
        owners = [col for col in assets if obj.name in col.all_objects]
        if not owners:
            owners = [col for col in generated if obj.name in col.all_objects]
        if not owners:
            owners = [col for col in obj.users_collection if col in scene_collections]
        if len(owners) != 1:
            raise ValueError(f'Select an unambiguous asset collection for {obj.name}')
        packs.setdefault(owners[0], []).append(obj)
    return sorted(packs.items(), key=lambda item: item[0].name.casefold())


@contextmanager
def selected_collection_copy(collection, meshes):
    """Clean export-only object copies; never include unselected collection siblings."""
    originals = [(obj, obj.name, obj.matrix_world.copy()) for obj in meshes]
    copies, temporary = {}, None
    with ExitStack() as holds:
        name = collection.name
        holds.enter_context(reserved_name(bpy.data.collections, name))
        try:
            temporary = bpy.data.collections.new(name)
            for obj, name, matrix in originals:
                holds.enter_context(reserved_name(bpy.data.objects, name))
                copy = obj.copy()
                copy.name = name
                temporary.objects.link(copy)
                copies[obj] = copy
            for obj, name, matrix in originals:
                copy = copies[obj]
                copy.parent = copies.get(obj.parent)
                copy.constraints.clear()
                copy.animation_data_clear()
                copy.matrix_world = matrix
            yield temporary
        finally:
            for copy in copies.values():
                bpy.data.objects.remove(copy, do_unlink=True)
            if temporary is not None:
                bpy.data.collections.remove(temporary)


@contextmanager
def enabled_for_export(collection):
    """Enable viewport/render on the collection tree and its meshes; restore the working file afterwards."""
    targets = [collection, *collection.children_recursive,
               *(obj for obj in collection.all_objects if obj.type == 'MESH')]
    saved = [(item, item.hide_viewport, item.hide_render) for item in targets]
    for item in targets:
        item.hide_viewport = item.hide_render = False
    try:
        yield
    finally:
        for item, viewport, render in saved:
            item.hide_viewport, item.hide_render = viewport, render


def export_collection_blend(collection, filepath, pack_textures=True, reset_y=False):
    """Write one collection with only its own textures; return the packed image count.

    With reset_y the prepared meshes are written at Y = 0; the working file keeps its positions."""
    packed = []
    moved = [(obj, obj.location.y) for obj in prepared_asset_meshes(collection)] if reset_y else []
    for obj, _y in moved:
        obj.location.y = 0.0
    studio = studio_collections(bpy.context.scene)
    if pack_textures:
        for image in set().union(*(collection_images(item) for item in [collection, *studio])):
            if image.source == 'FILE' and image.packed_file is None:
                image.pack()
                packed.append(image)
    try:
        with ExitStack() as holds:
            holds.enter_context(reserved_name(bpy.data.scenes, 'Scene'))
            holds.enter_context(enabled_for_export(collection))
            if not studio:
                # Generated Camera/Light need their plain names in the exported file.
                for id_collection, name in ((bpy.data.objects, 'Camera'), (bpy.data.objects, 'Light'),
                                            (bpy.data.cameras, 'Camera'), (bpy.data.lights, 'Light')):
                    holds.enter_context(reserved_name(id_collection, name))
            scene = objects = datas = None
            try:
                scene, objects, datas = build_clean_scene(collection)
                bpy.data.libraries.write(filepath, {scene}, path_remap='RELATIVE', compress=True)
            finally:
                # Remove the temporaries before the held names are given back.
                if scene is not None:
                    bpy.data.scenes.remove(scene)
                for obj in objects or ():
                    bpy.data.objects.remove(obj, do_unlink=True)
                for data in datas or ():
                    (bpy.data.cameras if data.id_type == 'CAMERA' else bpy.data.lights).remove(data)
    finally:
        for obj, y in moved:
            obj.location.y = y
        for image in packed:
            image.unpack(method='REMOVE')
    return len(packed)


def export_selected_collection_blend(collection, meshes, destination, pack_textures=True, reset_y=False):
    """Atomically replace one selected-asset blend, retaining its collection name."""
    destination = Path(destination)
    destination.parent.mkdir(exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.selected-', suffix='.blend', dir=destination.parent)
    os.close(fd)
    try:
        with selected_collection_copy(collection, meshes) as subset:
            export_collection_blend(subset, temporary, pack_textures, reset_y=reset_y)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


class OBJECT_OT_polygroups_phase2_export_blend(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_export_blend'
    bl_label = 'Export Blend Files'
    bl_description = ('Save each *_Collection asset as a separate clean blend (Scene, Camera, Light and one '
                      'collection with only its own textures packed) to the !Blend folder beside the saved blend')

    selected_only: bpy.props.BoolProperty(name='Selected Meshes Only', default=False,
        options={'SKIP_SAVE'}, description='Export only selected meshes, grouped by asset, replacing existing blend files')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and available(context)

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        if not bpy.data.filepath:
            p.phase2_blend_export_status = 'Save the working blend file first'
            self.report({'WARNING'}, p.phase2_blend_export_status)
            return {'CANCELLED'}
        selected_packs = {}
        if self.selected_only:
            try:
                selected_packs = dict(selected_asset_packs(context))
            except ValueError as error:
                p.phase2_blend_export_status = str(error)
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}
            collections = list(selected_packs)
        else:
            collections = asset_collections(context.scene)
            if p.phase2_blend_export_generated:
                collections += generated_collections(context.scene)
        if not collections:
            p.phase2_blend_export_status = ('Select at least one mesh' if self.selected_only else
                                           'No *_Collection assets in the scene')
            self.report({'WARNING'}, p.phase2_blend_export_status)
            return {'CANCELLED'}
        folder = Path(bpy.data.filepath).parent / BLEND_FOLDER
        names = [blend_file_stem(col) for col in collections]
        if len({name.casefold() for name in names}) != len(names):
            p.phase2_blend_export_status = 'Export failed: collection file names collide'
            self.report({'ERROR'}, p.phase2_blend_export_status)
            return {'CANCELLED'}
        done = 0
        try:
            folder.mkdir(exist_ok=True)
            for collection, name in zip(collections, names):
                p.phase2_blend_export_status = f'Exporting {done + 1}/{len(collections)}: {name}'
                destination = folder / f'{name}.blend'
                reset_y = p.phase2_blend_export_reset_y and collection.name.endswith(COLLECTION_SUFFIX)
                if self.selected_only:
                    export_selected_collection_blend(collection, selected_packs[collection], destination,
                                                     p.phase2_blend_export_pack, reset_y=reset_y)
                else:
                    export_collection_blend(collection, str(destination), p.phase2_blend_export_pack, reset_y=reset_y)
                done += 1
        except (RuntimeError, ValueError, OSError) as error:
            p.phase2_blend_export_status = f'Export failed after {done}/{len(collections)}: {error}'
            self.report({'ERROR'}, p.phase2_blend_export_status)
            return {'CANCELLED'}
        p.phase2_blend_export_status = f'Exported {done} blend file(s) to {BLEND_FOLDER}'
        self.report({'INFO'}, p.phase2_blend_export_status)
        return {'FINISHED'}


class OBJECT_OT_polygroups_phase2_open_blend_folder(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_open_blend_folder'
    bl_label = 'Open !Blend Folder'
    bl_description = 'Show the !Blend export folder in the file browser'

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath) and (Path(bpy.data.filepath).parent / BLEND_FOLDER).is_dir()

    def execute(self, context):
        os.startfile(str(Path(bpy.data.filepath).parent / BLEND_FOLDER)) if os.name == 'nt' else \
            bpy.ops.wm.path_open(filepath=str(Path(bpy.data.filepath).parent / BLEND_FOLDER))
        return {'FINISHED'}
