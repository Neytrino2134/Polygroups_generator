"""Temporary emission previews for asset Base Color and Normal textures."""
from math import radians
import json
import bpy

PLANE_TAG = 'polygroups_texture_plane'
TEMP_TAG = 'polygroups_temp_texture'


def texture_planes(collection=None):
    objects = collection.all_objects if collection else bpy.data.objects
    return [obj for obj in objects if obj.get(PLANE_TAG) in {'BaseColor', 'Normal'}]


def clear_planes(collection=None):
    planes = texture_planes(collection)
    for obj in planes:
        mesh = obj.data
        materials = list(mesh.materials)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0 and mesh.get(TEMP_TAG):
            bpy.data.meshes.remove(mesh)
        for material in materials:
            if material and material.users == 0 and material.get(TEMP_TAG):
                bpy.data.materials.remove(material)
    return len(planes)


def upstream_image(socket, visited=None):
    visited = visited or set()
    for link in socket.links:
        node = link.from_node
        if node.as_pointer() in visited:
            continue
        visited.add(node.as_pointer())
        if node.type == 'TEX_IMAGE' and node.image:
            return node
        for input_socket in node.inputs:
            found = upstream_image(input_socket, visited)
            if found:
                return found
    return None


def material_textures(material):
    if not material or not material.use_nodes:
        return None
    for node in material.node_tree.nodes:
        if node.type != 'BSDF_PRINCIPLED':
            continue
        base = upstream_image(node.inputs['Base Color'])
        normal = upstream_image(node.inputs['Normal'])
        if base and normal:
            return base, normal
    return None


def collection_textures(collection):
    from .render_queue import _render_suffix_from_name, MULTIVIEW_PROP
    meshes = sorted((obj for obj in collection.all_objects if obj.type == 'MESH' and not obj.get(PLANE_TAG) and not obj.get(MULTIVIEW_PROP)),
                    key=lambda obj: ({'LOW': 0, 'MID': 1}.get(_render_suffix_from_name(obj.name), 2), obj.name))
    for obj in meshes:
        for material in obj.data.materials:
            textures = material_textures(material)
            if textures:
                return textures
    return None


def create_plane(collection, kind, texture_node):
    mesh = bpy.data.meshes.new('temp_textures_' + kind)
    mesh[TEMP_TAG] = True
    mesh.from_pydata([(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0)], [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name='UVMap')
    for loop, coords in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = coords
    obj = bpy.data.objects.new(collection.name + '_Texture_' + kind, mesh)
    collection.objects.link(obj)
    obj[PLANE_TAG] = kind
    obj.location = (-.7 if kind == 'BaseColor' else .7, 0, .5)
    obj.rotation_euler.x = radians(90)
    material = bpy.data.materials.new('temp_textures_' + kind.lower())
    material[TEMP_TAG] = True
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    image = nodes.new('ShaderNodeTexImage')
    image.image = texture_node.image
    image.interpolation = texture_node.interpolation
    image.extension = texture_node.extension
    material.node_tree.links.new(image.outputs['Color'], emission.inputs['Color'])
    material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
    mesh.materials.append(material)
    return obj


class OBJECT_OT_prepare_render_textures(bpy.types.Operator):
    bl_idname = 'object.polygroups_prepare_render_textures'
    bl_label = 'Prepare Textures'
    bl_description = 'Create Base Color and Normal emission planes for each asset collection without modifying source materials'
    bl_options = {'REGISTER', 'UNDO'}
    collections_json: bpy.props.StringProperty(default='', options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        from .render_queue import _asset_name_from_collection
        prepared = 0
        skipped = []
        selected = set(json.loads(self.collections_json)) if self.collections_json else None
        for collection in context.scene.collection.children_recursive:
            if selected is not None and collection.name not in selected:
                continue
            if not _asset_name_from_collection(collection):
                continue
            textures = collection_textures(collection)
            if not textures:
                skipped.append(collection.name)
                continue
            clear_planes(collection)
            for kind, node in zip(('BaseColor', 'Normal'), textures):
                create_plane(collection, kind, node)
            prepared += 1
        self.report({'INFO'}, f'Prepared texture planes for {prepared} collection(s)')
        if skipped:
            self.report({'WARNING'}, 'No linked Base Color/Normal images: ' + ', '.join(skipped))
        return {'FINISHED'}


class OBJECT_OT_texture_plane_visibility(bpy.types.Operator):
    bl_idname = 'object.polygroups_texture_plane_visibility'
    bl_label = 'Show / Hide Texture Planes'
    bl_options = {'UNDO', 'INTERNAL'}
    kind: bpy.props.EnumProperty(items=[('BaseColor', 'Base Color', ''), ('Normal', 'Normal', '')])
    show: bpy.props.BoolProperty(default=True)

    @classmethod
    def poll(cls, context):
        return not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        for obj in texture_planes():
            if obj[PLANE_TAG] == self.kind:
                obj.hide_render = not self.show
                obj.hide_viewport = not self.show
        return {'FINISHED'}


class OBJECT_OT_clear_render_textures(bpy.types.Operator):
    bl_idname = 'object.polygroups_clear_render_textures'
    bl_label = 'Clear All Texture Planes'
    bl_description = 'Remove generated texture planes and their unused temporary meshes/materials'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        count = clear_planes()
        self.report({'INFO'}, f'Removed {count} texture plane(s)')
        return {'FINISHED'}


CLASSES = (OBJECT_OT_prepare_render_textures, OBJECT_OT_texture_plane_visibility, OBJECT_OT_clear_render_textures)
