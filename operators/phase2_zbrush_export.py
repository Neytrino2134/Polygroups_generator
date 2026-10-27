"""Export multires Resculpting meshes as per-level OBJ files and a manifest for the ZBrush job script."""
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import bpy
import numpy as np

from .phase2_blend_export import generated_collections
from .phase2_processing import available
from .resculpting import MULTIRES_MODIFIER_NAME
from ..core import zbrush_export as zb
from ..core.mesh_ngons import ngon_count, triangulated_ngon_copy

SCULPT_FACE_SET = '.sculpt_face_set'
GROUP_MATERIAL_PREFIX = 'ZBG_'
JOB_SOURCE = Path(__file__).resolve().parents[1] / 'core' / 'zbrush_job.py'


def multires_modifier(obj):
    mods = [mod for mod in obj.modifiers if mod.type == 'MULTIRES']
    return next((mod for mod in mods if mod.name == MULTIRES_MODIFIER_NAME), mods[0] if mods else None)


def batch_candidates(scene):
    """One Resculpting_01 source per Generated.N collection in the open scene."""
    found = []
    for collection in generated_collections(scene):
        name = f'Resculpting_01_Highpoly_{collection.name}'
        obj = collection.all_objects.get(name)
        if obj is not None and obj.type == 'MESH' and multires_modifier(obj):
            found.append((collection.name, obj))
    return found


def active_candidate(context):
    obj = context.view_layer.objects.active
    if obj is None or obj.type != 'MESH':
        obj = next((item for item in context.selected_objects if item.type == 'MESH'), None)
    if obj is None:
        return []
    collection = next((col.name for col in obj.users_collection if col.name != 'Scene Collection'), '')
    return [(zb.safe_name(collection if collection.startswith('Generated.') else obj.name), obj)]


@contextmanager
def preserved_selection(context):
    layer = context.view_layer
    selected = [obj for obj in layer.objects if obj.select_get(view_layer=layer)]
    active = layer.objects.active
    try:
        yield
    finally:
        for obj in layer.objects:
            obj.select_set(obj in selected, view_layer=layer)
        layer.objects.active = active


@contextmanager
def export_visibility(context, obj):
    """Reveal only the source's collection paths, then restore all restrictions."""
    from .rename_objects import layer_collection_paths
    layers, collections = {}, {}
    def snapshot(layer):
        layers[layer] = (layer.exclude, layer.hide_viewport)
        for child in layer.children:
            snapshot(child)
    snapshot(context.view_layer.layer_collection)
    flags = (obj.hide_viewport, obj.hide_render, obj.hide_select)
    eye = None
    try:
        for collection in obj.users_collection:
            for path in layer_collection_paths(context.view_layer.layer_collection, collection):
                for layer in path:
                    col = layer.collection
                    if col not in collections:
                        collections[col] = (col.hide_viewport, col.hide_render, col.hide_select)
                    col.hide_viewport = col.hide_render = col.hide_select = False
                    if layer.exclude:
                        layer.exclude = False
                    layer.hide_viewport = False
        context.view_layer.update()
        eye = obj.hide_get(view_layer=context.view_layer)
        obj.hide_viewport = obj.hide_render = obj.hide_select = False
        obj.hide_set(False, view_layer=context.view_layer)
        context.view_layer.update()
        yield
    finally:
        if eye is not None:
            obj.hide_set(eye, view_layer=context.view_layer)
        obj.hide_viewport, obj.hide_render, obj.hide_select = flags
        for col, values in collections.items():
            col.hide_viewport, col.hide_render, col.hide_select = values
        # Excluding a parent propagates to its children: restore parent first.
        for layer, (excluded, hidden) in layers.items():
            if layer.exclude != excluded:
                layer.exclude = excluded
            layer.hide_viewport = hidden
        context.view_layer.update()


