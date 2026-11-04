"""UV Bake: transfer a mesh's textures from one UV map to another (for example a repacked one).

The material keeps sampling the old UV map (made Active Render for the bake) while Cycles
writes into new images laid out on the new UV map (bake ``uv_layer``). Base Color is baked
as the Diffuse Color pass, Normal in tangent space of the new UV map. Like AutoBake it also
writes a MergeMask (UV coverage) and stores the images, material and object properties that
Merge Materials reads. With Duplicate the work happens on a <mesh>_UVBake copy.
"""
import os

import bpy

from ..core.datablock_names import remove_numbered_files, take_name
from .bake_constants import (
    BAKE_ALPHA_IMAGE_PROP,
    BAKE_ALPHA_NODE,
    BAKE_BASE_COLOR_IMAGE_PROP,
    BAKE_BASE_COLOR_NODE,
    BAKE_NORMAL_IMAGE_PROP,
    BAKE_NORMAL_NODE,
    BAKE_SOURCE_ALPHA_IMAGE_PROP,
    BAKE_SOURCE_BASE_COLOR_IMAGE_PROP,
    BAKE_SOURCE_NORMAL_IMAGE_PROP,
    BAKE_TARGET_MATERIAL_PROP,
)
from .bake_images import (
    _alpha_map_pixels,
    _apply_bake_background,
    _apply_bake_roughness,
    _coverage_from_image,
    _fill_normal_background,
    _read_image_pixels,
    _safe_path_name,
    _save_image_as_png,
    _write_pixels,
)

SUFFIX = '_UVBake'
TARGET_NODE = 'PolyGroups UV Bake Target'


def resolve_uv_maps(mesh, source_name='', target_name=''):
    """(source, target) UV map names: source defaults to Active Render, target to the other map."""
    layers = mesh.uv_layers
    if len(layers) < 2:
        raise ValueError('UV Bake needs two UV maps: the current one and the new one')
    source = layers.get(source_name) if source_name else next((uv for uv in layers if uv.active_render), layers[0])
    if source is None:
        raise ValueError(f'UV map not found: {source_name}')
    if target_name:
        target = layers.get(target_name)
        if target is None:
            raise ValueError(f'UV map not found: {target_name}')
    else:
        active = layers.active
        target = active if active is not None and active != source else next(uv for uv in layers if uv != source)
    if target == source:
        raise ValueError('From UV and To UV must be different UV maps')
    return source.name, target.name


def _new_image(name, resolution, colorspace):
    # A working name: the final one may still belong to a texture the bake reads (see uv_bake).
    image = bpy.data.images.new('__uv_bake_' + name, width=resolution, height=resolution, alpha=True)
    image.generated_color = (0.0, 0.0, 0.0, 0.0)  # alpha 0 = not covered; the bake writes alpha 1
    image.colorspace_settings.name = colorspace
    image['polygroups_uv_bake_name'] = name
    return image


def make_target(context, obj, duplicate):
    """The object that receives the bake: the mesh itself, or a fresh <mesh>_UVBake copy."""
    if not duplicate:
        return obj
    name = obj.name + SUFFIX
    old = bpy.data.objects.get(name)
    if old is not None and old.library is None:
        mesh = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.animation_data_clear()
    for collection in obj.users_collection:
        collection.objects.link(copy)
    copy.name = copy.data.name = name
    return copy


class _BakeScene:
    """Cycles, bake and selection overrides for one UV Bake; everything is restored afterwards."""

    def __init__(self, context, target):
        self.context, self.target = context, target
        scene = context.scene
        self.saved = [(scene.render, 'engine', scene.render.engine)]
        bake = scene.render.bake
        for name in ('use_selected_to_active', 'use_clear', 'margin', 'target'):
            self.saved.append((bake, name, getattr(bake, name)))
        self.selection = list(context.selected_objects)
        self.active = context.view_layer.objects.active

    def __enter__(self):
        scene = self.context.scene
        scene.render.engine = 'CYCLES'
        self.saved.append((scene.cycles, 'samples', scene.cycles.samples))
        scene.cycles.samples = 1  # Diffuse Color and Normal need no sampling noise reduction
        scene.render.bake.use_selected_to_active = False
        scene.render.bake.target = 'IMAGE_TEXTURES'
        for obj in self.context.selected_objects:
            obj.select_set(False)
        self.target.hide_set(False)
        self.target.hide_viewport = self.target.hide_render = self.target.hide_select = False
        self.target.select_set(True)
        self.context.view_layer.objects.active = self.target
        return self

    def __exit__(self, *_exc):
        for owner, name, value in reversed(self.saved):
            setattr(owner, name, value)
        for obj in self.context.selected_objects:
            obj.select_set(False)
        for obj in self.selection:
            try:
                obj.select_set(True)
            except ReferenceError:
                pass
        self.context.view_layer.objects.active = self.active if self.active is not None else self.target


