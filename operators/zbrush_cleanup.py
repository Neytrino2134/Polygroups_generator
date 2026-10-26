"""Explicit cleanup and success-only completion of the current ZBrush export."""
import json
import os
import shutil
from pathlib import Path

import bpy

from .phase2_blend_export import generated_collections
from .phase2_processing import available
from ..core import zbrush_export as zb
from ..core.generated_index import GENERATED_INDEX_PATTERN

_WATCH = None


def cleanup_pending():
    global _WATCH
    if _WATCH is not None and not bpy.app.timers.is_registered(poll_success):
        _WATCH = None
    return _WATCH is not None


def delete_generated(collections):
    tree = set(collections)
    for col in collections:
        tree.update(col.children_recursive)
    objects = {obj for col in tree for obj in col.objects}
    meshes = {obj.data for obj in objects if obj.type == 'MESH'}
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in tree:
        bpy.data.collections.remove(col)
    for mesh in meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return len(tree), len(objects)


def clear_obj(root, assets=None):
    """Delete only OBJ files under the resolved Mesh directory, never ZTL files."""
    mesh = (Path(root).resolve() / 'Mesh')
    if not mesh.is_dir() or mesh.is_symlink():
        return 0
    boundary = mesh.resolve()
    paths = (mesh.rglob('*') if assets is None else
             (Path(root) / level['obj'] for asset in assets for level in asset['levels']))
    count = 0
    for path in paths:
        if path.suffix.lower() != '.obj' or not path.is_file():
            continue
        resolved = path.resolve()
        if path.is_symlink() or not resolved.is_relative_to(boundary):
            continue
        path.unlink()
        count += 1
    return count


def clear_mesh_folder(root):
    """Remove the dedicated Mesh directory, counting files and folders (root included)."""
    export_root = Path(root).resolve()
    mesh = export_root / 'Mesh'
    if not mesh.exists():
        return 0, 0
    if not mesh.is_dir() or mesh.is_symlink() or mesh.resolve().parent != export_root:
        raise OSError(f'Unsafe Mesh directory: {mesh}')
    boundary = mesh.resolve()
    files, folders = 0, 1
    for directory, dirs, names in os.walk(mesh, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink() or not path.resolve().is_relative_to(boundary) or getattr(os.path, 'isjunction', lambda p: False)(path):
                raise OSError(f'Linked path inside Mesh directory: {path}')
        files += len(names)
        folders += len(dirs)
    shutil.rmtree(mesh)
    return files, folders


def focus_blender():
    if os.name != 'nt':
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid() and user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            return False
        return True
    user32.EnumWindows(visit, 0)


def watch_success(context, root, assets):
    global _WATCH
    manifest = json.loads((Path(root) / zb.MANIFEST_NAME).read_text(encoding='utf-8'))
    cols = {col.name: col for col in generated_collections(context.scene)}
    collections = [cols[asset['name']] for asset in assets]
    _WATCH = dict(root=Path(root), assets=assets, job_id=manifest['job_id'],
                  scene=context.scene, blend=bpy.data.filepath, collections=collections,
                  objects={obj for col in collections for obj in col.all_objects})
    if not bpy.app.timers.is_registered(poll_success):
        bpy.app.timers.register(poll_success, first_interval=2.0)


def poll_success():
    global _WATCH
    job = _WATCH
    if job is None:
        return None
    try:
        scene = job['scene']
        p = scene.polygroups_model_preparation_settings
        if not p.phase2_zbrush_cleanup_on_success or bpy.data.filepath != job['blend'] or bpy.context.scene != scene:
            _WATCH = None
            return None
        manifest = json.loads((job['root'] / zb.MANIFEST_NAME).read_text(encoding='utf-8'))
        if manifest.get('job_id') != job['job_id']:
            p.phase2_zbrush_status = 'Cleanup cancelled: export job was replaced'
            _WATCH = None
            return None
        result_path = job['root'] / zb.RESULT_NAME
        if not result_path.is_file():
            return 2.0
        result = json.loads(result_path.read_text(encoding='utf-8'))
        if result.get('job_id') != job['job_id'] or not result.get('finished'):
            return 2.0
        records = result.get('assets', [])
        expected = {(a['name'], a['ztl']) for a in job['assets']}
        actual = {(a.get('name'), a.get('ztl')) for a in records}
        valid = not result.get('cancelled') and len(records) == len(expected) and actual == expected and all(a.get('ok') is True for a in records)
        for asset in job['assets']:
            target = job['root'] / asset['ztl']
            valid = valid and target.is_file() and target.stat().st_size > 0
        if not valid:
            p.phase2_zbrush_status = 'ZBrush failed: collections and temporary OBJ files retained'
            _WATCH = None
            return None
        if bpy.context.mode != "OBJECT" or not available(bpy.context):
            return 2.0
        current = {obj for col in job['collections'] for obj in col.all_objects}
        if current != job['objects']:
            p.phase2_zbrush_status = 'Cleanup cancelled: exported collections changed'
            _WATCH = None
            return None
        count = clear_obj(job['root'], job['assets'])
        cols, objects = delete_generated(job['collections'])
        p.phase2_zbrush_status = f'ZBrush completed: deleted {cols} collections, {objects} objects, {count} OBJ files'
        _WATCH = None
        focus_blender()
        return None
    except (OSError, ValueError, KeyError):
        return 2.0  # Result may be in the middle of being written/replaced.
    except (ReferenceError, RuntimeError):
        _WATCH = None
        return None


class OBJECT_OT_polygroups_zbrush_delete_generated(bpy.types.Operator):
    bl_idname = 'object.polygroups_zbrush_delete_generated'
    bl_label = 'Delete All Generated.N Collections and Meshes'
    bl_description = 'Delete Generated.N collections in the current scene and all objects inside them'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and available(context) and not cleanup_pending()

    def execute(self, context):
        cols, objects = delete_generated([col for col in context.scene.collection.children_recursive if GENERATED_INDEX_PATTERN.fullmatch(col.name)])
        context.scene.polygroups_model_preparation_settings.phase2_zbrush_status = f'Deleted {cols} collections and {objects} objects'
        return {'FINISHED'}


class OBJECT_OT_polygroups_zbrush_clear_obj(bpy.types.Operator):
    bl_idname = 'object.polygroups_zbrush_clear_obj'
    bl_label = 'Delete Temporary ZBrush OBJ Files'
    bl_description = 'Delete the entire temporary Mesh folder and its contents; keep ZTL files outside Mesh'

    @classmethod
    def poll(cls, context):
        return available(context) and not cleanup_pending()

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        try:
            files, folders = clear_mesh_folder(zb.output_root(bpy.data.filepath, bpy.path.abspath(p.phase2_zbrush_directory)))
        except OSError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        p.phase2_zbrush_status = f'Successfully deleted {files} files / {folders} folders (including Mesh)'
        self.report({'INFO'}, p.phase2_zbrush_status)
        return {'FINISHED'}
