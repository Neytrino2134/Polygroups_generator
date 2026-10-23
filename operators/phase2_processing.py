"""Separate-file restore, name repair and sequential Phase 2 rebaking."""
import os
import re
import time
import hashlib
from array import array
from pathlib import Path

import bpy
from bpy.app.handlers import persistent

from .batch_import import import_path_sort_key
from .import_queue import generated_collection_files, redraw

GENERATED = re.compile(r'^Generated(?:\.\d+)*$', re.I)
NUMBERED = re.compile(r'^Generated\.\d+(?:\.\d+)*$', re.I)
HIGH = re.compile(r'^Highpoly_Generated(?:\.\d+)*$', re.I)
LOW = re.compile(r'^Retopo_(\d+)_Highpoly_Generated(?:\.\d+)*$', re.I)
ACTIVE_PHASE2 = None


def scan_separated_files(blend_path, recursive=False):
    """Return stable file/collection pairs, excluding the current working file."""
    if not blend_path:
        raise ValueError('Save the working blend file before scanning Phase 2 files')
    source = os.path.normcase(os.path.realpath(blend_path))
    directory = os.path.dirname(source)
    if recursive:
        files = [os.path.join(root, name)
                 for root, dirs, names in os.walk(directory, followlinks=False)
                 for name in names if name.lower().endswith('.blend')]
    else:
        files = [path for _number, _digits, path in generated_collection_files(blend_path)]
    files = sorted({os.path.realpath(path) for path in files
                    if os.path.normcase(os.path.realpath(path)) != source},
                   key=lambda path: import_path_sort_key(os.path.relpath(path, directory)))
    entries, errors = [], []
    for path in files:
        try:
            with bpy.data.libraries.load(path, link=False) as (data, _target):
                names = sorted((name for name in data.collections if GENERATED.fullmatch(name)),
                               key=import_path_sort_key)
            entries.extend((path, name) for name in names)
        except Exception as error:
            errors.append(f'{os.path.basename(path)}: {error}')
    return files, entries, errors


def clear_generated_collections(scene=None):
    """Remove Generated.N trees; retain objects also linked outside those trees."""
    scene = scene or bpy.context.scene
    reachable, pending = set(), list(scene.collection.children)
    while pending:
        col = pending.pop()
        if col not in reachable:
            reachable.add(col)
            pending.extend(col.children)
    doomed = {col for col in reachable if NUMBERED.fullmatch(col.name)}
    parents = {}
    for parent in list(bpy.data.collections) + [scene.collection for scene in bpy.data.scenes]:
        for child in parent.children:
            parents.setdefault(child, set()).add(parent)
    while True:
        children = {child for col in doomed for child in col.children
                    if parents.get(child, set()) <= doomed}
        if children <= doomed:
            break
        doomed.update(children)
    meshes = set()
    for obj in list(bpy.data.objects):
        if obj.users_collection and set(obj.users_collection) <= doomed:
            if obj.type == 'MESH':
                meshes.add(obj.data)
            bpy.data.objects.remove(obj, do_unlink=True)
    for col in doomed:
        bpy.data.collections.remove(col, do_unlink=True)
    for mesh in meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def restore_collection(filepath, source_name, scene):
    """Append into a new free sequential slot; repair double Blender suffixes."""
    before = {kind: set(getattr(bpy.data, kind))
              for kind in ('collections', 'objects', 'meshes', 'materials', 'images')}
    try:
        with bpy.data.libraries.load(filepath, link=False) as (source, target):
            if source_name not in source.collections:
                raise ValueError(f'Missing collection: {source_name}')
            target.collections = [source_name]
        collection = target.collections[0]
        objects = sorted(collection.all_objects, key=lambda obj: import_path_sort_key(obj.name))
        highs = [obj for obj in objects if obj.type == 'MESH' and HIGH.fullmatch(obj.name)]
        lows = [(obj, int(LOW.fullmatch(obj.name).group(1))) for obj in objects
                if obj.type == 'MESH' and LOW.fullmatch(obj.name)]
        if len(highs) > 1:
            raise ValueError(f'{source_name}: more than one Highpoly source; cannot form a unique bake pair')
        if not highs and not lows:
            raise ValueError(f'{source_name}: no Highpoly_Generated or numbered Retopo meshes')

        # Reserve object names as well: an unlinked object may own a target name.
        used = set()
        for col in before['collections']:
            match = re.match(r'^Generated\.(\d+)', col.name, re.I)
            if match:
                used.add(int(match.group(1)))
        for obj in before['objects']:
            match = re.search(r'Generated\.(\d+)', obj.name, re.I)
            if match:
                used.add(int(match.group(1)))
        index = 1
        while index in used:
            index += 1
        digits = f'{index:03d}'
        collection.name = f'Generated.{digits}'
        collection.color_tag = 'COLOR_05'
        scene.collection.children.link(collection)
        # Vacate all imported names before assigning canonical destinations.
        for ordinal, obj in enumerate(highs + [obj for obj, _stage in lows]):
            obj.name = f'__Phase2_{digits}_{ordinal:05d}__'
        if highs:
            highs[0].name = f'Highpoly_Generated.{digits}'
        stages = set()
        for obj, stage in lows:
            # Heal duplicate stage names rather than letting Blender add .001.
            while stage in stages:
                stage += 1
            stages.add(stage)
            obj.name = f'Retopo_{stage:02d}_Highpoly_Generated.{digits}'
        return collection
    except Exception:
        # A malformed file must not leave appended objects or affect old data.
        for kind in ('objects', 'collections', 'meshes', 'materials', 'images'):
            ids = getattr(bpy.data, kind)
            for item in set(ids) - before[kind]:
                if kind in ('objects', 'collections') or item.users == 0:
                    ids.remove(item, do_unlink=True)
        raise