def _group_ids(mesh):
    attribute = mesh.attributes.get(SCULPT_FACE_SET)
    if attribute is None or not len(mesh.polygons):
        return None
    values = np.empty(len(mesh.polygons), dtype=np.int32)
    attribute.data.foreach_get('value', values)
    return values


def _apply_group_materials(copy, mesh):
    """Give each polygroup (sculpt face set) its own material so the OBJ exporter writes one `g` per group."""
    ids = _group_ids(mesh)
    if ids is None:
        return 0, []
    unique = np.unique(ids)
    mesh.materials.clear()
    materials = []
    for number in unique:
        material = bpy.data.materials.new(f'{GROUP_MATERIAL_PREFIX}{int(number):03d}')
        mesh.materials.append(material)
        materials.append(material)
    index = mesh.attributes.get('material_index') or mesh.attributes.new('material_index', 'INT', 'FACE')
    index.data.foreach_set('value', np.searchsorted(unique, ids).astype(np.int32))
    mesh.update()
    return len(unique), materials


def _export_obj(context, obj, filepath):
    for old in (filepath, os.path.splitext(filepath)[0] + '.mtl'):
        if os.path.exists(old):
            os.remove(old)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    result = bpy.ops.wm.obj_export(
        filepath=filepath, check_existing=False, export_selected_objects=True, apply_modifiers=True,
        export_eval_mode='DAG_EVAL_VIEWPORT', export_uv=True, export_normals=False, export_colors=False,
        export_materials=True, export_pbr_extensions=False, export_material_groups=True,
        export_object_groups=False, export_smooth_groups=False, forward_axis='NEGATIVE_Z', up_axis='Y')
    mtl = os.path.splitext(filepath)[0] + '.mtl'
    if os.path.exists(mtl):
        os.remove(mtl)
    if 'FINISHED' not in result or not os.path.isfile(filepath):
        raise RuntimeError(f'OBJ export failed: {filepath}')


