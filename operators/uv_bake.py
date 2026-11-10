"""UV Bake: transfer a mesh's textures from one UV map to another (for example a repacked one).

The material keeps sampling the old UV map (made Active Render for the bake) while Cycles
writes into new images laid out on the new UV map (bake ``uv_layer``). Base Color is baked
as the Diffuse Color pass, Normal in tangent space of the new UV map. Like AutoBake it also
writes a MergeMask (UV coverage) and stores the images, material and object properties that
Merge Materials reads. With Duplicate the work happens on a <mesh>_UVBake copy.
"""
import os
import re
from array import array
from contextlib import ExitStack, contextmanager

import bpy

from ..core.datablock_names import remove_numbered_files, take_name
from ..core.generated_index import TRAILING_INDEX_PATTERN
from .phase2_zbrush_export import export_visibility, preserved_selection
from .baking import _redraw_bake_ui
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


class UVBakeCancelled(Exception):
    pass


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


def _new_bake_collection(context):
    indices = [int(match[1]) for collection in bpy.data.collections
               if (match := re.fullmatch(r'Generated(?:_UVBake)?\.(\d+)', collection.name, re.I))]
    collection = bpy.data.collections.new(f'Generated_UVBake.{max(indices, default=0) + 1:03d}')
    context.scene.collection.children.link(collection)
    return collection


def _duplicate_target(obj, collection):
    name = (TRAILING_INDEX_PATTERN.sub(lambda match: SUFFIX + match[0], obj.name)
            if TRAILING_INDEX_PATTERN.search(obj.name) else obj.name + SUFFIX)
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.animation_data_clear()
    collection.objects.link(copy)
    copy.name = name
    copy.data.name = copy.name
    return copy


def _remove_target(obj):
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _source_map(mesh, name):
    layers = mesh.uv_layers
    source = layers.get(name) if name else next((layer for layer in layers if layer.active_render), layers.active)
    if source is None:
        raise ValueError(f'UV map not found: {name}' if name else 'The mesh needs an existing UV map')
    return source.name


def _replace_source_map(mesh, source_name, target_name):
    layers = mesh.uv_layers
    layers.remove(layers[source_name])
    target = layers[target_name]
    target.name = source_name
    layers.active = target
    target.active_render = True
    return target.name


def _pack_new_maps(context, targets):
    settings = context.tool_settings
    sync, select_mode = settings.use_uv_select_sync, tuple(settings.mesh_select_mode)
    flags = []
    for target in targets:
        for elements in (target.data.vertices, target.data.edges, target.data.polygons):
            for attribute in ('hide', 'select'):
                values = array('b', [0]) * len(elements)
                elements.foreach_get(attribute, values)
                flags.append((elements, attribute, values))
    try:
        for obj in context.selected_objects:
            obj.select_set(False)
        for target in targets:
            target.select_set(True)
        context.view_layer.objects.active = targets[0]
        settings.use_uv_select_sync = True
        if 'FINISHED' not in bpy.ops.object.polygroups_uvpackmaster_pack('EXEC_DEFAULT'):
            raise RuntimeError(f'UVPackmaster PACK failed for {targets[0].name}')
    finally:
        if targets[0].mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        settings.use_uv_select_sync = sync
        settings.mesh_select_mode = select_mode
        for elements, attribute, values in flags:
            elements.foreach_set(attribute, values)


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
        return self

    def select_target(self):
        if self.context.object and self.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in self.context.selected_objects:
            obj.select_set(False)
        self.target.hide_set(False)
        self.target.hide_viewport = self.target.hide_render = self.target.hide_select = False
        self.target.select_set(True)
        self.context.view_layer.objects.active = self.target

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


def _final_material(name, base, normal, alpha, uv_name):
    material = bpy.data.materials.new('__uv_bake_tmp')
    material = take_name(bpy.data.materials, material, 'M_' + name, replace=True)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = next((node for node in tree.nodes if node.type == 'BSDF_PRINCIPLED'), None) \
        or tree.nodes.new('ShaderNodeBsdfPrincipled')
    _apply_bake_roughness(bsdf)
    uv_node = None
    if uv_name:
        uv_node = tree.nodes.new('ShaderNodeUVMap')
        uv_node.uv_map = uv_name
        uv_node.location = (-860, 0)

    def image_node(name, image, location):
        node = tree.nodes.new('ShaderNodeTexImage')
        node.name = node.label = name
        node.image = image
        node.location = location
        if uv_node is not None:
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