def bake_pair(collection):
    highs = [obj for obj in collection.all_objects if obj.type == 'MESH' and HIGH.fullmatch(obj.name)]
    lows = [(int(match.group(1)), obj) for obj in collection.all_objects
            if obj.type == 'MESH' and (match := LOW.fullmatch(obj.name))]
    if len(highs) != 1 or not lows:
        raise ValueError(f'{collection.name}: Auto Bake requires one Highpoly and a numbered Retopo')
    return highs[0], max(lows, key=lambda item: item[0])[1]


def mesh_uv_signature(mesh):
    """Detect geometry/topology/UV changes without selection-state noise."""
    digest = hashlib.blake2b()
    for collection, attr, width, kind in (
            (mesh.vertices, 'co', 3, 'f'), (mesh.edges, 'vertices', 2, 'i'),
            (mesh.loops, 'vertex_index', 1, 'i'),
            (mesh.polygons, 'loop_total', 1, 'i')):
        values = array(kind, [0]) * (len(collection) * width)
        collection.foreach_get(attr, values)
        digest.update(len(values).to_bytes(8, 'little'))
        digest.update(values.tobytes())
    for layer in mesh.uv_layers:
        digest.update(layer.name.encode('utf-8'))
        values = array('f', [0]) * (len(layer.data) * 2)
        layer.data.foreach_get('uv', values)
        digest.update(values.tobytes())
    return digest.digest()


def remove_mesh_objects(objects):
    """Delete objects and only their now-unused mesh datablocks."""
    count = 0
    for obj in list(objects):
        if obj.library:
            continue
        mesh = obj.data if obj.type == 'MESH' else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        count += 1
    return count


def disable_completed_collection(collection, view_layer):
    collection.hide_render = True
    collection.hide_viewport = True
    def visit(layer):
        if layer.collection == collection:
            layer.exclude = True
        else:
            for child in layer.children:
                visit(child)
    visit(view_layer.layer_collection)