def _final_material(target, base, normal, alpha, uv_name):
    material = bpy.data.materials.new('__uv_bake_tmp')
    material = take_name(bpy.data.materials, material, 'M_' + target.name, replace=True)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = next((node for node in tree.nodes if node.type == 'BSDF_PRINCIPLED'), None) \
        or tree.nodes.new('ShaderNodeBsdfPrincipled')
    _apply_bake_roughness(bsdf)
    uv_node = tree.nodes.new('ShaderNodeUVMap')
    uv_node.uv_map = uv_name
    uv_node.location = (-860, 0)

    def image_node(name, image, location):
        node = tree.nodes.new('ShaderNodeTexImage')
        node.name = node.label = name
        node.image = image
        node.location = location
        tree.links.new(uv_node.outputs['UV'], node.inputs['Vector'])
        return node

    if base is not None:
        node = image_node(BAKE_BASE_COLOR_NODE, base, (-560, 100))
        tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    if normal is not None:
        node = image_node(BAKE_NORMAL_NODE, normal, (-560, -180))
        normal_map = tree.nodes.new('ShaderNodeNormalMap')
        normal_map.name = 'PolyGroups Bake Normal Map'
        normal_map.uv_map = uv_name
        normal_map.location = (-260, -180)
        tree.links.new(node.outputs['Color'], normal_map.inputs['Color'])
        tree.links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])
    image_node(BAKE_ALPHA_NODE, alpha, (-560, -460))
    return material


