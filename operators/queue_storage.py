"""Queue storage helpers."""
import os
import re
from contextlib import contextmanager
import bpy


_BATCH_IMPORT_IDLE_STATE = {
    "batch_is_running": False,
    "batch_is_paused": False,
    "batch_stop_requested": False,
    "batch_cancel_requested": False,
    "batch_stage": "",
    "batch_last_error": "",
    "batch_total_count": 0,
    "batch_imported_count": 0,
    "batch_imported_object_count": 0,
    "batch_failed_count": 0,
    "batch_remaining_count": 0,
    "batch_import_progress": 0.0,
    "batch_current_progress": 0.0,
    "batch_remesh_progress": 0.0,
    "batch_baking_progress": 0.0,
    "batch_current_file": "",
    "batch_elapsed_seconds": 0.0,
    "batch_current_seconds": 0.0,
    "batch_average_seconds": 0.0,
    "batch_eta_seconds": -1.0,
}

def redo_source(collection):
    """Return the original highpoly in a numbered Generated collection."""
    match = re.fullmatch(r"Generated\.(\d+)", collection.name) if collection else None
    if match is None:
        return None
    name = f"Highpoly_Generated.{match.group(1)}"
    return next((obj for obj in collection.objects if obj.type == "MESH" and obj.name == name), None)

def active_highpoly_collection(context):
    """Resolve only the selected active Highpoly_Generated.N mesh."""
    source = context.active_object
    if (source is None or source.type != "MESH" or not source.select_get()
            or re.fullmatch(r"Highpoly_Generated\.(\d+)", source.name) is None):
        return None
    return next((collection for collection in source.users_collection
                 if redo_source(collection) == source), None)

RETOPO_PASS = re.compile(r"Retopo_(?:(\d+)_)?Highpoly_Generated\.(\d+)")
# Remesh passes finished per Retopo number: Retopo_ / Retopo_01 = first (stage 2), 02 = second (5), 03 = third (8).
RESUME_FROM_STAGE = {1: "batch_stage_narrow", 2: "batch_stage_second_narrow"}
FINAL_RETOPO_LEVEL = 3


def resume_state(context):
    """What Resume Selected can do for the active Retopo mesh, or None when it is not a Retopo pass result.

    Returns a dict with the mesh (``source``), its Generated.N ``collection``, the finished remesh
    ``level`` (1-3) and ``finished`` (Retopo_03 is the end of Phase 1)."""
    source = context.active_object
    if source is None or source.type != "MESH" or not source.select_get():
        return None
    match = RETOPO_PASS.fullmatch(source.name)
    if match is None:
        return None
    collection = next((col for col in source.users_collection
                       if redo_source(col) is not None and col.name == f"Generated.{match.group(2)}"), None)
    if collection is None:
        return None
    level = int(match.group(1) or 1)
    return dict(source=source, collection=collection, level=min(max(level, 1), FINAL_RETOPO_LEVEL),
                finished=level >= FINAL_RETOPO_LEVEL)


def redo_collections(view_layer):
    from .generated_visibility import generated_paths
    return [path[-1].collection for path in generated_paths(view_layer)
            if redo_source(path[-1].collection) is not None]

def selected_redo_collection(context):
    collections = redo_collections(context.view_layer)
    if not collections:
        return None
    name = context.scene.polygroups_model_preparation_settings.batch_redo_collection_name
    selected = next((collection for collection in collections if collection.name == name), None)
    if selected is not None:
        return selected
    active = context.active_object
    return next((collection for collection in collections
                 if active is not None and collection in active.users_collection), collections[0])

def reset_batch_import_settings(settings):
    """Return persisted/stale queue UI state to a clean idle state."""
    for name, value in _BATCH_IMPORT_IDLE_STATE.items():
        setattr(settings, name, value)

@contextmanager
def idle_import_state_for_copy():
    """Serialize idle results without stopping or changing the live queue."""
    snapshots = []
    try:
        for scene in bpy.data.scenes:
            groups = (
                (scene.polygroups_model_preparation_settings, _BATCH_IMPORT_IDLE_STATE),
                (scene.polygroups_baking_settings, {
                    "bake_task_is_running": False, "bake_task_stage": "",
                    "bake_task_progress": 0.0, "bake_task_message": "",
                }),
                (scene.polygroups_remesh_status, {
                    "is_running": False, "cancel_requested": False, "stage": "",
                    "progress": 0.0, "message": "",
                }),
            )
            for settings, defaults in groups:
                snapshots.append((settings, {
                    name: (getattr(settings, name), settings.is_property_set(name))
                    for name in defaults
                }))
                for name, value in defaults.items():
                    setattr(settings, name, value)
        yield
    finally:
        for settings, values in reversed(snapshots):
            for name, (value, was_set) in values.items():
                if was_set:
                    setattr(settings, name, value)
                else:
                    settings.property_unset(name)

