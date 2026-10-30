"""Clear Temp Files: scan and check the final asset folder, then delete its temporary files."""
import re
from pathlib import Path

import bpy

from ..core import final_cleanup as core

STATE = dict(scan=None, check=None, status='', orphans=None)
MAX_LISTED = 6


def busy(context):
    p = context.scene.polygroups_model_preparation_settings
    return bool(p.batch_is_running or p.phase2_pipeline_running or p.phase2_is_running
                or p.phase2_final_is_running or p.phase2_auto_render_running)


def reset_state():
    STATE.update(scan=None, check=None, status='', orphans=None)


ORPHAN_KINDS = (('materials', 'Materials'), ('images', 'Images'), ('textures', 'Textures'))


def orphan_datablocks():
    """Unused (zero-user, no fake user, local) materials, images and textures of the open blend, by kind."""
    return {kind: [item for item in getattr(bpy.data, kind)
                   if item.users == 0 and not item.use_fake_user and item.library is None]
            for kind, _label in ORPHAN_KINDS}


def purge_orphans():
    """Remove unused materials, textures and images; repeat because removing a material frees its images."""
    removed = 0
    for _ in range(6):
        found = orphan_datablocks()
        batch = {item for items in found.values() for item in items}
        if not batch:
            break
        bpy.data.batch_remove(batch)
        removed += len(batch)
    return removed


def orphan_count_total():
    return sum((STATE['orphans'] or {}).values())


class OBJECT_OT_polygroups_final_cleanup_scan(bpy.types.Operator):
    bl_idname = 'object.polygroups_final_cleanup_scan'
    bl_label = 'Scan and Check'
    bl_description = ('Find backup saves, extra .blend files and the Bakes / batch_reports folders in the working '
                      'blend folder, and check the Generated.N files in !Blend. Nothing is deleted')

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath) and not busy(context)

    def execute(self, context):
        current = Path(bpy.data.filepath)
        try:
            STATE['scan'] = core.scan(current.parent, current)
            STATE['check'] = core.check(current.parent)
            STATE['orphans'] = {kind: len(items) for kind, items in orphan_datablocks().items()}
        except (ValueError, OSError) as error:
            reset_state()
            STATE['status'] = str(error)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        scan = STATE['scan']
        unused = sum(STATE['orphans'].values())
        STATE['status'] = f'Found {scan.file_count} files | {core.megabytes(scan.total_bytes)} | {unused} unused datablocks'
        self.report({'INFO'}, STATE['status'])
        return {'FINISHED'}


class OBJECT_OT_polygroups_final_cleanup_clear(bpy.types.Operator):
    bl_idname = 'object.polygroups_final_cleanup_clear'
    bl_label = 'Clear All Temp Files'
    bl_description = 'Permanently delete the files found by Scan and Check (final folders, Textures and sources stay)'

    @classmethod
    def poll(cls, context):
        scan = STATE['scan']
        return (bool(bpy.data.filepath) and not busy(context) and scan is not None
                and (scan.file_count > 0 or sum((STATE['orphans'] or {}).values()) > 0))

    def invoke(self, context, event):
        scan = STATE['scan']
        if Path(bpy.data.filepath) != scan.current:
            self.report({'WARNING'}, 'The open blend changed: scan again')
            return {'CANCELLED'}
        return context.window_manager.invoke_confirm(
            self, event, title='Clear All Temp Files',
            message=(f'Permanently delete {scan.file_count} files ({core.megabytes(scan.total_bytes)}) and purge '
                     f'{orphan_count_total()} unused materials / images / textures?'),
            confirm_text='Delete')

    def execute(self, context):
        scan = STATE['scan']
        if scan is None or Path(bpy.data.filepath) != scan.current:
            self.report({'WARNING'}, 'Scan the folder first')
            return {'CANCELLED'}
        files, size, errors = core.delete(scan)
        purged = purge_orphans()
        STATE['orphans'] = {kind: len(items) for kind, items in orphan_datablocks().items()}
        STATE['scan'] = core.scan(scan.root, scan.current)
        STATE['check'] = core.check(scan.root)
        STATE['status'] = f'Deleted {files} files | {core.megabytes(size)} | purged {purged} unused | {len(errors)} errors'
        for error in errors[:5]:
            self.report({'WARNING'}, error)
        self.report({'WARNING'} if errors else {'INFO'}, STATE['status'])
        return {'FINISHED'}


GENERATED_COLLECTION = re.compile(r'^Generated\.\d+$')


def asset_collections(scene):
    """Final asset (<name>_Collection) and Generated.N collections of the scene, outermost first."""
    found = [col for col in scene.collection.children_recursive
             if col.name.endswith('_Collection') or GENERATED_COLLECTION.match(col.name)]
    nested = {child for col in found for child in col.children_recursive}
    return [col for col in found if col not in nested]


def clear_asset_collections(scene):
    """Delete those collections with their objects and nested collections; returns (collections, objects)."""
    collections = asset_collections(scene)
    nested = {child for col in collections for child in col.children_recursive}
    objects = {obj for col in collections for obj in col.all_objects}
    bpy.data.batch_remove(objects)
    removed = set(collections) | nested
    bpy.data.batch_remove(removed)
    return len(removed), len(objects)


def purge_all_unused():
    before = sum(len(collection) for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.images,
                                                     bpy.data.textures, bpy.data.node_groups))
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    after = sum(len(collection) for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.images,
                                                    bpy.data.textures, bpy.data.node_groups))
    return before - after


