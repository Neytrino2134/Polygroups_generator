"""Write every prepared *_Collection asset as its own clean blend file in !Blend."""
import os
import re
from contextlib import contextmanager
from pathlib import Path

import bpy
from mathutils import Vector

from .phase2_processing import available

BLEND_FOLDER = '!Blend'
COLLECTION_SUFFIX = '_Collection'


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


def blend_file_stem(collection):
    stem = collection.name[:-len(COLLECTION_SUFFIX)]
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


def build_clean_scene(collection):
    """Create Scene + Camera + Light + the one collection, return the datablocks to remove."""
    # bpy.data.scenes.new() crashes Blender 5.2 inside libraries.write, so derive the
    # scene from a copy of the active one and empty it.
    scene = bpy.context.scene.copy()
    scene.name = 'Scene'
    for child in list(scene.collection.children):
        scene.collection.children.unlink(child)
    for obj in list(scene.collection.objects):
        scene.collection.objects.unlink(obj)
    scene.world = None
    scene.camera = None
    scene.collection.children.link(collection)
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


def export_collection_blend(collection, filepath, pack_textures=True):
    """Write one collection with only its own textures; return the packed image count."""
    packed = []
    if pack_textures:
        for image in collection_images(collection):
            if image.source == 'FILE' and image.packed_file is None:
                image.pack()
                packed.append(image)
    try:
        with reserved_name(bpy.data.scenes, 'Scene'), \
                reserved_name(bpy.data.objects, 'Camera'), reserved_name(bpy.data.objects, 'Light'), \
                reserved_name(bpy.data.cameras, 'Camera'), reserved_name(bpy.data.lights, 'Light'):
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
        for image in packed:
            image.unpack(method='REMOVE')
    return len(packed)


class OBJECT_OT_polygroups_phase2_export_blend(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_export_blend'
    bl_label = 'Export Blend Files'
    bl_description = ('Save each *_Collection asset as a separate clean blend (Scene, Camera, Light and one '
                      'collection with only its own textures packed) to the !Blend folder beside the saved blend')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and available(context)

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        if not bpy.data.filepath:
            p.phase2_blend_export_status = 'Save the working blend file first'
            self.report({'WARNING'}, p.phase2_blend_export_status)
            return {'CANCELLED'}
        collections = asset_collections(context.scene)
        if not collections:
            p.phase2_blend_export_status = 'No *_Collection assets in the scene'
            self.report({'WARNING'}, p.phase2_blend_export_status)
            return {'CANCELLED'}
        folder = Path(bpy.data.filepath).parent / BLEND_FOLDER
        names = [blend_file_stem(col) for col in collections]
        if len({name.casefold() for name in names}) != len(names):
            p.phase2_blend_export_status = 'Export failed: collection names collide after removing _Collection'
            self.report({'ERROR'}, p.phase2_blend_export_status)
            return {'CANCELLED'}
        done = 0
        try:
            folder.mkdir(exist_ok=True)
            for collection, name in zip(collections, names):
                p.phase2_blend_export_status = f'Exporting {done + 1}/{len(collections)}: {name}'
                export_collection_blend(collection, str(folder / f'{name}.blend'), p.phase2_blend_export_pack)
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
