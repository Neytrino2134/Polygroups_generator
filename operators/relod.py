"""Recreate scene MID/HIGH LOD packs without rebaking or changing sources."""
import re
from contextlib import closing, ExitStack
from types import SimpleNamespace

import bpy

from ..core.lod_naming import lod_base, lod_name
from ..settings.preparation import engine_lod_targets
from .rebake_lods import LODReplacement
from .sequential_jobs import SequentialJob
from .smart_lods import OBJECT_OT_polygroups_generate_smart_lods, LOD_SOURCE, LOD_INDEX


def scene_sources(context):
    families = {}
    for obj in context.scene.objects:
        if obj.type != 'MESH' or not re.search(r'_(MID|HIGH)$', obj.name, re.I):
            continue
        base = lod_base(obj.name, 'UNREAL')
        current = families.get(base.casefold())
        if current is not None and current.name[-4:].upper() == obj.name[-4:].upper():
            raise ValueError('ReLOD: ambiguous source family: ' + base)
        if current is None or obj.name.upper().endswith('_MID'):
            families[base.casefold()] = obj
    return sorted(families.values(), key=lambda obj: obj.name.casefold())


def triangles(obj):
    return sum(len(polygon.vertices) - 2 for polygon in obj.data.polygons)


def selected_sources(context, sources):
    """Scene sources owning the selection: a selected MID/HIGH or any of its LODs."""
    families = {lod_base(src.name, 'UNREAL').casefold(): src for src in sources}
    by_name = {src.name: src for src in sources}
    picked = []
    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue
        owner = by_name.get(obj.get(LOD_SOURCE)) if isinstance(obj.get(LOD_SOURCE), str) else None
        owner = owner or families.get(lod_base(obj.name, 'UNREAL').casefold())
        if owner is None:
            raise ValueError('ReLOD: selected mesh has no _MID / _HIGH source: ' + obj.name)
        picked.append(owner)
    return sorted(set(picked), key=lambda obj: obj.name.casefold())


def family_meshes(context, source):
    """Source plus its current LOD meshes, for JSON rows of untouched assets."""
    pattern = re.compile(re.escape(lod_base(source.name, 'UNREAL')) + r'[._]LOD[._]?\d+', re.I)
    return [obj for obj in context.scene.objects if obj.type == 'MESH'
            and (obj == source or pattern.fullmatch(obj.name))]


