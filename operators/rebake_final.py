"""Final MID rebakes: deterministic sources, existing outputs, reversible scene setup."""
import json
import hashlib
from array import array
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import bpy

from . import bake_constants as C
from ..core.datablock_names import remove_numbered_files, take_name

MID_PATTERN = re.compile(r'^SM_(.+_(\d+))_MID$', re.IGNORECASE)
CHANNELS = {
    'BaseColor': (C.BAKE_BASE_COLOR_IMAGE_PROP, C.BAKE_SOURCE_BASE_COLOR_IMAGE_PROP, C.BAKE_BASE_COLOR_NODE),
    'Normal': (C.BAKE_NORMAL_IMAGE_PROP, C.BAKE_SOURCE_NORMAL_IMAGE_PROP, C.BAKE_NORMAL_NODE),
    'MergeMask': (C.BAKE_ALPHA_IMAGE_PROP, C.BAKE_SOURCE_ALPHA_IMAGE_PROP, C.BAKE_ALPHA_NODE),
    'ArtifactMask': (C.BAKE_ARTIFACT_IMAGE_PROP, None, 'PolyGroups Bake Artifact Mask'),
}


def uv_signature(mesh):
    signature = hashlib.blake2b()
    for layer in mesh.uv_layers:
        values = array('f',[0]) * (len(layer.data)*2)
        layer.data.foreach_get('uv',values)
        signature.update(layer.name.encode('utf-8'))
        signature.update(len(values).to_bytes(8,'little'))
        signature.update(values.tobytes())
    return signature.digest()


def final_asset_name(target):
    match = MID_PATTERN.fullmatch(target.name) if target and target.type == 'MESH' else None
    if not match:
        raise ValueError('Select a final mesh named SM_..._NN_MID')
    return match.group(1), int(match.group(2))


class MissingFinalSourceError(ValueError):
    pass


def resolve_final_source(context, target, use_selection=True):
    from .rebake_source import COLLECTION_PATTERN, preferred_source_name
    asset, index = final_asset_name(target)
    selected = [obj for obj in context.selected_objects if obj.type == 'MESH' and obj != target] if use_selection else []
    if selected:
        if context.active_object != target or target not in context.selected_objects or len(selected) != 1:
            raise ValueError('Select one Highpoly and make the final MID mesh active')
        source = selected[0]
    else:
        collections = [col for col in context.scene.collection.children_recursive
                       if (match := COLLECTION_PATTERN.fullmatch(col.name)) and int(match[1]) == index]
        canonical = [col for col in collections if col.name == f'Generated.{index:03d}']
        collections = canonical or collections
        if not collections:
            raise MissingFinalSourceError(f'Generated.{index:03d}: collection not found in this scene')
        if len(collections) != 1:
            raise ValueError(f'Ambiguous Generated collections for {asset}')
        collection = collections[0]
        candidates = {obj.name: obj for obj in collection.all_objects if obj.type == 'MESH' and obj != target}
        source = candidates[preferred_source_name(candidates, index, collection.name)]
    if (source.library or source.data.library or source.data.users != 1
            or target.library or target.data.library or target.data.users != 1):
        raise ValueError('ReBake requires local objects and a single-user final mesh')
    return source


def _image_path(image):
    return Path(bpy.path.abspath(image.filepath, library=image.library)).resolve()


def _channel_images(target, expected):
    """Every image in the MID materials that stands for one final channel."""
    images = set()
    for material in target.data.materials:
        if material and material.node_tree:
            for node in material.node_tree.nodes:
                image = node.image if node.type == 'TEX_IMAGE' else None
                if image and (image.name == expected or (image.filepath and _image_path(image).stem == expected)):
                    images.add(image)
    return images


def _reusable(image):
    path = _image_path(image) if image.filepath else None
    return (not image.library and image.source in {'FILE', 'GENERATED'} and path is not None
            and path.suffix.lower() == '.png' and path.is_file())