RESET_MODES = (
    ('ALL', 'Start from Scratch',
     'Delete every ! folder, Textures, Bakes, batch_reports, backup saves and other .blend files beside or below '
     'the working blend; remove _Collection / Generated.N collections and all unused data. '
     'Source folders 01_ ... 20_ and the working blend stay'),
    ('PHASE2', 'Clear Phase 2 Files',
     'Delete All Final Files: every ! folder and Textures folder; keep Bakes and other .blend files. '
     'Remove _Collection / Generated.N collections and all unused data'),
)


class OBJECT_OT_polygroups_clear_all_files(bpy.types.Operator):
    bl_idname = 'object.polygroups_clear_all_files'
    bl_label = 'Clear All Files'
    bl_options = {'REGISTER', 'UNDO'}
    mode: bpy.props.EnumProperty(items=RESET_MODES, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return next(text for key, _label, text in RESET_MODES if key == properties.mode)

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath) and not busy(context)

    def scan(self):
        current = Path(bpy.data.filepath)
        return core.scan_reset(current.parent, current, self.mode)

    def invoke(self, context, event):
        try:
            self.result = self.scan()
        except (ValueError, OSError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        label = next(label for key, label, _text in RESET_MODES if key == self.mode)
        return context.window_manager.invoke_props_dialog(self, width=460, title=label, confirm_text='Delete')

    def draw(self, context):
        column = self.layout.column(align=True)
        column.label(text=str(Path(bpy.data.filepath).parent), icon='FILE_FOLDER')
        totals = core.reset_totals(self.result)
        for key, label in core.RESET_CATEGORIES:
            if key in core.RESET_KEEP[self.mode]:
                column.label(text=f'Keep: {label}', icon='CHECKMARK')
            else:
                files, size = totals[key]
                column.label(text=f'{label}: {files} files | {core.megabytes(size)}', icon='TRASH')
        collections = asset_collections(context.scene)
        column.label(text=f'Collections _Collection / Generated.N: {len(collections)} (with their objects)',
                     icon='OUTLINER_COLLECTION')
        column.label(text='All unused data in this blend is purged', icon='ORPHAN_DATA')
        column.label(text='Files are deleted permanently; the working blend is not saved', icon='ERROR')

    def execute(self, context):
        try:
            result = self.scan()
        except (ValueError, OSError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        collections, objects = clear_asset_collections(context.scene)
        purged = purge_all_unused()
        files, size, errors = core.delete_reset(result)
        reset_state()
        STATE['status'] = (f'Deleted {files} files | {core.megabytes(size)} | {collections} collections, '
                           f'{objects} objects | purged {purged} unused | {len(errors)} errors')
        for error in errors[:5]:
            self.report({'WARNING'}, error)
        self.report({'WARNING'} if errors else {'INFO'}, STATE['status'])
        return {'FINISHED'}


def draw_clear_all_files(layout, context):
    """Clear All Files group under Clear Temp Files in Save and Cleanup."""
    box = layout.box().column(align=True)
    box.label(text='Clear All Files', icon='ERROR')
    row = box.row(align=True)
    row.enabled = bool(bpy.data.filepath) and not busy(context)
    row.operator('object.polygroups_clear_all_files', text='Start from Scratch', icon='TRASH').mode = 'ALL'
    row.operator('object.polygroups_clear_all_files', text='Clear Phase 2 Files', icon='TRASH').mode = 'PHASE2'


def draw_final_cleanup(layout, context):
    """Clear Temp Files controls; the same block is used in Save and Cleanup, Phase 1 and Phase 2."""
    column = layout.column(align=True)
    column.enabled = not busy(context)
    column.operator('object.polygroups_final_cleanup_scan', icon='VIEWZOOM')
    scan, check = STATE['scan'], STATE['check']
    if scan is not None:
        box = layout.box().column(align=True)
        totals = scan.totals()
        for key, label in core.CATEGORIES:
            files, size = totals[key]
            box.label(text=f'{label}: {files} | {core.megabytes(size)}')
        box.label(text=f'Total: {scan.file_count} files | {core.megabytes(scan.total_bytes)}', icon='INFO')
    orphans = STATE['orphans']
    if orphans is not None:
        box = layout.box().column(align=True)
        box.label(text='Unused data in the open blend: ' + ' | '.join(
            f'{label} {orphans[kind]}' for kind, label in ORPHAN_KINDS), icon='ORPHAN_DATA')
    if check is not None:
        box = layout.box().column(align=True)
        if check.folder is None:
            box.label(text='!Blend folder not found', icon='ERROR')
        else:
            box.label(text=f'!Blend: {check.blend_count} blend files', icon='FILE_BLEND')
            box.label(text=f'Generated.N files: {len(check.generated)}')
            box.label(text='Highpoly_Generated + Resculpting_01 / Retopo_01 in every file',
                      icon='CHECKBOX_HLT' if check.all_ok else 'CHECKBOX_DEHLT')
            missing = [item for item in check.generated if not item.ok]
            for item in missing[:MAX_LISTED]:
                box.label(text=f'{item.name}: {item.summary()}', icon='ERROR')
            if len(missing) > MAX_LISTED:
                box.label(text=f'... and {len(missing) - MAX_LISTED} more')
    clear = layout.column(align=True)
    clear.enabled = column.enabled and scan is not None and (scan.file_count > 0 or orphan_count_total() > 0)
    clear.operator('object.polygroups_final_cleanup_clear', icon='TRASH')
    if STATE['status']:
        layout.label(text=STATE['status'], icon='INFO')


CLASSES = (OBJECT_OT_polygroups_final_cleanup_scan, OBJECT_OT_polygroups_final_cleanup_clear,
           OBJECT_OT_polygroups_clear_all_files)