class Phase2Queue:
    def __init__(self, context, entries, auto_bake, repair, report):
        self.scene, self.view_layer = context.scene, context.view_layer
        self.settings = self.scene.polygroups_model_preparation_settings
        self.entries, self.auto_bake, self.repair = list(entries), auto_bake, repair
        self.report = report
        self.index, self.stage, self.collection = 0, 'RESTORE', None
        self.finished, self.stop_requested, self.timer = False, False, None
        self.saved_bake = {}
        self.results = []
        self.baked_pair = None

    def begin(self):
        settings = self.settings
        settings.phase2_is_running = True
        settings.phase2_done_count = settings.phase2_failed_count = 0
        settings.phase2_total_count = len(self.entries)
        settings.phase2_status = 'Starting Phase 2'

    def repair_mesh(self, context):
        if not self.settings.phase2_mesh_auto_repair:
            return
        from .rename_objects import ensure_collection_visible_in_view_layer
        lows = [(int(match.group(1)), obj) for obj in self.collection.all_objects
                if obj.type == 'MESH' and (match := LOW.fullmatch(obj.name))]
        if not lows:
            raise ValueError(f'{self.collection.name}: Auto Repair requires a numbered Retopo')
        low = max(lows, key=lambda item: item[0])[1]
        if not ensure_collection_visible_in_view_layer(context, self.collection):
            raise ValueError(f'{self.collection.name}: cannot make collection visible')
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in context.selected_objects:
            obj.select_set(False)
        low.hide_viewport = low.hide_render = low.hide_select = False
        low.hide_set(False)
        low.select_set(True)
        self.view_layer.objects.active = low
        if low.data.users > 1:
            low.data = low.data.copy()
        check_changes = self.settings.phase2_repack_only_if_changed
        before = mesh_uv_signature(low.data) if check_changes else None
        result = bpy.ops.mesh.polygroups_repair_mesh_folds(
            'EXEC_DEFAULT', action='REPAIR', fix_folds=True,
            fix_degenerate=True, fix_zero_area=False, selected_only=False)
        if 'FINISHED' not in result:
            raise RuntimeError(f'Auto Repair failed for {low.name}; processing skipped')
        changed = not check_changes or mesh_uv_signature(low.data) != before
        if self.settings.phase2_repack_after_repair and changed:
            if low.data.uv_layers.active is None:
                raise ValueError(f'{low.name}: UV repack requires a UV map')
            result = bpy.ops.object.polygroups_uvpackmaster_pack('EXEC_DEFAULT')
            if 'FINISHED' not in result:
                raise RuntimeError(f'UVPackmaster PACK failed for {low.name}; processing skipped')

    def start_bake(self, context):
        from .rename_objects import ensure_collection_visible_in_view_layer
        high, low = bake_pair(self.collection)
        self.baked_pair = (high, low)
        if low.data.uv_layers.active is None:
            raise ValueError(f'{low.name}: Auto Bake requires a UV map')
        if not ensure_collection_visible_in_view_layer(context, self.collection):
            raise ValueError(f'{self.collection.name}: cannot make collection visible')
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in (high, low):
            obj.hide_viewport = obj.hide_render = obj.hide_select = False
            obj.hide_set(False)
            obj.select_set(True)
        self.view_layer.objects.active = low
        bake = self.scene.polygroups_baking_settings
        overrides = dict(use_selected_to_active=True, auto_save_textures_after_bake=True,
                         bake_artifact_mask=self.repair, bake_artifact_autofill=self.repair)
        if not (bake.use_auto_cage or bake.use_smart_cage or bake.autogenerate_smart_cage):
            overrides['use_auto_cage'] = True
        if self.repair:
            overrides.update(bake_artifact_mode='FULL', bake_artifact_match_normal=True)
        self.saved_bake = {key: getattr(bake, key) for key in overrides}
        for key, value in overrides.items():
            setattr(bake, key, value)
        bake.bake_task_stage = ''
        result = bpy.ops.object.polygroups_checked_prepare_and_bake('EXEC_DEFAULT')
        if not ({'FINISHED', 'RUNNING_MODAL'} & result):
            raise RuntimeError(f'Auto Bake could not start for {low.name}')

    def restore_bake_settings(self):
        bake = self.scene.polygroups_baking_settings
        for key, value in self.saved_bake.items():
            setattr(bake, key, value)
        self.saved_bake.clear()

    def complete(self, error=''):
        self.restore_bake_settings()
        if self.collection is not None:
            if not error:
                if self.stage == 'BAKE_WAIT' and self.baked_pair is not None:
                    high, low = self.baked_pair
                    doomed = []
                    if self.settings.phase2_delete_high_after_bake:
                        doomed.append(high)
                    if self.settings.phase2_delete_lower_retopo:
                        stage = int(LOW.fullmatch(low.name).group(1))
                        doomed.extend(obj for obj in self.collection.all_objects
                            if obj.type == 'MESH' and (match := LOW.fullmatch(obj.name))
                            and int(match.group(1)) < stage)
                    # Preserve objects linked outside the completed collection tree.
                    tree = set()
                    def visit(col):
                        tree.add(col)
                        for child in col.children:
                            visit(child)
                    visit(self.collection)
                    for obj in doomed:
                        if set(obj.users_collection) <= tree:
                            remove_mesh_objects([obj])
                        else:
                            for col in list(obj.users_collection):
                                if col in tree:
                                    col.objects.unlink(obj)
                disable_completed_collection(self.collection, self.view_layer)
            self.collection.color_tag = 'COLOR_05' if error else 'COLOR_02'
        self.baked_pair = None
        if error:
            self.settings.phase2_failed_count += 1
            self.report({'WARNING'}, f'{self.entries[self.index]}: {error}')
        else:
            self.settings.phase2_done_count += 1
        self.results.append((self.entries[self.index], error))
        self.index += 1
        self.stage, self.collection = 'RESTORE', None

    def finish(self, stopped=False):
        if self.finished:
            return
        self.restore_bake_settings()
        self.settings.phase2_is_running = False
        self.settings.phase2_status = ('Stopped' if stopped else 'Completed') + (
            f': {self.settings.phase2_done_count} OK, {self.settings.phase2_failed_count} failed')
        self.finished = True

    def step(self, context):
        bake = self.scene.polygroups_baking_settings
        # Stop after the active bake completes; never mutate its inputs mid-job.
        if bake.bake_task_is_running:
            return
        if self.stop_requested and self.stage != 'BAKE_WAIT':
            self.finish(stopped=True)
            return
        if self.index >= len(self.entries):
            self.finish()
            return
        path, name = self.entries[self.index]
        self.settings.phase2_status = f'{self.index+1}/{len(self.entries)}: {name} / {self.stage}'
        try:
            if self.stage == 'RESTORE':
                self.collection = restore_collection(path, name, self.scene)
                self.view_layer.update()
                self.repair_mesh(context)
                if self.auto_bake:
                    self.stage = 'BAKE_START'
                else:
                    self.complete()
            elif self.stage == 'BAKE_START':
                self.start_bake(context)
                self.stage = 'BAKE_WAIT'
            elif self.stage == 'BAKE_WAIT':
                if bake.bake_task_stage != 'DONE':
                    raise RuntimeError(f'Auto Bake failed: {bake.bake_task_message}')
                self.complete()
        except Exception as error:
            self.complete(str(error))