class ReLODPlan:
    def __init__(self, context, source, delete_current, reexport=False):
        self.source = source
        self.reexport = reexport
        self.generated = []
        self.export_collection = None
        if reexport:
            from .rebake_export import rebake_asset_collection
            if not bpy.data.filepath:
                raise ValueError('ReLOD re-export: save the working blend file first')
            self.export_collection = rebake_asset_collection(context, source)
        if source.library or source.data.library or not source.data.polygons:
            raise ValueError('ReLOD requires a local, non-empty mesh: ' + source.name)
        base = lod_base(source.name, 'UNREAL')
        pattern = re.compile(re.escape(base) + r'[._]LOD[._]?\d+', re.I)
        family = re.compile(re.escape(base) + r'_(MID|HIGH)', re.I)
        self.old = {obj for obj in context.scene.objects if obj.type == 'MESH' and obj != source
                    and not re.search(r'_(MID|HIGH)$', obj.name, re.I)
                    and (pattern.fullmatch(obj.name) or
                         (isinstance(obj.get(LOD_SOURCE), str) and family.fullmatch(obj[LOD_SOURCE])
                          and isinstance(obj.get(LOD_INDEX), int) and obj[LOD_INDEX] >= 0))}
        # A swapped pack (old rename by polygon count) names the real source
        # _LOD0 and a generated LOD _MID. Rebuilding would delete the source.
        if isinstance(source.get(LOD_SOURCE), str) and isinstance(source.get(LOD_INDEX), int):
            raise ValueError(f'ReLOD: {source.name} is a generated LOD{source[LOD_INDEX]} of '
                             f'{source[LOD_SOURCE]}; restore the real source name first')
        size = triangles(source)
        for obj in self.old:
            if not isinstance(obj.get(LOD_INDEX), int) and triangles(obj) > size:
                raise ValueError(f'ReLOD: {obj.name} is larger than {source.name} and not a generated LOD; '
                                 'it looks like the real source, rename it first')
        if self.old and not delete_current:
            raise ValueError('ReLOD: enable Delete Current LODs for ' + source.name)
        replacement = LODReplacement(context, self.old)
        for obj in replacement.objects:
            if obj.library or any(scene != context.scene for scene in obj.users_scene):
                raise ValueError('ReLOD: old LOD or label is linked/shared: ' + obj.name)
            if any(child not in replacement.objects for child in obj.children):
                raise ValueError('ReLOD: old LOD has an unrelated child: ' + obj.name)
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_mesh_finalization_settings
        self.options = {prop.identifier: getattr(s, prop.identifier) for prop in s.bl_rna.properties
                        if prop.identifier.startswith('smart_lods_') and not prop.is_readonly
                        and prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}
                        and prop.identifier not in {'smart_lods_is_running', 'smart_lods_progress', 'smart_lods_status'}}
        self.options.update(smart_lods_prepare_mode='UNREAL',
                            smart_lods_decimate_method=p.phase2_relod_method,
                            smart_lods_uv_seam_mode=p.phase2_relod_seam_mode,
                            **engine_lod_targets(p))
        self.names = {lod_name(source.name, i, 'UNREAL') for i in range(s.smart_lods_count)}
        for name in self.names:
            collision = bpy.data.objects.get(name)
            if collision is not None and collision not in self.old:
                raise ValueError('ReLOD: name belongs to another object/scene: ' + name)

    def steps(self, context, report):
        from .phase2_zbrush_export import export_visibility
        s = context.scene.polygroups_mesh_finalization_settings
        saved = {name: getattr(s, name) for name in self.options}
        before = set(bpy.data.objects)
        replacement = LODReplacement(context, self.old)
        success = False
        try:
            replacement.stash()
            for name, value in self.options.items():
                setattr(s, name, value)
            with export_visibility(context, self.source):
                bpy.ops.object.select_all(action='DESELECT')
                self.source.select_set(True)
                context.view_layer.objects.active = self.source
                worker = SimpleNamespace(report=report)
                yield from OBJECT_OT_polygroups_generate_smart_lods.source_steps(worker, context)
            generated = [obj for obj in set(bpy.data.objects)-before if obj.type == 'MESH'
                         and obj.get(LOD_SOURCE) == self.source.name]
            if len(generated) != self.options['smart_lods_count']:
                raise RuntimeError('ReLOD did not produce the requested LOD count')
            for obj in generated:
                obj.data.name = obj.name
            self.generated = generated
            success = True
        finally:
            if not success:
                for obj in list(set(bpy.data.objects)-before):
                    if obj.type in {'MESH', 'FONT'}:
                        data, kind = obj.data, obj.type
                        bpy.data.objects.remove(obj, do_unlink=True)
                        if data.users == 0:
                            (bpy.data.meshes if kind == 'MESH' else bpy.data.curves).remove(data)
            replacement.finish(success)
            for name, value in saved.items():
                setattr(s, name, value)

    def export(self, context, report):
        if not self.reexport:
            return
        from .rebake_export import export_rebaked_asset
        from .phase2_zbrush_export import export_visibility, preserved_selection
        p = context.scene.polygroups_model_preparation_settings
        saved_json = p.phase2_export_json, p.is_property_set('phase2_export_json')
        try:
            # Write one complete JSON after the batch, not a partial per-asset
            # document that overwrites the previous asset's statistics.
            p.phase2_export_json = False
            with ExitStack() as stack:
                stack.enter_context(preserved_selection(context))
                meshes = set(self.generated) | {obj for obj in self.export_collection.all_objects if obj.type == 'MESH'}
                for obj in sorted(meshes, key=lambda item: item.name):
                    stack.enter_context(export_visibility(context, obj))
                export_rebaked_asset(context, self.source, self.generated, self.export_collection,
                    'UNREAL', report, operation='ReLOD')
        except (ValueError, RuntimeError, OSError) as error:
            raise RuntimeError(f'ReLOD succeeded; re-export failed for {self.source.name}: {error}') from error
        finally:
            if saved_json[1]:
                p.phase2_export_json = saved_json[0]
            else:
                p.property_unset('phase2_export_json')


