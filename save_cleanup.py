"""Explicit scan and cleanup of numbered Blender backup saves."""
import os
import re
from pathlib import Path
import bpy

BACKUP_NAME = re.compile(r'.+\.(?:blend|blendAutosave)[1-9][0-9]*$', re.IGNORECASE)
_SCAN = None


def _invalidate(self, context):
    global _SCAN
    _SCAN = None
    self.status = 'Scan required'
    self.file_count = 0
    self.total_bytes = 0


class AIRETOPO_PG_save_cleanup(bpy.types.PropertyGroup):
    directory: bpy.props.StringProperty(name='Directory', subtype='DIR_PATH', update=_invalidate)
    file_count: bpy.props.IntProperty(default=0)
    total_bytes: bpy.props.FloatProperty(default=0)
    status: bpy.props.StringProperty(default='Scan required')


def _root(settings):
    if not settings.directory.strip():
        raise ValueError('Choose a directory first')
    root = Path(bpy.path.abspath(settings.directory)).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('The selected path is not a directory')
    return root


def scan_backups(root, recursive):
    records, errors = [], []
    def onerror(error):
        errors.append(str(error))
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        dirs[:] = [name for name in dirs if not Path(folder, name).is_symlink()
                   and not os.path.isjunction(Path(folder, name))]
        for name in files:
            path = Path(folder, name)
            if not BACKUP_NAME.fullmatch(name) or path.is_symlink():
                continue
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root) or not resolved.is_file():
                    continue
                stat = resolved.stat()
                records.append((resolved, stat.st_size, stat.st_mtime_ns))
            except OSError as error:
                errors.append(str(error))
        if not recursive:
            break
    return records, errors


class AIRETOPO_OT_scan_save_cleanup(bpy.types.Operator):
    bl_idname = 'wm.airetopo_scan_save_cleanup'
    bl_label = 'Scan Backup Saves'

    def execute(self, context):
        global _SCAN
        settings = context.window_manager.airetopo_save_cleanup
        try:
            root = _root(settings)
            records, errors = scan_backups(root, True)
        except (OSError, ValueError) as error:
            _invalidate(settings, context)
            settings.status = str(error)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        _SCAN = (root, True, records)
        settings.file_count = len(records)
        settings.total_bytes = sum(record[1] for record in records)
        settings.status = f'Found: {len(records)} files' + (f'; scan errors: {len(errors)}' if errors else '')
        return {'FINISHED'}


class AIRETOPO_OT_scan_current_save_folder(bpy.types.Operator):
    bl_idname = 'wm.airetopo_scan_current_save_folder'
    bl_label = 'Scan From Current Folder'
    bl_description = 'Scan the current blend file folder and all subfolders for numbered backup saves'

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, 'Save the current blend file first')
            return {'CANCELLED'}
        context.window_manager.airetopo_save_cleanup.directory = str(Path(bpy.data.filepath).parent)
        return bpy.ops.wm.airetopo_scan_save_cleanup()


class AIRETOPO_OT_clean_backup_saves(bpy.types.Operator):
    bl_idname = 'wm.airetopo_clean_backup_saves'
    bl_label = 'Clean Backup Saves'
    bl_description = 'Delete only the numbered backup files from the last scan'

    def execute(self, context):
        global _SCAN
        settings = context.window_manager.airetopo_save_cleanup
        try:
            root = _root(settings)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        if _SCAN is None or _SCAN[:2] != (root, True):
            self.report({'ERROR'}, 'Scan this directory before cleaning')
            return {'CANCELLED'}
        deleted, skipped, failed, remaining = 0, 0, 0, []
        for path, size, modified in _SCAN[2]:
            try:
                if not path.exists():
                    skipped += 1
                    continue
                stat = path.stat()
                if (path.is_symlink() or not path.resolve().is_relative_to(root)
                        or not BACKUP_NAME.fullmatch(path.name)
                        or (stat.st_size, stat.st_mtime_ns) != (size, modified)):
                    skipped += 1
                    continue
                path.unlink()
                deleted += 1
            except OSError:
                failed += 1
                remaining.append((path, size, modified))
        _SCAN = None
        settings.file_count = len(remaining)
        settings.total_bytes = sum(record[1] for record in remaining)
        settings.status = f'Deleted: {deleted}; skipped: {skipped}; errors: {failed}. Scan again to refresh.'
        self.report({'WARNING'} if failed or skipped else {'INFO'}, settings.status)
        return {'FINISHED'}


def draw_cleanup(layout, context):
    settings = context.window_manager.airetopo_save_cleanup
    layout.prop(settings, 'directory')
    layout.operator('wm.airetopo_scan_save_cleanup', icon='VIEWZOOM')
    layout.operator('wm.airetopo_scan_current_save_folder', icon='FILE_BLEND')
    layout.label(text=f'{settings.file_count} files | {settings.total_bytes / (1024 * 1024):.2f} MiB')
    layout.label(text=settings.status)
    row = layout.row()
    row.enabled = _SCAN is not None and settings.file_count > 0
    row.operator('wm.airetopo_clean_backup_saves', icon='TRASH')


CLASSES = (AIRETOPO_PG_save_cleanup, AIRETOPO_OT_scan_save_cleanup, AIRETOPO_OT_scan_current_save_folder, AIRETOPO_OT_clean_backup_saves)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.airetopo_save_cleanup = bpy.props.PointerProperty(type=AIRETOPO_PG_save_cleanup)


def unregister():
    global _SCAN
    _SCAN = None
    del bpy.types.WindowManager.airetopo_save_cleanup
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