def final_texture_outputs(target, settings):
    """Pick final output paths; the MID's current textures are optional.

    ReBake overwrites the final textures and rewires the material, so missing,
    duplicated, packed-only or non-PNG images never block it. A reusable PNG
    keeps its file and folder; otherwise T_<asset>_<channel>.png is written
    next to the other final textures or into Textures/<asset> of the blend.
    """
    asset, _ = final_asset_name(target)
    if not (settings.bake_base_color or settings.bake_normal):
        raise ValueError('Enable Base Color or Normal before ReBake')
    if not target.data.uv_layers.active:
        raise ValueError('Final mesh needs an existing UV map')
    found = {}
    for channel in CHANNELS:
        expected = f'T_{asset}_{channel}'
        reusable = sorted((image for image in _channel_images(target, expected) if _reusable(image)),
                          key=lambda image: (image.name != expected, image.name))
        if reusable:
            found[channel] = reusable[0]
    if found:
        folder = _image_path(next(iter(found.values()))).parent
    elif bpy.data.filepath:
        folder = Path(bpy.data.filepath).parent / 'Textures' / asset
    else:
        raise ValueError('Save the blend file before ReBake: final textures need a folder')
    outputs = {channel: (found[channel], _image_path(found[channel])) if channel in found
               else (None, folder / f'T_{asset}_{channel}.png') for channel in CHANNELS}
    sizes = {tuple(found[channel].size) for channel in ('BaseColor', 'Normal') if channel in found}
    sizes = {size for size in sizes if size[0] == size[1] and size[0] >= 16}
    resolution = next(iter(sizes))[0] if len(sizes) == 1 else settings.bake_resolution
    return outputs, resolution


def final_material(target, asset):
    """The MID's first material; a MID without one gets a fresh node material."""
    material = target.data.materials[0] if target.data.materials else None
    if material is None:
        material = bpy.data.materials.new(f'M_{asset}')
        if target.data.materials:
            target.data.materials[0] = material
        else:
            target.data.materials.append(material)
    material.use_nodes = True
    return material


def wire_channel(material, node, channel):
    """Connect a newly created final texture to the Principled BSDF."""
    tree = material.node_tree
    bsdf = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        bsdf = tree.nodes.new('ShaderNodeBsdfPrincipled')
        output = next((n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL'), None) \
            or tree.nodes.new('ShaderNodeOutputMaterial')
        tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    if channel == 'BaseColor':
        tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    elif channel == 'Normal':
        normal_map = tree.nodes.get('PolyGroups Bake Normal Map') or tree.nodes.new('ShaderNodeNormalMap')
        normal_map.name = 'PolyGroups Bake Normal Map'
        tree.links.new(node.outputs['Color'], normal_map.inputs['Color'])
        tree.links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])