def export_object_levels(context, obj, stem, root):
    """Write L0..Ln OBJ files for the object's multires levels; returns the manifest asset record.

    The user's object is never changed: a temporary copy with polygroup materials is exported instead."""
    mesh = obj.data.copy()
    copy = obj.copy()
    copy.data = mesh
    copy.name = stem
    try:
        prepared = triangulated_ngon_copy(mesh)
    except Exception:
        bpy.data.objects.remove(copy)
        bpy.data.meshes.remove(mesh)
        raise
    if prepared is not None:
        copy.data = prepared
        bpy.data.meshes.remove(mesh)
        mesh = prepared
    for mod in list(copy.modifiers):
        if mod.type != 'MULTIRES':
            copy.modifiers.remove(mod)
    mod = next((item for item in copy.modifiers if item.type == 'MULTIRES'), None)
    total = mod.total_levels if mod else 0
    copy.hide_viewport = copy.hide_render = copy.hide_select = False
    context.scene.collection.objects.link(copy)
    copy.hide_set(False)
    context.view_layer.update()
    groups, materials = _apply_group_materials(copy, mesh)
    levels = []
    try:
        with preserved_selection(context):
            folder = Path(root) / 'Mesh' / stem
            folder.mkdir(parents=True, exist_ok=True)
            for level in range(total + 1):
                if mod:
                    mod.show_viewport = True
                    mod.levels = level
                bpy.ops.object.select_all(action='DESELECT')
                evaluated = copy.evaluated_get(context.evaluated_depsgraph_get())
                evaluated_mesh = evaluated.to_mesh()
                export_mesh = None
                export_copy = None
                try:
                    export_mesh = triangulated_ngon_copy(evaluated_mesh)
                    if export_mesh is not None:
                        export_copy = bpy.data.objects.new(f'{stem}_Level{level}', export_mesh)
                        export_copy.matrix_world = copy.matrix_world.copy()
                        context.scene.collection.objects.link(export_copy)
                        context.view_layer.update()
                    exported = export_mesh or evaluated_mesh
                    counts = {'level': level, 'faces': len(exported.polygons),
                              'verts': len(exported.vertices)}
                    _export_obj(context, export_copy or copy,
                                str(Path(root) / zb.level_file(stem, level)))
                finally:
                    if export_copy is not None:
                        bpy.data.objects.remove(export_copy, do_unlink=True)
                    if export_mesh is not None:
                        bpy.data.meshes.remove(export_mesh)
                    evaluated.to_mesh_clear()
                levels.append(counts)
            dims = tuple(round(value, 6) for value in obj.dimensions)
    finally:
        bpy.data.objects.remove(copy, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        for material in materials:
            bpy.data.materials.remove(material)
    return zb.asset_record(stem, obj.name, levels, groups, {'dimensions': dims})


def export_candidates(context, candidates, root, report=None):
    """Export every candidate's levels into ``root``; returns the asset records."""
    stems = zb.unique_stems([stem for stem, _obj in candidates])
    assets = []
    for number, (stem, (_stem, obj)) in enumerate(zip(stems, candidates), 1):
        if report:
            report(f'Exporting {number}/{len(candidates)}: {stem}')
        with preserved_selection(context), export_visibility(context, obj):
            assets.append(export_object_levels(context, obj, stem, root))
    return assets


def write_job(root, assets, build, source_blend):
    """Create ZTL/, copy the ZBrush job script and write the manifest."""
    (Path(root) / 'ZTL').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(JOB_SOURCE, Path(root) / zb.JOB_SCRIPT_NAME)
    for stale in (zb.RESULT_NAME, zb.LOG_NAME, "job_control.json"):
        (Path(root) / stale).unlink(missing_ok=True)
    return zb.write_manifest(root, assets, build, source_blend)


class OBJECT_OT_polygroups_phase2_export_zbrush(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_export_zbrush'
    bl_label = 'Export to ZBrush'
    bl_description = ('Write every multires level of the Resculpting meshes as OBJ (polygroups kept) and build one '
                      'ZTL per mesh with ZBrush subdivision levels')

    scope: bpy.props.EnumProperty(name='Scope', items=(('ACTIVE', 'Active Mesh', ''), ('ALL', 'All Generated.N', '')),
                                  default='ACTIVE')

    @classmethod
    def poll(cls, context):
        from .zbrush_cleanup import cleanup_pending
        return context.mode == 'OBJECT' and available(context) and not cleanup_pending()

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings

        def fail(message):
            p.phase2_zbrush_status = message
            self.report({'WARNING'}, message)
            return {'CANCELLED'}

        candidates = batch_candidates(context.scene) if self.scope == 'ALL' else active_candidate(context)
        if not candidates:
            return fail('No Resculpting_01_Highpoly_Generated.N meshes with Multires found' if self.scope == 'ALL' else 'Select a mesh first')
        root = zb.output_root(bpy.data.filepath, bpy.path.abspath(p.phase2_zbrush_directory))
        try:
            root.mkdir(parents=True, exist_ok=True)
            assets = export_candidates(context, candidates, root,
                                       report=lambda text: setattr(p, 'phase2_zbrush_status', text))
            write_job(root, assets, p.phase2_zbrush_build, bpy.data.filepath)
            if self.scope == 'ALL' and p.phase2_zbrush_cleanup_on_success:
                from .zbrush_cleanup import watch_success
                watch_success(context, root, assets)
        except (RuntimeError, ValueError, OSError) as error:
            p.phase2_zbrush_status = f'Export failed: {error}'
            self.report({'ERROR'}, p.phase2_zbrush_status)
            return {'CANCELLED'}
        p.phase2_zbrush_status = f'Exported {len(assets)} mesh(es) to {root.name}'
        if p.phase2_zbrush_launch:
            p.phase2_zbrush_status += ' | ' + launch_zbrush(p, root)
        self.report({'INFO'}, p.phase2_zbrush_status)
        return {'FINISHED'}


def configured_exe():
    """ZBrush.exe from Preferences > External Programs ('' when the add-on preferences are unavailable)."""
    addon = bpy.context.preferences.addons.get(__package__.split('.')[0])
    return bpy.path.abspath(addon.preferences.zbrush_exe) if addon else ''


def launch_zbrush(settings, root):
    """Start ZBrush with the job script; returns a status text."""
    exe = zb.find_zbrush_exe(configured_exe())
    if not exe:
        return 'ZBrush.exe not found: set it in Preferences > Add-ons > External Programs'
    if zb.zbrush_running():
        return (f'ZBrush is running: close it and press Launch, or run {zb.JOB_SCRIPT_NAME} '
                'via ZScript > Python Scripting > Load')
    try:
        command = zb.launch_command(exe, zb.prepare_launcher(root, JOB_SOURCE))
        subprocess.Popen(command, cwd=os.path.dirname(exe), close_fds=True)
    except OSError as error:
        return f'ZBrush launch failed: {error}'
    return 'ZBrush started'


class OBJECT_OT_polygroups_phase2_launch_zbrush(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_launch_zbrush'
    bl_label = 'Launch ZBrush'
    bl_description = 'Start ZBrush with the job script of the last export'

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath) and not context.scene.polygroups_model_preparation_settings.phase2_pipeline_running

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        root = zb.output_root(bpy.data.filepath, bpy.path.abspath(p.phase2_zbrush_directory))
        if not (root / zb.MANIFEST_NAME).is_file():
            p.phase2_zbrush_status = 'Nothing exported yet'
            self.report({'WARNING'}, p.phase2_zbrush_status)
            return {'CANCELLED'}
        p.phase2_zbrush_status = launch_zbrush(p, root)
        return {'FINISHED'}


class OBJECT_OT_polygroups_phase2_open_zbrush_folder(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_open_zbrush_folder'
    bl_label = 'Open ZBrush Folder'
    bl_description = 'Show the ZBrush export folder in the file browser'

    @classmethod
    def poll(cls, context):
        p = context.scene.polygroups_model_preparation_settings
        return bool(bpy.data.filepath) and zb.output_root(bpy.data.filepath, bpy.path.abspath(p.phase2_zbrush_directory)).is_dir()

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        folder = str(zb.output_root(bpy.data.filepath, bpy.path.abspath(p.phase2_zbrush_directory)))
        os.startfile(folder) if os.name == 'nt' else bpy.ops.wm.path_open(filepath=folder)
        return {'FINISHED'}


WORKER_SOURCE = Path(__file__).resolve().parents[1] / 'core' / 'zbrush_batch_worker.py'


def blend_folder_files(settings):
    """Generated.N.blend files of the configured folder (default: the folder of the current blend)."""
    custom = bpy.path.abspath(settings.phase2_zbrush_blend_folder)
    folder = Path(custom) if custom else Path(bpy.data.filepath).parent if bpy.data.filepath else None
    if folder is None or not folder.is_dir():
        return []
    return sorted((item for item in folder.iterdir() if item.is_file() and zb.GENERATED_BLEND.match(item.name)),
                  key=lambda item: item.name.casefold())


def start_worker(blend_file, root, part):
    """Export one blend file in a background Blender; returns the process."""
    addon = __package__.split('.')[0]
    command = [bpy.app.binary_path, '-b', '--factory-startup', str(blend_file), '--python', str(WORKER_SOURCE),
               '--', addon, str(Path(__file__).resolve().parents[2]), str(root), str(part)]
    log = open(str(part) + '.log', 'w', encoding='utf-8')
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL), log


def collect_part(part):
    try:
        return json.loads(Path(part).read_text(encoding='utf-8'))['assets']
    except (OSError, ValueError, KeyError):
        return None


class OBJECT_OT_polygroups_phase2_export_zbrush_folder(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_export_zbrush_folder'
    bl_label = 'Export Folder to ZBrush'
    bl_description = ('Export every Generated.N.blend of the folder (each opened in a background Blender) into one '
                      'job, then build the ZTL files in ZBrush')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not _FOLDER_JOB and not context.scene.polygroups_model_preparation_settings.phase2_pipeline_running

    def _prepare(self, context):
        p = context.scene.polygroups_model_preparation_settings
        files = blend_folder_files(p)
        if not files:
            p.phase2_zbrush_status = 'No Generated.N.blend files found'
            self.report({'WARNING'}, p.phase2_zbrush_status)
            return None
        root = zb.output_root(str(files[0]), bpy.path.abspath(p.phase2_zbrush_directory))
        parts = root / '_parts'
        parts.mkdir(parents=True, exist_ok=True)
        return p, files, root, parts

    def _finish(self, p, files, root, assets, failed):
        names = [asset['name'].casefold() for asset in assets]
        if len(set(names)) != len(names):
            p.phase2_zbrush_status = 'Export failed: duplicate asset names across the blend files'
            self.report({'ERROR'}, p.phase2_zbrush_status)
            return {'CANCELLED'}
        write_job(root, assets, p.phase2_zbrush_build, str(files[0].parent))
        shutil.rmtree(root / '_parts', ignore_errors=True)
        p.phase2_zbrush_status = f'Exported {len(assets)} mesh(es) from {len(files)} blend(s)' + (
            f' | {failed} failed (see _parts)' if failed else '')
        if p.phase2_zbrush_launch and assets:
            p.phase2_zbrush_status += ' | ' + launch_zbrush(p, root)
        self.report({'INFO'}, p.phase2_zbrush_status)
        return {'FINISHED'}

    def execute(self, context):
        """Blocking run (scripts, tests)."""
        prepared = self._prepare(context)
        if prepared is None:
            return {'CANCELLED'}
        p, files, root, parts = prepared
        assets, failed = [], 0
        for number, blend_file in enumerate(files, 1):
            p.phase2_zbrush_status = f'Exporting {number}/{len(files)}: {blend_file.stem}'
            part = parts / f'{blend_file.stem}.json'
            process, log = start_worker(blend_file, root, part)
            process.wait()
            log.close()
            found = collect_part(part)
            if found is None:
                failed += 1
            else:
                assets += found
        return self._finish(p, files, root, assets, failed)

    def invoke(self, context, event):
        prepared = self._prepare(context)
        if prepared is None:
            return {'CANCELLED'}
        self._p, self._files, self._root, self._parts = prepared
        self._assets, self._failed, self._index, self._running = [], 0, 0, None
        _FOLDER_JOB.append(self)
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _stop(self, context):
        context.window_manager.event_timer_remove(self._timer)
        if self._running:
            self._running[0].kill()
            self._running[1].close()
        _FOLDER_JOB.clear()

    def modal(self, context, event):
        if event.type == 'ESC':
            self._stop(context)
            self._p.phase2_zbrush_status = 'Batch export cancelled'
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        if self._running and self._running[0].poll() is None:
            return {'RUNNING_MODAL'}
        if self._running:
            self._running[1].close()
            found = collect_part(self._running[2])
            if found is None:
                self._failed += 1
            else:
                self._assets += found
            self._running = None
        if self._index >= len(self._files):
            self._stop(context)
            return self._finish(self._p, self._files, self._root, self._assets, self._failed)
        blend_file = self._files[self._index]
        self._index += 1
        self._p.phase2_zbrush_status = f'Exporting {self._index}/{len(self._files)}: {blend_file.stem} (Esc cancels)'
        part = self._parts / f'{blend_file.stem}.json'
        process, log = start_worker(blend_file, self._root, part)
        self._running = (process, log, part)
        return {'RUNNING_MODAL'}


_FOLDER_JOB = []