def _validate_bake(obj, settings):
    if not bpy.data.filepath:
        raise ValueError('Save the blend file first: UV Bake stores its textures on disk')
    if not (settings.uv_bake_base_color or settings.uv_bake_normal):
        raise ValueError('Enable Base Color or Normal')
    if not any(slot.material for slot in obj.material_slots):
        raise ValueError(f'{obj.name} has no material to transfer')


def _run_bake_pass(options, modal):
    if not modal:
        return 'FINISHED' in bpy.ops.object.bake(**options)

    outcome = None

    def complete(*_args):
        nonlocal outcome
        outcome = True

    def cancel(*_args):
        nonlocal outcome
        outcome = False

    handlers = bpy.app.handlers
    handlers.object_bake_complete.append(complete)
    handlers.object_bake_cancel.append(cancel)
    try:
        result = bpy.ops.object.bake('INVOKE_DEFAULT', **options)
        if 'RUNNING_MODAL' not in result:
            return 'FINISHED' in result
        # Allow the native job to start before testing whether it has stopped.
        yield None
        while bpy.app.is_job_running('OBJECT_BAKE'):
            yield None
        if outcome is False:
            raise UVBakeCancelled()
        return outcome is True
    finally:
        handlers.object_bake_complete.remove(complete)
        handlers.object_bake_cancel.remove(cancel)


def _bake_target(context, target, settings, source_uv, target_uv, base, normal, clear, label, modal):
    target.data.uv_layers[source_uv].active_render = True
    originals = [slot.material for slot in target.material_slots]
    copies = {}
    try:
        for index, material in enumerate(originals):
            if material is None:
                continue
            if material not in copies:
                copies[material] = material.copy()
            target.material_slots[index].material = copies[material]
        with _BakeScene(context, target) as scene:
            for image, kind, channel in ((base, 'DIFFUSE', 'Base Color'), (normal, 'NORMAL', 'Normal')):
                if image is None:
                    continue
                yield f'{label} | Baking {channel} | {target.name}'
                scene.select_target()
                for material in copies.values():
                    material.use_nodes = True
                    nodes = material.node_tree.nodes
                    node = nodes.get(TARGET_NODE) or nodes.new('ShaderNodeTexImage')
                    node.name = TARGET_NODE
                    node.image = image
                    nodes.active = node
                options = dict(type=kind, uv_layer=target_uv, margin=settings.bake_margin,
                               use_clear=clear, target='IMAGE_TEXTURES', use_selected_to_active=False)
                if kind == 'DIFFUSE':
                    options['pass_filter'] = {'COLOR'}
                else:
                    options['normal_space'] = 'TANGENT'
                if not (yield from _run_bake_pass(options, modal)):
                    raise RuntimeError(f'UV Bake {channel} failed for {target.name}')
    finally:
        for index, material in enumerate(originals):
            target.material_slots[index].material = material
        bpy.data.batch_remove(set(copies.values()))


