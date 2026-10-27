"""Optional, selected-asset LOD creation after a manual final rebake."""
import re
import uuid
from types import SimpleNamespace

import bpy

from ..core.asset_names import asset_name
from ..core.lod_naming import lod_name
from .smart_lods import OBJECT_OT_polygroups_generate_smart_lods, LOD_SOURCE, LOD_INDEX, LOD_LABEL
from .unity_preparation import unity_name


class FinalRebakeLODs:
    def __init__(self, context, target):
        self.target = target
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_mesh_finalization_settings
        self.engine = 'UNITY' if p.phase2_run_engine == 'UNITY' else 'UNREAL'
        # Freeze the Phase 2 engine/LOD options; resolve existing MID identity below.
        self.options = {}
        for prop in s.bl_rna.properties:
            name = prop.identifier
            if (name.startswith(('smart_lods_', 'unity_', 'unreal_lod_'))
                    and name not in {'smart_lods_progress', 'smart_lods_status'}
                    and not prop.is_readonly and prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}):
                value = getattr(s, name)
                self.options[name] = tuple(value) if getattr(prop, 'is_array', False) else value
        self.options['smart_lods_prepare_mode'] = self.engine
        self.options['unreal_lod_keep_high'] = False
        # A manual rebake updates an existing asset, so stale Phase 2 identity
        # defaults must not redirect LOD replacement to another asset number.
        identity = re.fullmatch(r'SM_(.+)_(\d+)_(\d+)_MID', target.name, re.IGNORECASE)
        prefix = 'unity_' if self.engine == 'UNITY' else 'unreal_lod_'
        if identity:
            self.options[prefix + 'asset_name'] = identity.group(1)
            self.options[prefix + 'name_index'] = identity.group(2)
            self.options['unity_asset_index' if self.engine == 'UNITY' else
                         'unreal_lod_version_index'] = identity.group(3)
        asset = asset_name(self.options[prefix + 'asset_name'])
        name_index = self.options[prefix + 'name_index']
        version = self.options['unity_asset_index' if self.engine == 'UNITY' else 'unreal_lod_version_index']
        if not asset or not name_index.isdigit() or not version.isdigit():
            raise ValueError('Create LODs: set an Asset Name and numeric indices above Start Phase 2')
        self.options[prefix + 'asset_name'] = asset
        count = self.options['smart_lods_count']
        if self.engine == 'UNITY':
            settings = SimpleNamespace(**self.options)
            base = unity_name(settings, '')
            final_names = [unity_name(settings, f'LOD{i}') for i in range(count)]
            final_pattern = re.escape(base) + r'(?:[._]LOD[._]?\d+)?'
        else:
            base = f'SM_{asset}_{name_index.zfill(2)}_{version.zfill(max(2, len(version)))}'
            final_names = [f'{base}_LOD{i}' for i in range(count)]
            final_pattern = re.escape(base) + r'[._]LOD[._]?\d+'
        self.patterns = [re.compile(final_pattern, re.IGNORECASE), re.compile(
            re.escape(target.name) + r'[._]LOD[._]?\d+', re.IGNORECASE)]
        self.planned = {lod_name(target.name, i, self.engine) for i in range(count)} | set(final_names)
        self.existing(context)  # Validate ownership before starting any bake.

    def existing(self, context):
        old = {obj for obj in context.scene.objects if obj != self.target and obj.type == 'MESH'
               and (any(pattern.fullmatch(obj.name) for pattern in self.patterns)
                    or (obj.get(LOD_SOURCE) == self.target.name
                        and isinstance(obj.get(LOD_INDEX), int) and obj.get(LOD_INDEX) >= 0
                        and obj.get('polygroups_rebake_lod_engine',
                                    'UNREAL' if obj.name.startswith('SM_') and '.LOD' not in obj.name
                                    else 'UNITY') == self.engine))}
        # A similarly named non-mesh or object outside this scene is not a LOD
        # belonging to the active asset and must never be silently removed.
        for name in self.planned:
            collision = bpy.data.objects.get(name)
            if collision is not None and collision not in old:
                raise ValueError('Create LODs: name belongs to another object/scene: ' + name)
        for obj in old:
            if obj.library or any(scene != context.scene for scene in obj.users_scene):
                raise ValueError('Create LODs: existing LOD is linked or shared by another scene: ' + obj.name)
            if any(child.type != 'FONT' for child in obj.children):
                raise ValueError('Create LODs: existing LOD has non-label children: ' + obj.name)
        return old

    def run(self, context, report):
        s = context.scene.polygroups_mesh_finalization_settings
        saved = {name: getattr(s, name)[:] if isinstance(value, tuple) else getattr(s, name)
                 for name, value in self.options.items()}
        selected = [obj.name for obj in context.selected_objects]
        active_name = context.active_object.name if context.active_object else None
        mode = context.object.mode if context.object else 'OBJECT'
        before = set(bpy.data.objects)
        success = False
        replacement = LODReplacement(context, self.existing(context))
        try:
            replacement.stash()
            if replacement.meshes:
                report({'INFO'}, f'ReBake Final Mesh: replacing {len(replacement.meshes)} old LODs for {self.target.name}')
            for name, value in self.options.items():
                setattr(s, name, value)
            if context.object and context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for obj in context.selected_objects:
                obj.select_set(False)
            self.target.select_set(True)
            context.view_layer.objects.active = self.target
            worker = SimpleNamespace(report=report)
            # Reuse single-source generation without batch arrangement of MID.
            for _ in OBJECT_OT_polygroups_generate_smart_lods.source_steps(worker, context):
                pass
            generated = sorted((o for o in set(bpy.data.objects) - before
                                if o.type == 'MESH' and o.get(LOD_SOURCE) == self.target.name),
                               key=lambda o: o.get(LOD_INDEX, 0))
            if len(generated) != self.options['smart_lods_count']:
                raise RuntimeError('Create LODs did not produce the configured number of meshes')
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in generated:
                obj.select_set(True)
            context.view_layer.objects.active = generated[0]
            if self.engine == 'UNITY':
                result = bpy.ops.object.polygroups_prepare_unity('EXEC_DEFAULT', auto_lods=True)
            else:
                result = bpy.ops.object.polygroups_unreal_lod_rename('EXEC_DEFAULT')
            if 'FINISHED' not in result:
                raise RuntimeError(f'Create LODs: {self.engine} preparation failed')
            for obj in generated:
                obj['polygroups_rebake_lod_engine'] = self.engine
            success = True
            report({'INFO'}, f'ReBake Final Mesh: created {len(generated)} {self.engine} LODs')
        finally:
            if not success:
                # Only remove newly generated data; existing scene assets stay intact.
                for obj in list(set(bpy.data.objects) - before):
                    if obj.type in {'MESH', 'FONT'}:
                        data = obj.data
                        kind = obj.type
                        bpy.data.objects.remove(obj, do_unlink=True)
                        if data.users == 0:
                            (bpy.data.meshes if kind == 'MESH' else bpy.data.curves).remove(data)
            replacement.finish(success)
            if success:
                for obj in generated:
                    if obj.data.users == 1:
                        obj.data.name = obj.name
            for name, value in saved.items():
                setattr(s, name, value)
            for obj in context.selected_objects:
                obj.select_set(False)
            for name in selected:
                obj = bpy.data.objects.get(name)
                if obj and obj.name in context.view_layer.objects:
                    obj.select_set(True)
            context.view_layer.objects.active = bpy.data.objects.get(active_name) if active_name else None
            if mode != 'OBJECT' and context.active_object:
                bpy.ops.object.mode_set(mode=mode)
        return generated