class OBJECT_OT_polygroups_relod(SequentialJob, bpy.types.Operator):
    bl_idname = 'object.polygroups_relod'
    bl_label = 'Re-create LODs'
    bl_description = 'Recreate LODs for all scene MID/HIGH assets; prefer MID when both exist. Uses Smart LOD counts and budgets'
    bl_options = {'REGISTER', 'UNDO'}
    _is_relod = True

    selected_only: bpy.props.BoolProperty(name='Selected Only', default=False, options={'SKIP_SAVE'},
        description='Recreate LODs only for assets of the selected MID/HIGH or LOD meshes')

    @classmethod
    def description(cls, context, properties):
        if properties.selected_only:
            return 'Recreate LODs only for the selected assets: select their MID/HIGH or any of their LODs'
        return cls.bl_description

    @classmethod
    def poll(cls, context):
        from .rebake_queue import editable
        return editable(context)

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        try:
            self.update_json = p.phase2_relod_json
            if self.update_json:
                from .relod_json import validate_json_update
                validate_json_update(context)
            sources = scene_sources(context)
            self.untouched = []
            if self.selected_only:
                chosen = selected_sources(context, sources)
                if not chosen:
                    raise ValueError('ReLOD: select a _MID / _HIGH mesh or one of its LODs')
                # The JSON is rewritten whole; keep rows of assets not rebuilt.
                self.untouched = [obj for source in sources if source not in chosen
                                  for obj in family_meshes(context, source)]
                sources = chosen
            self.plans = [ReLODPlan(context, source, p.phase2_relod_delete_current_lods, p.phase2_relod_reexport)
                          for source in sources]
            if not self.plans:
                raise ValueError('ReLOD: no _MID / _HIGH meshes in this scene')
        except ValueError as error:
            p.phase2_relod_status = str(error)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.selected = [obj.name for obj in context.selected_objects]
        self.active = context.active_object.name if context.active_object else None
        self.mode = context.object.mode if context.object else 'OBJECT'
        if self.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        p.phase2_relod_running = True
        p.phase2_relod_done = 0
        p.phase2_relod_total = len(self.plans)
        return self.start_job(context, self.steps(context), modal=not bpy.app.background)

    def steps(self, context):
        p = self._job_scene.polygroups_model_preparation_settings
        for index, plan in enumerate(self.plans):
            with closing(plan.steps(context, self.report)) as iterator:
                for number in iterator:
                    yield (index+number/plan.options['smart_lods_count'])/len(self.plans), f'{plan.source.name} | LOD{number-1}'
            if plan.reexport:
                self.update_job(context, (index+1)/len(self.plans), f'{plan.source.name} | Re-export FBX / Blend')
                plan.export(context, self.report)
            p.phase2_relod_done += 1
            yield (index+1)/len(self.plans), f'{plan.source.name} completed'
        if self.update_json:
            from .relod_json import update_json
            self.update_job(context, 1, 'Export / Update JSON')
            try:
                update_json(context, self.plans, self.untouched)
            except (ValueError, RuntimeError, OSError) as error:
                raise RuntimeError(f'ReLOD succeeded; JSON update failed: {error}') from error

    def update_job(self, context, fraction, message):
        super().update_job(context, fraction, message)
        p = self._job_scene.polygroups_model_preparation_settings
        p.phase2_relod_progress = fraction*100
        p.phase2_relod_status = message

    def finish_job(self, context, stopped=False, error=''):
        if getattr(self, '_job_done', False):
            return self._job_result
        result = super().finish_job(context, stopped=stopped, error=error)
        p = self._job_scene.polygroups_model_preparation_settings
        p.phase2_relod_running = False
        p.phase2_relod_status = ('Failed: '+error if error else 'Stopped' if stopped else
                                f'Completed {p.phase2_relod_done}/{p.phase2_relod_total} assets')
        if not stopped and not error:
            p.phase2_relod_progress = 100
        for obj in context.selected_objects:
            obj.select_set(False)
        for name in self.selected:
            obj = bpy.data.objects.get(name)
            if obj and obj.name in context.view_layer.objects:
                obj.select_set(True)
        context.view_layer.objects.active = bpy.data.objects.get(self.active) if self.active else None
        if self.mode != 'OBJECT' and context.active_object:
            bpy.ops.object.mode_set(mode=self.mode)
        return result