class FinalRebakeSession:
    def __init__(self, context, target, settings, create_lods=False, export_selected=False, repair_mesh=False,
                 delete_current_lods=False, use_selection=True):
        self.context, self.target, self.settings = context, target, settings
        self.repair_mesh = repair_mesh
        self.delete_lods_before_bake = delete_current_lods
        self.source_import = None
        self.source = None
        try:
            self.source = resolve_final_source(context, target, use_selection=use_selection)
        except MissingFinalSourceError:
            from .rebake_source import TemporaryRebakeSource
            self.source_import = TemporaryRebakeSource(final_asset_name(target)[1])
        if target.library or target.data.library or target.data.users != 1:
            raise ValueError('ReBake requires a local single-user final mesh')
        if repair_mesh and target.data.shape_keys:
            raise ValueError('ReBake Repair Mesh requires a mesh without shape keys')
        self.outputs, self.resolution = final_texture_outputs(target, settings)
        asset = final_asset_name(target)[0]
        # Duplicates / unusable copies of a channel get remapped to the new image.
        self.stale_images = {channel: _channel_images(target, f'T_{asset}_{channel}') - {image}
                             for channel, (image, _) in self.outputs.items()}
        if delete_current_lods:
            from .rebake_lods import current_asset_lods
            current_asset_lods(context, target)  # Read-only ownership preflight.
        from .rebake_lods import FinalRebakeLODs
        self.lod_job = FinalRebakeLODs(context, target) if create_lods else None
        self.export_selected = export_selected
        self.export_collection = None
        if export_selected:
            if not create_lods:
                raise ValueError('Enable Create LODs before Export Selected FBX / Blend')
            if not bpy.data.filepath:
                raise ValueError('Save the working blend before exporting FBX / Blend')
            s = context.scene.polygroups_mesh_finalization_settings
            if self.lod_job.engine == 'UNITY' and not s.unity_export_directory.strip():
                raise ValueError('Choose a Unity export directory before exporting FBX / Blend')
            from .rebake_export import rebake_asset_collection
            self.export_collection = rebake_asset_collection(context, target)
            if self.source_import is not None:
                from .phase2_blend_export import BLEND_FOLDER, blend_file_stem
                destination = (Path(bpy.data.filepath).parent / BLEND_FOLDER /
                               (blend_file_stem(self.export_collection) + '.blend'))
                if destination.resolve() == self.source_import.path.resolve():
                    raise ValueError('Final Blend export would overwrite the Highpoly source; '
                                     'put the MID in its final asset _Collection first')
            # Engine preparation may otherwise leave copied LOD textures as
            # generated-only images, which the FBX texture exporter cannot read.
            self.lod_job.options['unreal_lod_copy_textures'] = True
            self.lod_job.options['unity_copy_textures'] = True
        self.packed_outputs = {channel: bool(image and image.packed_file)
                               for channel, (image, _) in self.outputs.items()}
        self.token = 'ReBake_' + uuid.uuid4().hex
        self.saved_settings = {}
        self.attributes = []
        self.objects = []
        self.slots = []
        self.created_materials = []
        self.started = False
        self.closed = False
        self.target_prepared = False
        self.frozen_source = None

    def set_attribute(self, owner, name, value):
        self.attributes.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    def delete_current_lods(self):
        if not self.delete_lods_before_bake:
            return 0
        from .rebake_lods import delete_current_asset_lods
        return delete_current_asset_lods(self.context, self.target)

    def repair_target(self):
        p = self.context.scene.polygroups_model_preparation_settings
        pending_pack = p.phase2_rebake_repack_uv and self.target.get('polygroups_rebake_uv_needs_pack')
        if not self.repair_mesh and not pending_pack:
            self.target_prepared = True
            return
        from .phase2_zbrush_export import preserved_selection, export_visibility
        context,target = self.context,self.target
        p = context.scene.polygroups_model_preparation_settings
        mode = context.object.mode if context.object else 'OBJECT'
        if mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            with preserved_selection(context),export_visibility(context,target):
                bpy.ops.object.select_all(action='DESELECT')
                target.select_set(True)
                context.view_layer.objects.active = target
                before = uv_signature(target.data)
                if self.repair_mesh:
                    result = bpy.ops.mesh.polygroups_repair_mesh_folds('EXEC_DEFAULT', action='REPAIR',
                        fix_folds=p.phase2_rebake_repair_folds,
                        fix_degenerate=p.phase2_rebake_repair_coincident,
                        fix_zero_area=p.phase2_rebake_repair_zero_area,
                        fix_stretched_triangles=p.phase2_rebake_repair_stretched,
                        fix_dangling=p.fold_repair_dangling,
                        stretched_triangle_ratio=p.fold_repair_stretch_ratio, selected_only=False)
                    if 'FINISHED' not in result:
                        raise RuntimeError('ReBake Final Mesh: Auto Repair failed for ' + target.name)
                if uv_signature(target.data) != before:
                    target['polygroups_rebake_uv_needs_pack'] = True
                if p.phase2_rebake_repack_uv and target.get('polygroups_rebake_uv_needs_pack'):
                    if 'FINISHED' not in bpy.ops.object.polygroups_uvpackmaster_pack('EXEC_DEFAULT'):
                        raise RuntimeError('ReBake Final Mesh: UV repack after repair failed for ' + target.name)
                    del target['polygroups_rebake_uv_needs_pack']
                target.data.update()
                context.view_layer.update()
                self.target_prepared = True
        finally:
            if mode == 'EDIT' and context.active_object == target and target.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')

    def freeze_source_geometry(self):
        """Use one evaluated Multires surface/UV for every bake/diagnostic pass.

        Multires can resample evaluated UVs differently after shader overrides.
        Keep the original object identity, data and modifier settings recoverable.
        """
        source = self.source
        if not any(mod.type == 'MULTIRES' and mod.show_viewport for mod in source.modifiers):
            return
        self.context.view_layer.update()
        graph = self.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(source.evaluated_get(graph),
                                              preserve_all_data_layers=True, depsgraph=graph)
        mesh.name = self.token + '_FrozenHighpoly'
        flags = [(mod, mod.show_viewport, mod.show_render) for mod in source.modifiers]
        self.frozen_source = (source.data, mesh, flags)
        for mod, _, _ in flags:
            mod.show_viewport = mod.show_render = False
        source.data = mesh
        self.context.view_layer.update()

    def restore_source_geometry(self):
        if self.frozen_source is None:
            return
        original, mesh, flags = self.frozen_source
        self.source.data = original
        for mod, viewport, render in flags:
            mod.show_viewport, mod.show_render = viewport, render
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        self.frozen_source = None

    def begin(self):
        # All target fixes and packing finish before source/material setup and
        # before any projection fingerprint or native bake can be created.
        if not self.target_prepared:
            self.repair_target()
        if self.source_import is not None:
            self.source = self.source_import.load(self.context)
        context, target, source = self.context, self.target, self.source
        self.properties = {k: v for k, v in target.items() if k.startswith('polygroups_bake_') or k == 'polygroups_projection_run'}
        self.source_matrix = source.matrix_world.copy()
        self.selection = list(context.selected_objects)
        self.active = context.view_layer.objects.active
        self.mode = target.mode
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        self.polygon_materials = [p.material_index for p in target.data.polygons]
        self.active_material = target.active_material_index
        for obj in (target, source):
            self.slots.append((obj, list(obj.data.materials)))
        self.started = True
        target.data.materials.clear()
        # Reveal every ancestor collection along a path to the two objects.
        visibility = []
        relevant_layers = []
        def all_layers(layer):
            yield layer
            for child in layer.children:
                yield from all_layers(child)
        self.attributes.extend((layer, 'exclude', layer.exclude)
                               for layer in all_layers(context.view_layer.layer_collection))
        def collect_visibility(layer):
            if not any(o.name in layer.collection.all_objects for o in (target, source)):
                return
            relevant_layers.append(layer)
            for owner, name in ((layer, 'hide_viewport'),
                                (layer.collection, 'hide_viewport'), (layer.collection, 'hide_render'),
                                (layer.collection, 'hide_select')):
                visibility.append((owner, name, getattr(owner, name)))
            for child in layer.children:
                collect_visibility(child)
        collect_visibility(context.view_layer.layer_collection)
        # Snapshot descendants before unexcluding any parent (which propagates).
        self.attributes.extend(visibility)
        for layer in relevant_layers:
            if layer.exclude:
                layer.exclude = False
        for owner, name, _ in visibility:
            setattr(owner, name, False)
        context.view_layer.update()
        for obj in (target, source):
            self.objects.append((obj, obj.hide_get(view_layer=context.view_layer)))
            for name in ('hide_viewport', 'hide_render', 'hide_select'):
                self.set_attribute(obj, name, False)
            obj.hide_set(False, view_layer=context.view_layer)
        for modifier in source.modifiers:
            if modifier.type == 'MULTIRES':
                self.set_attribute(modifier, 'show_viewport', True)
                self.set_attribute(modifier, 'show_render', True)
                self.set_attribute(modifier, 'levels', modifier.render_levels)
            else:
                self.set_attribute(modifier, 'show_viewport', modifier.show_render)
                if modifier.type == 'SUBSURF':
                    self.set_attribute(modifier, 'levels', modifier.render_levels)
        # Align translation only: retain each mesh's rotation, scale and vertices.
        matrix = source.matrix_world.copy()
        matrix.translation = target.matrix_world.translation
        source.matrix_world = matrix
        # Prepare source materials on copies, so AutoBake's rewiring is temporary.
        for i, material in enumerate(list(source.data.materials)):
            if material:
                copy = material.copy()
                copy.name = self.token + '_Source'
                self.created_materials.append(copy)
                source.data.materials[i] = copy
        overrides = dict(image_prefix=self.token, bake_resolution=self.resolution,
                         auto_fix_generated_index=False, auto_pack_uv_before_bake=False,
                         use_selected_to_active=True, auto_save_textures_after_bake=False,
                         disable_highpoly_after_bake=False)
        for name, value in overrides.items():
            self.saved_settings[name] = getattr(self.settings, name)
            setattr(self.settings, name, value)
        for key in self.properties:
            if key in target:
                del target[key]
        for obj in context.selected_objects:
            obj.select_set(False)
        source.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        context.view_layer.update()
        self.freeze_source_geometry()

    def save(self):
        """Stage all outputs, then replace files; roll back replacements on error."""
        from ..core.bake_projection import save_mask_png, META_PROP
        target = self.target
        staged, committed = [], []
        self.results = {}
        try:
            for channel, (prop, _, _) in CHANNELS.items():
                if channel == 'BaseColor' and not self.settings.bake_base_color:
                    continue
                if channel == 'Normal' and not self.settings.bake_normal:
                    continue
                if channel == 'ArtifactMask' and not self.settings.bake_artifact_mask:
                    continue
                work = bpy.data.images.get(target.get(prop, ''))
                if work is None:
                    raise ValueError(f'ReBake did not produce {channel}')
                original, path = self.outputs[channel]
                path.parent.mkdir(parents=True, exist_ok=True)
                folder = Path(tempfile.mkdtemp(prefix='.rebake-', dir=str(path.parent)))
                temporary, backup = folder / path.name, folder / 'original.png'
                staged.append((path, temporary, backup, folder))
                if path.exists():
                    shutil.copy2(path, backup)
                work.filepath_raw, work.file_format = str(temporary), 'PNG'
                if channel == 'ArtifactMask':
                    metadata = json.loads(work.get(META_PROP, '{}'))
                    normal = self.outputs.get('Normal', (None, None))[0]
                    metadata['normal'] = normal.name if normal else ''
                    work[META_PROP] = json.dumps(metadata, sort_keys=True)
                    save_mask_png(work, str(temporary))
                else:
                    work.save()
                self.results[channel] = (work, original, path)
            # Commit the sidecar together with its mask.
            for path, temporary, backup, folder in list(staged):
                sidecar = Path(str(temporary) + '.json')
                if sidecar.exists():
                    destination = Path(str(path) + '.json')
                    side_backup = folder / 'original.json'
                    if destination.exists():
                        shutil.copy2(destination, side_backup)
                    staged.append((destination, sidecar, side_backup, folder))
            for path, temporary, backup, folder in staged:
                os.replace(temporary, path)
                committed.append((path, backup))
        except Exception:
            for path, backup in reversed(committed):
                if backup.exists():
                    os.replace(backup, path)
                elif path.exists():
                    path.unlink()
            raise
        finally:
            for folder in {item[3] for item in staged}:
                shutil.rmtree(folder)

    def close(self, success):
        if self.closed:
            return
        if not self.started:
            self.closed = True
            self.cleanup_import()
            return
        self.closed = True
        target, context = self.target, self.context
        self.restore_source_geometry()
        work_material = target.data.materials[0] if target.data.materials else None
        for obj, materials in self.slots:
            obj.data.materials.clear()
            for material in materials:
                obj.data.materials.append(material)
        for polygon, index in zip(target.data.polygons, self.polygon_materials):
            polygon.material_index = index
        target.active_material_index = self.active_material
        run = target.get('polygroups_projection_run')
        for key in list(target.keys()):
            if key.startswith('polygroups_bake_') or key == 'polygroups_projection_run':
                del target[key]
        for key, value in self.properties.items():
            target[key] = value
        try:
            if success:
                from ..core.bake_projection import seal_mask
                asset, _ = final_asset_name(target)
                for channel, (work, original, path) in self.results.items():
                    image = original or bpy.data.images.load(str(path), check_existing=True)
                    packed = (self.packed_outputs[channel] if original else
                              any(self.packed_outputs.get(c) for c in ('BaseColor', 'Normal')))
                    # Reload must read the new PNG, not the old packed bytes.
                    if image.packed_file:
                        image.unpack(method='REMOVE')
                    image.filepath_raw = bpy.path.relpath(str(path))
                    image.reload()
                    # The new final texture replaces every stale copy of this channel
                    # (T_<asset>_<channel>.001 ...): users are remapped, the copies removed.
                    for stale in self.stale_images.get(channel, set()) - {image}:
                        try:
                            if stale.library is None:
                                stale.user_remap(image)
                                bpy.data.images.remove(stale)
                        except ReferenceError:
                            pass
                    take_name(bpy.data.images, image, f'T_{asset}_{channel}', replace=True)
                    remove_numbered_files(path)
                    if channel != 'BaseColor':
                        image.colorspace_settings.name = 'Non-Color'
                    image.filepath_raw = bpy.path.relpath(str(path))
                    for key, value in work.items():
                        image[key] = value
                    if packed:
                        image.pack()
                    prop, source_prop, node_name = CHANNELS[channel]
                    target[prop] = image.name
                    if source_prop:
                        target[source_prop] = image.name
                    material = final_material(target, asset)
                    node = material.node_tree.nodes.get(node_name)
                    if node is None:
                        node = material.node_tree.nodes.new('ShaderNodeTexImage')
                        node.name = node_name
                    node.image = image
                    if original is None:
                        wire_channel(material, node, channel)
                if run:
                    target['polygroups_projection_run'] = run
                if target.data.materials and target.data.materials[0]:
                    target[C.BAKE_TARGET_MATERIAL_PROP] = target.data.materials[0].name
                seal_mask(target)
        finally:
            for name, value in self.saved_settings.items():
                setattr(self.settings, name, value)
            self.source.matrix_world = self.source_matrix
            for owner, name, value in reversed(self.attributes):
                if name != 'exclude':
                    setattr(owner, name, value)
            # Exclusion propagates to descendants in Blender. Restore parents
            # first, then each child's explicit original exclusion state.
            for owner, name, value in self.attributes:
                if name == 'exclude':
                    setattr(owner, name, value)
            for obj, hidden in self.objects:
                obj.hide_set(hidden, view_layer=context.view_layer)
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in self.selection:
                obj.select_set(True)
            context.view_layer.objects.active = self.active
            for material in [work_material, *self.created_materials]:
                if material and material.name.startswith(self.token) and material.users == 0:
                    bpy.data.materials.remove(material)
            for image in list(bpy.data.images):
                if image.name.startswith(self.token) and image.users == 0:
                    bpy.data.images.remove(image)
            context.view_layer.update()
            if self.mode == 'EDIT' and context.active_object == target:
                bpy.ops.object.mode_set(mode='EDIT')

    def cleanup_import(self):
        if self.source_import is not None:
            self.source_import.cleanup()