def uv_bake(context, plans, settings, name, first, total, modal, replace_source=False, report=print):
    """Bake prepared UVs into one set of images, keeping previously baked islands."""
    resolution = int(settings.uv_bake_resolution)
    stem = _safe_path_name(name)
    base = _new_image(f'{stem}_BaseColor', resolution, 'sRGB') if settings.uv_bake_base_color else None
    normal = _new_image(f'{stem}_Normal', resolution, 'Non-Color') if settings.uv_bake_normal else None
    alpha = None
    try:
        for index, (target, source_uv, target_uv) in enumerate(plans):
            label = f'{first + index + 1}/{total}'
            yield from _bake_target(
                context, target, settings, source_uv, target_uv, base, normal, index == 0, label, modal,
            )
        label = f'{first + len(plans)}/{total}'
        yield f'{label} | Creating MergeMask | {name}'
        # Coverage of the new UV layout and background fill use the same rules as AutoBake.
        size = (resolution, resolution)
        coverage = _coverage_from_image(base or normal, size)
        alpha = _new_image(f'{stem}_MergeMask', resolution, 'Non-Color')
        _write_pixels(alpha, _alpha_map_pixels(coverage))
        alpha['polygroups_bake_mask'] = 'MergeMask'
        if base is not None:
            yield f'{label} | Filling Base Color | {name}'
            _write_pixels(base, _apply_bake_background(_read_image_pixels(base, size), coverage, size,
                                                       settings.bake_background_mode))
        if normal is not None:
            yield f'{label} | Filling Normal | {name}'
            _write_pixels(normal, _fill_normal_background(_read_image_pixels(normal, size), coverage))
        yield f'{label} | Saving textures and assigning material | {name}'
    except (Exception, GeneratorExit):
        bpy.data.batch_remove({image for image in (base, normal, alpha) if image})
        raise
    folder = os.path.join(os.path.dirname(bpy.data.filepath), 'Bakes', stem)
    os.makedirs(folder, exist_ok=True)
    for image in (base, normal, alpha):
        if image is not None:
            # The bake is done: the new texture now replaces any older one of this name.
            take_name(bpy.data.images, image, image.pop('polygroups_uv_bake_name'), replace=True)
            path = os.path.join(folder, image.name + '.png')
            _save_image_as_png(image, path)
            remove_numbered_files(path)
    _, first_source, first_target = plans[0]
    # Shared materials sample the active render UV on each mesh, even when the slot names differ.
    uv_name = '' if len(plans) > 1 else first_source if replace_source else first_target
    material = _final_material(name, base, normal, alpha, uv_name)
    for target, source_uv, target_uv in plans:
        if replace_source:
            target_uv = _replace_source_map(target.data, source_uv, target_uv)
        target.data.materials.clear()
        target.data.materials.append(material)
        target.material_slots[0].link = 'DATA'
        target.data.polygons.foreach_set('material_index', [0] * len(target.data.polygons))
        layers = target.data.uv_layers
        layers.active = layers[target_uv]
        layers[target_uv].active_render = True
        for prop, source_prop, image in ((BAKE_BASE_COLOR_IMAGE_PROP, BAKE_SOURCE_BASE_COLOR_IMAGE_PROP, base),
                                         (BAKE_NORMAL_IMAGE_PROP, BAKE_SOURCE_NORMAL_IMAGE_PROP, normal),
                                         (BAKE_ALPHA_IMAGE_PROP, BAKE_SOURCE_ALPHA_IMAGE_PROP, alpha)):
            if image is not None:
                target[prop] = target[source_prop] = image.name
            else:
                target.pop(prop, None)
                target.pop(source_prop, None)
        target[BAKE_TARGET_MATERIAL_PROP] = material.name
    report(f'UV Bake: {len(plans)} mesh(es) | {resolution}px | {folder}')