def current_asset_lods(context, target):
    """Exact SM_<asset>_LOD<number> siblings, including hidden collections."""
    if not re.fullmatch(r'SM_.+_MID', target.name, re.IGNORECASE):
        raise ValueError('Delete Current LODs requires a final SM_..._MID mesh')
    pattern = re.compile(re.escape(target.name[:-3]) + r'LOD\d+', re.IGNORECASE)
    meshes = {obj for obj in context.scene.objects
              if obj.type == 'MESH' and pattern.fullmatch(obj.name)}
    replacement = LODReplacement(context, meshes)
    for obj in replacement.objects:
        if obj.library or any(scene != context.scene for scene in obj.users_scene):
            raise ValueError('Delete Current LODs: object is linked or shared by another scene: ' + obj.name)
        if any(child not in replacement.objects for child in obj.children):
            raise ValueError('Delete Current LODs: object has an unrelated child: ' + obj.name)
    return meshes


def delete_current_asset_lods(context, target):
    meshes = current_asset_lods(context, target)
    replacement = LODReplacement(context, meshes)
    replacement.stash()
    replacement.finish(True)
    return len(meshes)


class LODReplacement:
    """Keep old LODs recoverable until every replacement has been prepared."""
    def __init__(self, context, meshes):
        self.context = context
        self.meshes = meshes
        names = {obj.name for obj in meshes}
        self.objects = set(meshes) | {obj for obj in context.scene.objects if obj.type == 'FONT'
                        and (obj.parent in meshes or obj.get(LOD_LABEL) in names)}
        self.snapshot = [(obj, obj.name, list(obj.users_collection)) for obj in self.objects]
        self.storage = None

    def stash(self):
        if not self.objects:
            return
        # An unlinked collection keeps originals alive without interfering with
        # the engine preparer's asset-collection membership checks.
        self.storage = bpy.data.collections.new('__ReBake_LOD_Backup_' + uuid.uuid4().hex)
        for obj, name, collections in self.snapshot:
            self.storage.objects.link(obj)
            for collection in collections:
                collection.objects.unlink(obj)
            obj.name = self.storage.name + '_' + name
        self.context.view_layer.update()

    def finish(self, success):
        if self.storage is None:
            return
        if success:
            for obj, name, collections in self.snapshot:
                data, kind = obj.data, obj.type
                bpy.data.objects.remove(obj, do_unlink=True)
                if data.users == 0:
                    (bpy.data.meshes if kind == 'MESH' else bpy.data.curves).remove(data)
        else:
            for obj, name, collections in self.snapshot:
                obj.name = name
                for collection in collections:
                    if obj.name not in collection.objects:
                        collection.objects.link(obj)
        bpy.data.collections.remove(self.storage)
        self.storage = None
        self.context.view_layer.update()