def rebake_dispatch(context, use_queue):
    """One dispatch decision shared by the review and actual launch."""
    queue = context.scene.polygroups_model_preparation_settings.phase2_rebake_queue
    selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
    queued = {entry.target for entry in queue if entry.target}
    active = context.active_object
    explicit = (active is not None and MID_PATTERN.fullmatch(active.name) and
                len(selected) == 2 and not set(selected).issubset(queued) and
                not any(obj.get('polygroups_lod_source') for obj in selected if obj != active))
    queued_run = bool(use_queue and queue and not explicit)
    return queued_run, [entry.target for entry in queue] if queued_run else [active]


def rebake_review(context, operator):
    """Read-only preflight: never append source IDs or modify meshes/files."""
    queued, targets = rebake_dispatch(context, operator.use_queue)
    rows, signature = [], []
    for target in targets:
        row = dict(target=target.name if target else 'Missing mesh', source='', error='')
        try:
            if target is None or target.name not in context.scene.objects:
                raise ValueError('Mesh is missing from the current scene')
            session = FinalRebakeSession(context, target, context.scene.polygroups_baking_settings,
                create_lods=operator.create_lods, export_selected=operator.export_selected,
                repair_mesh=operator.repair_mesh, delete_current_lods=operator.delete_current_lods,
                use_selection=not queued)
            if session.source_import:
                imported = session.source_import
                row['source'] = str(imported.path) + ' / ' + imported.collection_name
                source_key = ('FILE', str(imported.path), imported.collection_name)
            else:
                row['source'] = session.source.name
                source_key = ('MESH', session.source.as_pointer(), session.source.name)
            signature.append((target.as_pointer(), target.name, source_key))
        except (ValueError, RuntimeError) as error:
            row['error'] = str(error)
        rows.append(row)
    return dict(queued=queued, rows=rows, signature=(queued, tuple(signature)))