def uv_bake(context, obj, settings, report=print):
    """Run one UV Bake on ``obj``; returns the object that holds the new material and textures."""
    if obj is None or obj.type != 'MESH':
        raise ValueError('Select a mesh')
    if not bpy.data.filepath:
        raise ValueError('Save the blend file first: UV Bake stores its textures on disk')
    if not (settings.uv_bake_base_color or settings.uv_bake_normal):
        raise ValueError('Enable Base Color or Normal')
    if not any(slot.material for slot in obj.material_slots):
        raise ValueError(f'{obj.name} has no material to transfer')
    source_uv, target_uv = resolve_uv_maps(obj.data, settings.uv_bake_source_uv, settings.uv_bake_target_uv)
    if context.object is not None and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    resolution = int(settings.uv_bake_resolution)
    target = make_target(context, obj, settings.uv_bake_duplicate)
    layers = target.data.uv_layers
    # The material samples the old UV map (image nodes without a UV input use Active Render).
    layers[source_uv].active_render = True
    stem = _safe_path_name(target.name)
    base = _new_image(f'{stem}_BaseColor', resolution, 'sRGB') if settings.uv_bake_base_color else None
    normal = _new_image(f'{stem}_Normal', resolution, 'Non-Color') if settings.uv_bake_normal else None
    # Bake on temporary copies of the materials: the originals (and the source mesh) stay untouched.
    originals = list(target.data.materials)
    copies = {}
    for index, material in enumerate(originals):
        if material is None:
            continue
        if material not in copies:
            copies[material] = material.copy()
        target.data.materials[index] = copies[material]
    try:
        with _BakeScene(context, target):
            for image, kind in ((base, 'DIFFUSE'), (normal, 'NORMAL')):
                if image is None:
                    continue
                for material in copies.values():
                    material.use_nodes = True
                    nodes = material.node_tree.nodes
                    node = nodes.get(TARGET_NODE) or nodes.new('ShaderNodeTexImage')
                    node.name = TARGET_NODE
                    node.image = image
                    nodes.active = node
                options = dict(type=kind, uv_layer=target_uv, margin=settings.bake_margin,
                               use_clear=True, target='IMAGE_TEXTURES', use_selected_to_active=False)
                if kind == 'DIFFUSE':
                    options['pass_filter'] = {'COLOR'}
                else:
                    options['normal_space'] = 'TANGENT'
                if 'FINISHED' not in bpy.ops.object.bake(**options):
                    raise RuntimeError(f'UV Bake {kind.title()} failed for {target.name}')
    except Exception:
        for index, material in enumerate(originals):
            target.data.materials[index] = material
        bpy.data.batch_remove(set(copies.values()) | {image for image in (base, normal) if image})
        if target is not obj:
            mesh = target.data
            bpy.data.objects.remove(target, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
    bpy.data.batch_remove(set(copies.values()))
    # Coverage of the new UV layout -> MergeMask, background fill like AutoBake.
    size = (resolution, resolution)
    coverage = _coverage_from_image(base or normal, size)
    alpha = _new_image(f'{stem}_MergeMask', resolution, 'Non-Color')
    _write_pixels(alpha, _alpha_map_pixels(coverage))
    alpha['polygroups_bake_mask'] = 'MergeMask'
    if base is not None:
        _write_pixels(base, _apply_bake_background(_read_image_pixels(base, size), coverage, size,
                                                   settings.bake_background_mode))
    if normal is not None:
        _write_pixels(normal, _fill_normal_background(_read_image_pixels(normal, size), coverage))
    folder = os.path.join(os.path.dirname(bpy.data.filepath), 'Bakes', stem)
    os.makedirs(folder, exist_ok=True)
    for image in (base, normal, alpha):
        if image is not None:
            # The bake is done: the new texture now replaces any older one of this name.
            take_name(bpy.data.images, image, image.pop('polygroups_uv_bake_name'), replace=True)
            path = os.path.join(folder, image.name + '.png')
            _save_image_as_png(image, path)
            remove_numbered_files(path)
    target.data.materials.clear()
    material = _final_material(target, base, normal, alpha, target_uv)
    target.data.materials.append(material)
    target.data.polygons.foreach_set('material_index', [0] * len(target.data.polygons))
    # The new UV map becomes both the edited and the rendered one.
    layers.active = layers[target_uv]
    layers[target_uv].active_render = True
    for prop, source_prop, image in ((BAKE_BASE_COLOR_IMAGE_PROP, BAKE_SOURCE_BASE_COLOR_IMAGE_PROP, base),
                                     (BAKE_NORMAL_IMAGE_PROP, BAKE_SOURCE_NORMAL_IMAGE_PROP, normal),
                                     (BAKE_ALPHA_IMAGE_PROP, BAKE_SOURCE_ALPHA_IMAGE_PROP, alpha)):
        if image is not None:
            target[prop] = target[source_prop] = image.name
    target[BAKE_TARGET_MATERIAL_PROP] = material.name
    report(f'UV Bake: {source_uv} -> {target_uv} on {target.name} | {resolution}px | {folder}')
    return target


class OBJECT_OT_polygroups_uv_bake(bpy.types.Operator):
    bl_idname = 'object.polygroups_uv_bake'
    bl_label = 'UV Bake'
    bl_description = ('Bake the textures of the active mesh from its current UV map onto the new one, save them '
                      'to Bakes with a MergeMask, assign a new material and make the new UV map active')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        settings = getattr(context.scene, 'polygroups_baking_settings', None)
        return (obj is not None and obj.type == 'MESH' and len(obj.data.uv_layers) >= 2
                and settings is not None and not settings.bake_task_is_running)

    def execute(self, context):
        settings = context.scene.polygroups_baking_settings
        try:
            target = uv_bake(context, context.active_object, settings,
                             report=lambda text: self.report({'INFO'}, text))
        except (ValueError, RuntimeError) as error:
            settings.uv_bake_status = str(error)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        settings.uv_bake_status = f'Baked {target.name}: {target.data.uv_layers.active.name}'
        return {'FINISHED'}