class OBJECT_OT_polygroups_uv_bake(bpy.types.Operator):
    bl_idname = 'object.polygroups_uv_bake'
    bl_label = 'UV Bake'
    bl_description = ('Bake textures of selected meshes from their current UV maps onto the new ones, save them '
                      'to Bakes with a MergeMask, assign a new material and make the new UV map active')
    bl_options = {'REGISTER', 'UNDO'}
    action: bpy.props.EnumProperty(items=(
        ('BAKE', 'UV Bake', 'Transfer textures between two existing maps on each selected mesh'),
        ('CREATE', 'Create New UV', 'Copy the source UV map for every selected mesh'),
        ('PACK', 'Pack to New UV', 'Copy and pack a new UV map for every selected mesh'),
        ('PACK_BAKE', 'Pack and UV Bake', 'Copy, pack and transfer textures for every selected mesh'),
    ), default='BAKE', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, 'polygroups_baking_settings', None)
        return (settings is not None and not settings.bake_task_is_running
                and not settings.uv_bake_is_running and not settings.autobake_queue_running
                and not bpy.app.is_job_running('OBJECT_BAKE')
                and any(obj.type == 'MESH' and obj.data.uv_layers for obj in context.selected_objects))

    def execute(self, context):
        settings = context.scene.polygroups_baking_settings
        active = context.active_object
        meshes = sorted((obj for obj in context.selected_objects if obj.type == 'MESH'),
                        key=lambda obj: (obj != active, obj.name.casefold()))
        baking = self.action in {'BAKE', 'PACK_BAKE'}
        duplicate = settings.uv_bake_duplicate and self.action != 'CREATE'
        together = ((self.action == 'PACK' and settings.uv_bake_pack_mode == 'TOGETHER')
                    or (self.action == 'PACK_BAKE' and settings.uv_bake_pack_bake_mode == 'TOGETHER'))
        plans = []
        try:
            if not meshes:
                raise ValueError('Select a mesh')
            uvpm = context.preferences.addons.get('uvpackmaster4')
            if uvpm is not None and getattr(uvpm.preferences, 'group_scheme_boxes_editing', False):
                raise ValueError('Finish editing the scheme target boxes before UV Bake')
            if self.action in {'PACK', 'PACK_BAKE'} and not hasattr(context.scene, 'uvpm4_props'):
                raise ValueError('Enable UVPackmaster 4 before packing a new UV map')
            for obj in meshes:
                if not duplicate and (obj.library or obj.data.library):
                    raise ValueError(f'{obj.name} is linked. Make it local before editing its UV maps')
                if baking:
                    _validate_bake(obj, settings)
                try:
                    if self.action == 'BAKE':
                        source_uv, target_uv = resolve_uv_maps(
                            obj.data, settings.uv_bake_source_uv, settings.uv_bake_target_uv,
                        )
                    else:
                        source_uv, target_uv = _source_map(obj.data, settings.uv_bake_source_uv), None
                except ValueError as error:
                    raise ValueError(f'{obj.name}: {error}') from error
                plans.append((obj, source_uv, target_uv))
            if context.object and context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except (ValueError, RuntimeError) as error:
            settings.uv_bake_status = str(error)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        groups = [plans] if together else [[plan] for plan in plans]
        modal = baking and not bpy.app.background and context.window is not None and context.area is not None
        self._settings = settings
        self._view_layer = context.view_layer
        self._scene = context.scene
        self._cancel_requested = False
        self._shows_progress = baking
        self._timer = None
        self._steps = self.run_groups(context, groups, settings, duplicate, len(plans), modal)
        channels = int(settings.uv_bake_base_color) + int(settings.uv_bake_normal) if baking else 0
        group_stages = 1 + int(self.action in {'PACK', 'PACK_BAKE'}) + (2 + channels if baking else 0)
        self._stage_count = len(groups) * group_stages + len(plans) * channels
        self._stage = 0
        settings.uv_bake_progress = 0
        if modal:
            settings.uv_bake_is_running = True
            settings.uv_bake_status = f'Preparing UV Bake | {len(plans)} mesh(es)'
            self._timer = context.window_manager.event_timer_add(0.12, window=context.window)
            context.window_manager.modal_handler_add(self)
            _redraw_bake_ui(context)
            return {'RUNNING_MODAL'}
        while (result := self.advance(context)) is None:
            pass
        return result

    def advance(self, context):
        try:
            stage = self._steps.throw(UVBakeCancelled()) if self._cancel_requested else next(self._steps)
        except StopIteration as finished:
            result = finished.value
            if (self._shows_progress and 'FINISHED' in result and not self._cancel_requested
                    and self._stage == self._stage_count):
                self._settings.uv_bake_progress = 100
        except UVBakeCancelled:
            self._settings.uv_bake_status = 'UV Bake cancelled'
            result = {'CANCELLED'}
        except Exception as error:
            self._settings.uv_bake_status = f'UV Bake failed: {error}'
            self.report({'ERROR'}, self._settings.uv_bake_status)
            result = {'CANCELLED'}
        else:
            if stage is not None:
                self._settings.uv_bake_status = stage
                if self._shows_progress:
                    self._settings.uv_bake_progress = 100 * self._stage / self._stage_count
                self._stage += 1
                _redraw_bake_ui(context)
            return None
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self._settings.uv_bake_is_running = False
        _redraw_bake_ui(context)
        return result

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            self._cancel_requested = True
        if event.type == 'TIMER':
            if self._cancel_requested and bpy.app.is_job_running('OBJECT_BAKE'):
                return {'PASS_THROUGH'}
            with context.temp_override(scene=self._scene, view_layer=self._view_layer):
                result = self.advance(context)
            if result is not None:
                return result
        return {'PASS_THROUGH'}

    def run_groups(self, context, groups, settings, duplicate, total, modal):
        collection = _new_bake_collection(context) if duplicate else None
        results = []
        error = None
        cancelled = False
        with preserved_selection(context):
            first = 0
            for group in groups:
                try:
                    results.extend((yield from self.run_targets(
                        context, group, settings, collection, first, total, modal,
                    )))
                    first += len(group)
                except UVBakeCancelled:
                    cancelled = True
                    break
                except Exception as failure:
                    error = f'{group[0][0].name}: {str(failure).strip()}'
                    break
        if collection is not None:
            if not results:
                bpy.data.collections.remove(collection)
            else:
                for obj in context.selected_objects:
                    obj.select_set(False)
                for obj in results:
                    obj.select_set(True)
                context.view_layer.objects.active = results[0]
        label = {'BAKE': 'UV Bake', 'CREATE': 'Create New UV', 'PACK': 'Pack to New UV',
                 'PACK_BAKE': 'Pack and UV Bake'}[self.action]
        settings.uv_bake_status = f'{label}: {len(results)}/{total} meshes'
        if cancelled:
            settings.uv_bake_status += ' | Cancelled'
            self.report({'INFO'}, settings.uv_bake_status)
            return {'FINISHED'} if results else {'CANCELLED'}
        if error:
            settings.uv_bake_status += f' | {error}'
            self.report({'WARNING'} if results else {'ERROR'}, settings.uv_bake_status)
            if not results:
                return {'CANCELLED'}
        elif results:
            self.report({'INFO'}, settings.uv_bake_status)
        return {'FINISHED'}

    def run_targets(self, context, group, settings, collection, first, total, modal):
        with ExitStack() as stack:
            label = f'{first + 1}/{total}' if len(group) == 1 else f'{first + 1}–{first + len(group)}/{total}'
            yield f'{label} | Preparing UV maps'
            plans = [stack.enter_context(self.prepare_target(obj, source, target, collection))
                     for obj, source, target in group]
            targets = [target for target, _, _ in plans]
            for target in targets:
                stack.enter_context(export_visibility(context, target))
            if self.action in {'PACK', 'PACK_BAKE'}:
                yield f'{label} | Packing UVs with UVPackmaster'
                _pack_new_maps(context, targets)
            if self.action in {'BAKE', 'PACK_BAKE'}:
                name = targets[0].name
                if len(targets) > 1:
                    stem = (collection.name if collection is not None else name) + '_UVAtlas'
                    name = stem
                    folder = os.path.join(os.path.dirname(bpy.data.filepath), 'Bakes')
                    index = 1
                    while os.path.exists(os.path.join(folder, _safe_path_name(name))) or bpy.data.materials.get('M_' + name):
                        name = f'{stem}.{index:03d}'
                        index += 1
                yield from uv_bake(context, plans, settings, name, first, total, modal,
                                   replace_source=collection is not None,
                                   report=lambda message: self.report({'INFO'}, message))
            elif collection is not None:
                for target, source_uv, target_uv in plans:
                    _replace_source_map(target.data, source_uv, target_uv)
            return targets

    @contextmanager
    def prepare_target(self, obj, source_uv, target_uv, collection):
        target = _duplicate_target(obj, collection) if collection is not None else obj
        original_mesh = target.data
        if collection is None and original_mesh.users > 1:
            target.data = original_mesh.copy()
        layers = target.data.uv_layers
        old_active = layers.active.name if layers.active else ''
        old_render = next((layer.name for layer in layers if layer.active_render), '')
        created = None
        try:
            if target_uv is None:
                layers.active = layers[source_uv]
                created = layers.new(name=source_uv + '_New', do_init=True).name
                target_uv = created
            layers.active = layers[target_uv]
            yield target, source_uv, target_uv
        except Exception:
            if collection is not None:
                _remove_target(target)
            elif target.data != original_mesh:
                working = target.data
                target.data = original_mesh
                bpy.data.meshes.remove(working)
            else:
                if created and layers.get(created):
                    layers.remove(layers[created])
                if old_active and layers.get(old_active):
                    layers.active = layers[old_active]
                if old_render and layers.get(old_render):
                    layers[old_render].active_render = True
            raise