@persistent
def stop_phase2(*_args):
    global ACTIVE_PHASE2
    if ACTIVE_PHASE2 is not None:
        queue = ACTIVE_PHASE2
        queue.finish(stopped=True)
        if queue.timer is not None:
            bpy.context.window_manager.event_timer_remove(queue.timer)
            queue.timer = None
        ACTIVE_PHASE2 = None


def available(context):
    from .import_queue import ACTIVE_QUEUE
    from .remesh_progress import ACTIVE_REMESH
    settings = context.scene.polygroups_model_preparation_settings
    return bool(bpy.data.filepath and ACTIVE_PHASE2 is None and ACTIVE_QUEUE is None
                and ACTIVE_REMESH is None and not settings.batch_is_running
                and not bpy.app.is_job_running('OBJECT_BAKE')
                and not context.scene.polygroups_baking_settings.bake_task_is_running)


def scan(context, report):
    settings = context.scene.polygroups_model_preparation_settings
    files, entries, errors = scan_separated_files(bpy.data.filepath, settings.phase2_scan_subfolders)
    settings.phase2_scanned_files = len(files)
    settings.phase2_scanned_collections = len(entries)
    settings.phase2_status = f'{len(files)} blend file(s), {len(entries)} Generated collection(s)'
    for error in errors:
        report({'WARNING'}, error)
    return entries


