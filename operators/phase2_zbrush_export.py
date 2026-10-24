"""Export multires Resculpting meshes as per-level OBJ files and a manifest for the ZBrush job script."""
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

SCULPT_FACE_SET = '.sculpt_face_set'
GROUP_MATERIAL_PREFIX = 'ZBG_'
JOB_SOURCE = Path(__file__).resolve().parents[1] / 'core' / 'zbrush_job.py'


def multires_modifier(obj):
    mods = [mod for mod in obj.modifiers if mod.type == 'MULTIRES']
    return next((mod for mod in mods if mod.name == MULTIRES_MODIFIER_NAME), mods[0] if mods else None)


def batch_candidates(scene):
    """(stem, object) for every multires mesh inside the scene's Generated.N collections."""
    found = []
    for collection in generated_collections(scene):
        meshes = sorted((obj for obj in collection.all_objects if obj.type == 'MESH' and multires_modifier(obj)),
                        key=lambda obj: obj.name.casefold())
        for obj in meshes:
            stem = collection.name if len(meshes) == 1 else f'{collection.name}_{obj.name}'
            found.append((stem, obj))
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
    for mod in list(copy.modifiers):
        if mod.type != 'MULTIRES':
            copy.modifiers.remove(mod)
    mod = next((item for item in copy.modifiers if item.type == 'MULTIRES'), None)
    total = mod.total_levels if mod else 0
    context.scene.collection.objects.link(copy)
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
                counts = {'level': level, 'faces': len(evaluated_mesh.polygons), 'verts': len(evaluated_mesh.vertices)}
                evaluated.to_mesh_clear()
                _export_obj(context, copy, str(Path(root) / zb.level_file(stem, level)))
                levels.append(counts)
            dims = tuple(round(value, 6) for value in obj.dimensions)
    finally:
        bpy.data.objects.remove(copy, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        for material in materials:
            bpy.data.materials.remove(material)
    return zb.asset_record(stem, obj.name, levels, groups, {'dimensions': dims})


def export_candidates(context, candidates, root, build, report=None):
    """Export every candidate into ``root`` and write the manifest; returns the asset records."""
    stems = zb.unique_stems([stem for stem, _obj in candidates])
    assets = []
    for number, (stem, (_stem, obj)) in enumerate(zip(stems, candidates), 1):
        if report:
            report(f'Exporting {number}/{len(candidates)}: {stem}')
        assets.append(export_object_levels(context, obj, stem, root))
    (Path(root) / 'ZTL').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(JOB_SOURCE, Path(root) / zb.JOB_SCRIPT_NAME)
    zb.write_manifest(root, assets, build, bpy.data.filepath)
    return assets


class OBJECT_OT_polygroups_phase2_export_zbrush(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_export_zbrush'
    bl_label = 'Export to ZBrush'
    bl_description = ('Write every multires level of the Resculpting meshes as OBJ (polygroups kept) and build one '
                      'ZTL per mesh with ZBrush subdivision levels')

    scope: bpy.props.EnumProperty(name='Scope', items=(('ACTIVE', 'Active Mesh', ''), ('ALL', 'All Generated.N', '')),
                                  default='ACTIVE')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and available(context)

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings

        def fail(message):
            p.phase2_zbrush_status = message
            self.report({'WARNING'}, message)
            return {'CANCELLED'}

        candidates = batch_candidates(context.scene) if self.scope == 'ALL' else active_candidate(context)
        if not candidates:
            return fail('No multires meshes found' if self.scope == 'ALL' else 'Select a mesh first')
        root = zb.output_root(bpy.data.filepath, bpy.path.abspath(p.phase2_zbrush_directory))
        try:
            root.mkdir(parents=True, exist_ok=True)
            assets = export_candidates(context, candidates, root, p.phase2_zbrush_build,
                                       report=lambda text: setattr(p, 'phase2_zbrush_status', text))
        except (RuntimeError, ValueError, OSError) as error:
            p.phase2_zbrush_status = f'Export failed: {error}'
            self.report({'ERROR'}, p.phase2_zbrush_status)
            return {'CANCELLED'}
        p.phase2_zbrush_status = f'Exported {len(assets)} mesh(es) to {root.name}'
        if p.phase2_zbrush_launch:
            p.phase2_zbrush_status += ' | ' + launch_zbrush(p, root)
        self.report({'INFO'}, p.phase2_zbrush_status)
        return {'FINISHED'}


def launch_zbrush(settings, root):
    """Start ZBrush with the job script; returns a status text."""
    exe = zb.find_zbrush_exe(bpy.path.abspath(settings.phase2_zbrush_exe))
    if not exe:
        return 'ZBrush.exe not found (set the path)'
    if zb.zbrush_running():
        return (f'ZBrush is running: close it and press Launch, or run {zb.JOB_SCRIPT_NAME} '
                'via ZScript > Python Scripting > Load')
    command = zb.launch_command(exe, Path(root) / zb.JOB_SCRIPT_NAME, Path(root) / zb.MANIFEST_NAME)
    try:
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
        return bool(bpy.data.filepath)

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
