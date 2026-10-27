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

MID_PATTERN = re.compile(r'^SM_(.+_(\d+))_MID$', re.IGNORECASE)
SOURCE_PATTERN = re.compile(r'^Resculpting_01_Highpoly_Generated(?:\.(\d+))?$', re.IGNORECASE)
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


def resolve_final_source(context, target):
    asset, index = final_asset_name(target)
    candidates = []
    for obj in context.scene.objects:
        match = SOURCE_PATTERN.fullmatch(obj.name)
        if obj.type == 'MESH' and match and int(match.group(1) or 0) == index:
            candidates.append(obj)
    if len(candidates) != 1:
        expected = f'Resculpting_01_Highpoly_Generated.{index:03d}'
        reason = 'not found in this scene' if not candidates else 'ambiguous (multiple matching sources)'
        error = MissingFinalSourceError if not candidates else ValueError
        raise error(f'{expected}: {reason}; keep exactly one matching Highpoly in the scene')
    source = candidates[0]
    owners = [int(c.name.split('.')[-1]) for c in source.users_collection
              if re.fullmatch(r'Generated\.\d+', c.name, re.IGNORECASE)]
    if owners and index not in owners:
        raise ValueError(f'{source.name}: Generated collection index does not match {asset}')
    if (source.library or source.data.library or source.data.users != 1
            or target.library or target.data.library or target.data.users != 1):
        raise ValueError('ReBake requires local objects and a single-user final mesh')
    return source


def final_texture_outputs(target, settings):
    """Material references own final paths; stale Bake_Temp ID properties do not."""
    asset, _ = final_asset_name(target)
    outputs = {}
    for channel in CHANNELS:
        expected = f'T_{asset}_{channel}'
        matches = set()
        for material in target.data.materials:
            if material and material.node_tree:
                for node in material.node_tree.nodes:
                    image = node.image if node.type == 'TEX_IMAGE' else None
                    if image and (image.name == expected or Path(bpy.path.abspath(image.filepath, library=image.library)).stem == expected):
                        matches.add(image)
        required = ((channel == 'BaseColor' and settings.bake_base_color)
                    or (channel == 'Normal' and settings.bake_normal))
        if len(matches) > 1 or (required and not matches):
            raise ValueError(f'{expected}: expected one existing image referenced by the final material')
        if matches:
            image = matches.pop()
            path = Path(bpy.path.abspath(image.filepath, library=image.library)).resolve()
            if image.library or image.source not in {'FILE', 'GENERATED'} or not image.filepath or not path.is_file():
                raise ValueError(f'{expected}: save the existing final texture to a local file first')
            if path.suffix.lower() != '.png':
                raise ValueError(f'{expected}: final rebake currently requires PNG textures')
            outputs[channel] = (image, path)
    enabled = [outputs[channel] for channel, flag in
               (('BaseColor', settings.bake_base_color), ('Normal', settings.bake_normal)) if flag]
    if not enabled:
        raise ValueError('Enable Base Color or Normal before ReBake')
    sizes = {tuple(image.size) for image, _ in enabled}
    if len(sizes) != 1 or any(w != h or w < 16 for w, h in sizes):
        raise ValueError('Final bake textures must have matching square resolutions of at least 16 pixels')
    if not target.data.uv_layers.active or not target.data.materials:
        raise ValueError('Final mesh needs an existing UV map and material')
    folder = enabled[0][1].parent
    for channel in ('MergeMask', 'ArtifactMask'):
        outputs.setdefault(channel, (None, folder / f'T_{asset}_{channel}.png'))
    return outputs, next(iter(sizes))[0]


class FinalRebakeSession:
    def __init__(self, context, target, settings, create_lods=False, export_selected=False, repair_mesh=False):
        self.context, self.target, self.settings = context, target, settings
        self.repair_mesh = repair_mesh
        self.source_import = None
        self.source = None
        try:
            self.source = resolve_final_source(context, target)
        except MissingFinalSourceError:
            from .rebake_source import TemporaryRebakeSource
            self.source_import = TemporaryRebakeSource(final_asset_name(target)[1])
        if target.library or target.data.library or target.data.users != 1:
            raise ValueError('ReBake requires a local single-user final mesh')
        if repair_mesh and target.data.shape_keys:
            raise ValueError('ReBake Repair Mesh requires a mesh without shape keys')
        self.outputs, self.resolution = final_texture_outputs(target, settings)
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

    def set_attribute(self, owner, name, value):
        self.attributes.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    def repair_target(self):
        if not self.repair_mesh:
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
                result = bpy.ops.mesh.polygroups_repair_mesh_folds('EXEC_DEFAULT', action='REPAIR',
                    fix_folds=p.phase2_rebake_repair_folds,
                    fix_degenerate=p.phase2_rebake_repair_coincident,
                    fix_zero_area=p.phase2_rebake_repair_zero_area,
                    fix_stretched_triangles=p.phase2_rebake_repair_stretched,
                    stretched_triangle_ratio=p.fold_repair_stretch_ratio, selected_only=False)
                if 'FINISHED' not in result:
                    raise RuntimeError('ReBake Final Mesh: Auto Repair failed for ' + target.name)
                if uv_signature(target.data) != before:
                    target['polygroups_rebake_uv_needs_pack'] = True
                if p.phase2_rebake_repack_uv and target.get('polygroups_rebake_uv_needs_pack'):
                    if 'FINISHED' not in bpy.ops.object.polygroups_uvpackmaster_pack('EXEC_DEFAULT'):
                        raise RuntimeError('ReBake Final Mesh: UV repack after repair failed for ' + target.name)
                    del target['polygroups_rebake_uv_needs_pack']
        finally:
            if mode == 'EDIT' and context.active_object == target and target.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')

    def begin(self):
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
                if not path.parent.is_dir():
                    raise ValueError(f'Texture directory is unavailable: {path.parent}')
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
                    image.name = f'T_{asset}_{channel}'
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
                    material = target.data.materials[0]
                    node = material.node_tree.nodes.get(node_name)
                    if node is None:
                        node = material.node_tree.nodes.new('ShaderNodeTexImage')
                        node.name = node_name
                    node.image = image
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


class OBJECT_OT_polygroups_rebake_final_mesh(bpy.types.Operator):
    bl_idname = 'object.polygroups_rebake_final_mesh'
    bl_label = 'ReBake Final Mesh'
    bl_description = 'Find the numbered Resculpting Highpoly, align it and rebake into the existing final texture files'
    bl_options = {'REGISTER', 'UNDO'}

    create_lods: bpy.props.BoolProperty(name='Create LODs', default=False, options={'SKIP_SAVE'},
        description='Create LODs after a successful rebake using the Phase 2 pipeline and asset settings')
    export_selected: bpy.props.BoolProperty(name='Export Selected FBX / Blend', default=False, options={'SKIP_SAVE'},
        description='After Create LODs, select current asset meshes and replace their FBX and Blend exports')
    repair_mesh: bpy.props.BoolProperty(name='Repair Mesh', default=False, options={'SKIP_SAVE'})
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
            if self.use_queue and len(context.scene.polygroups_model_preparation_settings.phase2_rebake_queue):
                return bpy.ops.object.polygroups_rebake_queue_run('EXEC_DEFAULT',
                    repair_mesh=self.repair_mesh, create_lods=self.create_lods, export_selected=self.export_selected)
            return bpy.ops.object.polygroups_bake_task('INVOKE_DEFAULT', prepare_materials=True,
                        rebake_final=True, rebake_create_lods=self.create_lods,
                        rebake_export_selected=self.export_selected, rebake_repair_mesh=self.repair_mesh)
        except RuntimeError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