def generated_collection_output_path(blend_filepath, collection_name):
    """Return the sibling blend path used for a numbered Generated collection."""
    match = re.fullmatch(r"Generated\.(\d+)", collection_name or "")
    if match is None:
        raise ValueError("Separate saving requires a numbered Generated.N collection")
    source = os.path.abspath(blend_filepath) if blend_filepath else ""
    if not source:
        raise ValueError("Save the working blend file before using separate collection saving")
    stem, _extension = os.path.splitext(os.path.basename(source))
    return os.path.join(
        os.path.dirname(source),
        f"{stem}_Generated_{match.group(1)}.blend",
    )

def generated_collection_files(blend_filepath):
    """Return numbered separate Generated files belonging to the working blend."""
    source = os.path.abspath(blend_filepath) if blend_filepath else ""
    if not source:
        raise ValueError("Save the working blend file before restoring separate collections")
    directory = os.path.dirname(source)
    stem, _extension = os.path.splitext(os.path.basename(source))
    pattern = re.compile(rf"^{re.escape(stem)}_Generated_(\d+)\.blend$", re.IGNORECASE)
    files = []
    for entry in os.scandir(directory):
        if not entry.is_file():
            continue
        match = pattern.fullmatch(entry.name)
        if match is not None:
            digits = match.group(1)
            files.append((int(digits), digits, entry.path))
    return sorted(files, key=lambda item: item[0])

def restore_retopo_collection(filepath, collection_name, scene, keep_all=False, include_highpoly=False):
    """Append Retopo objects and optionally Highpoly_Generated from a saved collection."""
    with bpy.data.libraries.load(filepath, link=False) as (source, target):
        if collection_name not in source.collections:
            return 0
        target.collections = [collection_name]
    imported_collection = target.collections[0] if target.collections else None
    if imported_collection is None:
        return 0

    destination = bpy.data.collections.get(collection_name)
    if destination is imported_collection:
        destination = None
    if destination is None:
        destination = bpy.data.collections.new(collection_name)
        scene.collection.children.link(destination)

    # Re-running restore should reproduce the file, not create .001 duplicates.
    for obj in list(destination.objects):
        if obj.name.startswith("Retopo_") or (include_highpoly and obj.name.startswith("Highpoly_Generated")):
            bpy.data.objects.remove(obj, do_unlink=True)

    imported_collections = []
    pending = [imported_collection]
    while pending:
        collection = pending.pop()
        if collection in imported_collections:
            continue
        imported_collections.append(collection)
        pending.extend(collection.children)
    imported_objects = set(imported_collection.all_objects)
    restored = []
    for obj in imported_objects:
        if keep_all or obj.name.startswith("Retopo_") or (include_highpoly and obj.name.startswith("Highpoly_Generated")):
            destination.objects.link(obj)
            restored.append(obj)

    # Discard excluded objects and the temporary collection hierarchy.
    # Restored objects survive through their links to the destination.
    for obj in imported_objects:
        if obj not in restored:
            bpy.data.objects.remove(obj, do_unlink=True)
    for collection in reversed(imported_collections):
        if collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection, do_unlink=True)
    return len(restored)

def write_collection_blend(filepath, collection):
    """Save a directly openable copy while keeping the working file active."""
    if collection.name not in bpy.data.collections:
        raise RuntimeError("The Generated.N collection no longer exists")
    # Do not use bpy.data.libraries.write with a temporary Scene here. Blender
    # 5.2 can crash in BKE_view_layer_copy_data when that partial write runs
    # from the modal Batch Import operator after baking. Save As Copy follows
    # Blender's regular full-file writer and does not change bpy.data.filepath.
    # Remove other generated datablocks, not merely their view-layer visibility.
    # Keep empty placeholders in the working file for Restore Separate Retopo.
    with idle_import_state_for_copy():
        result = bpy.ops.wm.save_as_mainfile(
            filepath=filepath, copy=True, relative_remap=True, check_existing=False,
        )
    if "FINISHED" not in result:
        raise RuntimeError("Blender did not finish saving the Generated.N copy")
    # Isolate the COPY in another Blender process. Removing IDs in the working
    # scene used to destroy earlier partial imports and invalidate queue refs.
    import subprocess
    script = f"""import bpy, re
keep = bpy.data.collections[{collection.name!r}]
keep_objects = set(keep.all_objects)
for other in list(bpy.data.collections):
    if other != keep and re.fullmatch(r'Generated(?:\\.\\d+)?', other.name):
        for obj in list(other.all_objects):
            if obj not in keep_objects and obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(other, do_unlink=True)
bpy.context.preferences.filepaths.save_version = 0
assert 'FINISHED' in bpy.ops.wm.save_as_mainfile(filepath={filepath!r}, check_existing=False)
"""
    process = subprocess.run(
        [bpy.app.binary_path, '--background', '--factory-startup', filepath,
         '--python-exit-code', '1', '--python-expr', script],
        capture_output=True, text=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if process.returncode:
        raise RuntimeError(f'Could not isolate separate output: {process.stderr[-2000:]}')

def move_to_collection(objects, collection):
    for obj in objects:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        for previous in list(obj.users_collection):
            if previous != collection:
                previous.objects.unlink(obj)