class OBJECT_OT_polygroups_rebake_final_mesh(bpy.types.Operator):
    bl_idname = 'object.polygroups_rebake_final_mesh'
    bl_label = 'ReBake Selected Final Mesh'
    bl_description = 'Rebake selected Highpoly onto the active MID, or find Highpoly in Generated.N locally and then in !Blend'
    bl_options = {'REGISTER', 'UNDO'}

    create_lods: bpy.props.BoolProperty(name='Create LODs', default=False, options={'SKIP_SAVE'},
        description='Create LODs after a successful rebake using the Phase 2 pipeline and asset settings')
    export_selected: bpy.props.BoolProperty(name='Export Selected FBX / Blend', default=False, options={'SKIP_SAVE'},
        description='After Create LODs, select current asset meshes and replace their FBX and Blend exports')
    repair_mesh: bpy.props.BoolProperty(name='Repair Mesh', default=False, options={'SKIP_SAVE'})
    delete_current_lods: bpy.props.BoolProperty(name='Delete Current LODs Before ReBake', default=False, options={'SKIP_SAVE'})
    use_queue: bpy.props.BoolProperty(default=False, options={'HIDDEN','SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, 'polygroups_baking_settings', None)
        target = context.active_object
        p = getattr(context.scene, 'polygroups_model_preparation_settings', None)
        from .sequential_jobs import ACTIVE_JOB
        busy = p and any(getattr(p, name) for name in ('phase2_pipeline_running', 'phase2_is_running',
                        'phase2_final_is_running', 'phase2_auto_render_running', 'batch_is_running',
                        'phase2_rebake_queue_running'))
        valid_target = target and target.type == 'MESH' and MID_PATTERN.fullmatch(target.name)
        return bool(settings and not settings.bake_task_is_running and (valid_target or (p and len(p.phase2_rebake_queue)))
                    and not busy and ACTIVE_JOB is None)

    def execute(self, context):
        # The common task owns setup/cleanup for both modal and background runs.
        try:
            reviewed = getattr(self, '_rebake_review', None)
            if reviewed is not None:
                current = rebake_review(context, self)
                errors = [row['error'] for row in current['rows'] if row['error']]
                if errors:
                    raise ValueError('; '.join(errors))
                if current['signature'] != reviewed['signature']:
                    raise ValueError('ReBake selection, queue or Highpoly changed; reopen the confirmation window')
            queued, _targets = rebake_dispatch(context, self.use_queue)
            if queued:
                return bpy.ops.object.polygroups_rebake_queue_run('EXEC_DEFAULT',
                    repair_mesh=self.repair_mesh, create_lods=self.create_lods, export_selected=self.export_selected,
                    delete_current_lods=self.delete_current_lods)
            return bpy.ops.object.polygroups_bake_task('INVOKE_DEFAULT', prepare_materials=True,
                        rebake_final=True, rebake_create_lods=self.create_lods,
                        rebake_export_selected=self.export_selected, rebake_repair_mesh=self.repair_mesh,
                        rebake_delete_current_lods=self.delete_current_lods)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

    def invoke(self, context, event):
        self._rebake_review = rebake_review(context, self)
        return context.window_manager.invoke_props_dialog(self, width=640,
            title='Проверка ReBake Final Mesh', confirm_text='Запустить')

    def draw(self, context):
        layout = self.layout
        review = self._rebake_review
        rows = review['rows']
        # The mesh / Highpoly source list is collapsed by default; errors stay visible below.
        header, body = layout.panel('polygroups_rebake_review_sources', default_closed=True)
        header.label(text=('Очередь ReBake' if review['queued'] else 'Выбранный объект')
                     + f': исходные файлы для запечки ({len(rows)})', icon='OUTLINER_OB_MESH')
        if body is not None:
            for index, item in enumerate(rows, 1):
                box = body.box()
                box.label(text=f'{index}. {item["target"]}', icon='MESH_DATA')
                if item['source']:
                    box.label(text='Highpoly: ' + item['source'])
        for index, item in enumerate(rows, 1):
            if item['error']:
                row = layout.row()
                row.alert = True
                row.label(text=f'{index}. {item["target"]}: {item["error"]}', icon='ERROR')
        layout.label(text='Существующие текстуры будут перезаписаны.', icon='ERROR')
        for enabled, text in ((self.repair_mesh, 'Исправление меша перед ReBake'),
                (self.delete_current_lods, 'Удаление текущих LOD перед ReBake'),
                (self.create_lods, 'Создание LOD после ReBake'),
                (self.export_selected, 'Перезапись экспорта FBX / Blend')):
            if enabled:
                layout.label(text=text, icon='CHECKMARK')
        if any(item['error'] for item in review['rows']):
            layout.label(text='Устраните ошибки перед запуском.', icon='CANCEL')