class OBJECT_OT_polygroups_phase2_scan(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_scan'
    bl_label = 'Scan Separated Files'
    bl_description = 'Scan beside the working blend; optionally include all blends in subfolders'

    @classmethod
    def poll(cls, context):
        return available(context)

    def execute(self, context):
        try:
            scan(context, self.report)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_polygroups_phase2_restore(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_restore'
    bl_label = 'Restore from Separate Files'
    bl_description = 'Restore with repaired numbering and optionally rebake the highest Retopo stage'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return available(context)

    def execute(self, context):
        global ACTIVE_PHASE2
        settings = context.scene.polygroups_model_preparation_settings
        try:
            # Re-scan before any deletion: changes to files/options cannot leave
            # the restore using a stale list or clearing the scene on no input.
            entries = scan(context, self.report)
            if not entries:
                self.report({'WARNING'}, 'No Generated collections found; current collections were kept')
                return {'CANCELLED'}
            if settings.phase2_clear_generated:
                clear_generated_collections(context.scene)
            queue = Phase2Queue(context, entries, settings.phase2_auto_bake,
                                settings.phase2_repair_artifacts, self.report)
            ACTIVE_PHASE2 = queue
            queue.begin()
            if bpy.app.background:
                while not queue.finished:
                    queue.step(context)
                ACTIVE_PHASE2 = None
                return {'FINISHED'}
            queue.timer = context.window_manager.event_timer_add(.2, window=context.window)
            self._next_tick = time.monotonic() + .2
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception as error:
            stop_phase2()
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

    def modal(self, context, event):
        queue = ACTIVE_PHASE2
        if queue is None:
            return {'CANCELLED'}
        if event.type == 'ESC' and event.value == 'PRESS':
            queue.stop_requested = True
            return {'PASS_THROUGH'}
        if event.type == 'TIMER' and time.monotonic() >= self._next_tick:
            self._next_tick = time.monotonic() + .2
            try:
                with context.temp_override(scene=queue.scene, view_layer=queue.view_layer):
                    queue.step(context)
            except Exception as error:
                self.report({'ERROR'}, str(error))
                stop_phase2()
                return {'CANCELLED'}
            redraw(context)
            if queue.finished:
                stopped = queue.stop_requested
                stop_phase2()
                return {'CANCELLED'} if stopped else {'FINISHED'}
        return {'PASS_THROUGH'}


class OBJECT_OT_polygroups_phase2_stop(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_stop'
    bl_label = 'Stop Phase 2'
    bl_description = 'Stop after the current bake has finished'

    @classmethod
    def poll(cls, context):
        return ACTIVE_PHASE2 is not None

    def execute(self, context):
        ACTIVE_PHASE2.stop_requested = True
        return {'FINISHED'}


class OBJECT_OT_polygroups_phase2_clear_backups(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_clear_backups'
    bl_label = 'Delete All Backup_Retopo Objects'
    bl_description = 'Remove all local mesh objects whose names start with Backup_Retopo_'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_model_preparation_settings
        return (context.mode == 'OBJECT' and ACTIVE_PHASE2 is None
            and not settings.phase2_is_running and not settings.batch_is_running
            and not context.scene.polygroups_baking_settings.bake_task_is_running
            and not bpy.app.is_job_running('OBJECT_BAKE'))

    def execute(self, context):
        count = remove_mesh_objects(obj for obj in bpy.data.objects
            if obj.type == 'MESH' and obj.name.lower().startswith('backup_retopo_'))
        self.report({'INFO'}, f'Deleted {count} Backup_Retopo objects')
        return {'FINISHED'}


_FILE_SCAN = None


def blend_manager_root():
    if not bpy.data.filepath:
        raise ValueError('Save the active blend file first')
    current = Path(bpy.data.filepath).resolve(strict=True)
    return current.parent, current


def scan_blend_manager(root, current):
    destination = root / '!Blend'
    if destination.is_symlink() or os.path.isjunction(destination):
        raise ValueError('!Blend must be a regular folder inside the project')
    records, errors = [], []
    for folder, dirs, files in os.walk(root, followlinks=False,
            onerror=lambda error: errors.append(str(error))):
        dirs[:] = [name for name in dirs if Path(folder, name) != destination
                   and not Path(folder, name).is_symlink()
                   and not os.path.isjunction(Path(folder, name))]
        for name in files:
            path = Path(folder, name)
            if path.suffix.lower() != '.blend' or path.is_symlink():
                continue
            try:
                path = path.resolve(strict=True)
                if path == current or not path.is_relative_to(root):
                    continue
                stat = path.stat()
                records.append((path, stat.st_size, stat.st_mtime_ns))
            except OSError as error:
                errors.append(str(error))
    return records, errors


class OBJECT_OT_polygroups_phase2_files_scan(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_files_scan'
    bl_label = 'Scan Blend Files From Current Folder'
    bl_description = 'Scan all subfolders; exclude the open file and !Blend destination'

    @classmethod
    def poll(cls, context):
        return available(context)

    def execute(self, context):
        global _FILE_SCAN
        settings = context.scene.polygroups_model_preparation_settings
        try:
            root, current = blend_manager_root()
            records, errors = scan_blend_manager(root, current)
            _FILE_SCAN = (root, current, records, len(errors))
            settings.phase2_files_found = len(records)
            settings.phase2_files_status = f'Found: {len(records)} blend files / {len(errors)} scan errors'
            settings.phase2_files_cleanup_status = ''
        except (ValueError, OSError) as error:
            _FILE_SCAN = None
            settings.phase2_files_found = 0
            settings.phase2_files_status = str(error)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_polygroups_phase2_files_move(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_files_move'
    bl_label = 'Move Blend Files to !Blend'
    bl_description = 'Move scanned files preserving subfolders; existing destination files are never overwritten'

    @classmethod
    def poll(cls, context):
        return available(context)

    def execute(self, context):
        global _FILE_SCAN
        settings = context.scene.polygroups_model_preparation_settings
        try:
            root, current = blend_manager_root()
            if _FILE_SCAN is None or _FILE_SCAN[:2] != (root, current):
                raise ValueError('Scan the current folder before moving files')
            moved, errors = 0, _FILE_SCAN[3]
            for source, size, modified in _FILE_SCAN[2]:
                try:
                    resolved = source.resolve(strict=True)
                    if source.is_symlink() or resolved != source or not resolved.is_relative_to(root):
                        raise ValueError('Source path changed')
                    stat = source.stat()
                    if (stat.st_size, stat.st_mtime_ns) != (size, modified):
                        raise ValueError('Source file changed after scanning')
                    target = root / '!Blend' / source.relative_to(root)
                    # Check the final absolute destination before creating or moving.
                    if not target.resolve().is_relative_to(root / '!Blend'):
                        raise ValueError('Destination escapes !Blend')
                    if target.exists():
                        raise ValueError('Destination already exists')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(target)
                    moved += 1
                except (ValueError, OSError) as error:
                    errors += 1
                    self.report({'WARNING'}, f'{source.name}: {error}')
            _FILE_SCAN = None
            settings.phase2_files_found = 0
            settings.phase2_files_status = f'{moved} files moved / {errors} errors'
            if moved:
                settings.phase2_scan_subfolders = True
            if settings.phase2_files_cleanup:
                cleanup = context.window_manager.airetopo_save_cleanup
                cleanup.directory = str(root)
                result = bpy.ops.wm.airetopo_scan_save_cleanup()
                if 'FINISHED' in result and cleanup.file_count:
                    result = bpy.ops.wm.airetopo_clean_backup_saves()
                settings.phase2_files_cleanup_status = cleanup.status
                if 'FINISHED' not in result:
                    self.report({'WARNING'}, 'Save Cleanup did not complete')
            self.report({'WARNING'} if errors else {'INFO'}, settings.phase2_files_status)
            return {'FINISHED'}
        except (ValueError, OSError) as error:
            self.report({'ERROR'}, str(error))
            settings.phase2_files_status = str(error)
            return {'CANCELLED'}


CLASSES = (OBJECT_OT_polygroups_phase2_clear_backups, OBJECT_OT_polygroups_phase2_files_scan, OBJECT_OT_polygroups_phase2_files_move,
           OBJECT_OT_polygroups_phase2_scan, OBJECT_OT_polygroups_phase2_restore,
           OBJECT_OT_polygroups_phase2_stop)
