"""Versioned autosaves that live beside the current blend file."""

from pathlib import Path
import os
import shutil
import tempfile
import time
import uuid

import bpy
from bpy.app.handlers import persistent


_SESSION_ID = uuid.uuid4().hex[:12]
_SAVING_COPY = False
_LAST_STATUS = ""
_LAST_AUTOSAVE_TIME = None
_LAST_REGULAR_SAVE_TIME = None
_LAST_EVENT = "NONE"
_TEMP_MAX_AGE_DAYS = 7


def _preferences():
    context = getattr(bpy, "context", None)
    preferences = getattr(context, "preferences", None)
    addons = getattr(preferences, "addons", None)
    if addons is None:
        return None
    addon = addons.get(__package__)
    return addon.preferences if addon is not None else None


def _temp_root():
    return Path(tempfile.gettempdir()) / "polygroups_generator" / "autosave"


def _session_temp_dir():
    return _temp_root() / _SESSION_ID


def autosave_paths(filepath, versions, temp_directory=None):
    """Return newest-to-oldest version paths without touching the filesystem."""
    versions = max(1, int(versions))
    if filepath:
        source = Path(filepath)
        directory = source.parent
        basename = source.name
    else:
        directory = Path(temp_directory) if temp_directory else _session_temp_dir()
        basename = "Unsaved.blend"
    return [directory / f"{basename}Autosave{index}" for index in range(1, versions + 1)]


def current_autosave_directory():
    filepath = bpy.data.filepath
    return Path(filepath).parent if filepath else _session_temp_dir()


def _clock_time(timestamp):
    return time.strftime("%H:%M:%S", time.localtime(timestamp)) if timestamp else "—"


def status_snapshot():
    """Return presentation-ready state for the N-panel status block."""
    return {
        "event": _LAST_EVENT,
        "autosave_time": _clock_time(_LAST_AUTOSAVE_TIME),
        "regular_save_time": _clock_time(_LAST_REGULAR_SAVE_TIME),
        "message": _LAST_STATUS,
    }


def _tag_redraw():
    window_manager = getattr(bpy.context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _read_status_from_disk():
    global _LAST_AUTOSAVE_TIME, _LAST_REGULAR_SAVE_TIME, _LAST_EVENT, _LAST_STATUS
    _LAST_AUTOSAVE_TIME = None
    _LAST_REGULAR_SAVE_TIME = None
    _LAST_EVENT = "NONE"
    _LAST_STATUS = ""
    data = getattr(bpy, "data", None)
    filepath = getattr(data, "filepath", "")
    if not filepath:
        _tag_redraw()
        return

    project = Path(filepath)
    try:
        _LAST_REGULAR_SAVE_TIME = project.stat().st_mtime
    except OSError:
        pass
    newest_autosave = Path(f"{project}Autosave1")
    try:
        _LAST_AUTOSAVE_TIME = newest_autosave.stat().st_mtime
    except OSError:
        pass
    if _LAST_AUTOSAVE_TIME and (
        not _LAST_REGULAR_SAVE_TIME or _LAST_AUTOSAVE_TIME > _LAST_REGULAR_SAVE_TIME
    ):
        _LAST_EVENT = "CUSTOM"
    elif _LAST_REGULAR_SAVE_TIME:
        _LAST_EVENT = "REGULAR"
    _tag_redraw()


def _initialize_status_timer():
    """Wait until Blender releases _RestrictData after add-on registration."""
    data = getattr(bpy, "data", None)
    if not hasattr(data, "filepath"):
        return 0.1
    _read_status_from_disk()
    return None


def _rotate(paths):
    oldest = paths[-1]
    if oldest.exists():
        oldest.unlink()
    for index in range(len(paths) - 2, -1, -1):
        source = paths[index]
        if source.exists():
            os.replace(source, paths[index + 1])


def _prune_excess_versions(paths):
    prefix = paths[0].name.rsplit("Autosave", 1)[0] + "Autosave"
    keep = set(paths)
    for candidate in paths[0].parent.glob(f"{prefix}*"):
        suffix = candidate.name[len(prefix):]
        if candidate not in keep and suffix.isdigit():
            try:
                candidate.unlink()
            except OSError:
                pass


def _save_copy(destination):
    global _SAVING_COPY
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.{_SESSION_ID}.writing.blend"
    try:
        _SAVING_COPY = True
        result = bpy.ops.wm.save_as_mainfile(
            filepath=str(staging),
            check_existing=False,
            copy=True,
        )
        if "FINISHED" not in result:
            raise RuntimeError("Blender cancelled the autosave")
        if not staging.exists():
            # Some Blender versions append .blend for an unfamiliar suffix.
            appended = Path(f"{staging}.blend")
            if not appended.exists():
                raise RuntimeError("Blender did not create the autosave copy")
            staging = appended
        os.replace(staging, destination)
    finally:
        _SAVING_COPY = False
        for candidate in (staging, Path(f"{staging}.blend")):
            try:
                if candidate.exists():
                    candidate.unlink()
            except OSError:
                pass


def save_now(force=False):
    """Create one custom autosave. Returns (saved, user-facing status)."""
    global _LAST_AUTOSAVE_TIME, _LAST_EVENT, _LAST_STATUS
    preferences = _preferences()
    if preferences is None or preferences.autosave_mode != "CUSTOM":
        return False, "Custom autosave is disabled"
    if _SAVING_COPY:
        return False, "Autosave is already running"
    if not force and not bpy.data.is_dirty:
        return False, "No new changes"
    window_manager = getattr(bpy.context, "window_manager", None)
    if getattr(window_manager, "is_interface_locked", False):
        return False, "Blender is busy; autosave postponed"

    paths = autosave_paths(
        bpy.data.filepath,
        preferences.autosave_versions,
        _session_temp_dir(),
    )
    try:
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        staging_target = paths[0].parent / f".{paths[0].name}.{_SESSION_ID}.new"
        _save_copy(staging_target)
        _rotate(paths)
        os.replace(staging_target, paths[0])
        _prune_excess_versions(paths)
    except Exception as error:
        _LAST_STATUS = f"Autosave failed: {error}"
        _LAST_EVENT = "ERROR"
        _tag_redraw()
        print(f"AI Retopo custom autosave: {_LAST_STATUS}")
        return False, _LAST_STATUS

    _LAST_AUTOSAVE_TIME = time.time()
    _LAST_EVENT = "CUSTOM"
    _LAST_STATUS = f"Saved {paths[0]}"
    _tag_redraw()
    print(f"AI Retopo custom autosave: {_LAST_STATUS}")
    return True, _LAST_STATUS


def _timer_callback():
    preferences = _preferences()
    if preferences is None:
        return None
    interval = max(1.0, float(preferences.autosave_interval_minutes)) * 60.0
    if preferences.autosave_mode == "CUSTOM":
        save_now()
    return interval


def _cleanup_session_temp():
    session_dir = _session_temp_dir()
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)


def _cleanup_stale_temp():
    root = _temp_root()
    if not root.exists():
        return
    cutoff = time.time() - (_TEMP_MAX_AGE_DAYS * 24 * 60 * 60)
    for directory in root.iterdir():
        try:
            if directory.is_dir() and directory.stat().st_mtime < cutoff:
                shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            pass


@persistent
def _save_post(_unused):
    global _LAST_REGULAR_SAVE_TIME, _LAST_EVENT, _LAST_STATUS
    if _SAVING_COPY:
        return
    if bpy.data.filepath:
        _LAST_REGULAR_SAVE_TIME = time.time()
        _LAST_EVENT = "REGULAR"
        _LAST_STATUS = f"Saved {bpy.data.filepath}"
        _cleanup_session_temp()
        _tag_redraw()


@persistent
def _load_post(_unused):
    _cleanup_session_temp()
    _read_status_from_disk()


def configure(context=None):
    """Apply the selected mode and restart the interval from this moment."""
    preferences = _preferences()
    if preferences is None:
        return
    filepaths = (context or bpy.context).preferences.filepaths
    filepaths.use_auto_save_temporary_files = preferences.autosave_mode == "NATIVE"
    if bpy.app.timers.is_registered(_timer_callback):
        bpy.app.timers.unregister(_timer_callback)
    bpy.app.timers.register(
        _timer_callback,
        first_interval=max(1.0, float(preferences.autosave_interval_minutes)) * 60.0,
        persistent=True,
    )


class AIRETOPO_OT_custom_autosave_now(bpy.types.Operator):
    bl_idname = "wm.airetopo_custom_autosave_now"
    bl_label = "Create Autosave Now"
    bl_description = "Immediately create and rotate a custom autosave copy"

    def execute(self, _context):
        saved, status = save_now(force=True)
        self.report({"INFO" if saved else "WARNING"}, status)
        return {"FINISHED" if saved else "CANCELLED"}


def register():
    bpy.utils.register_class(AIRETOPO_OT_custom_autosave_now)
    for handler, callback in (
        (bpy.app.handlers.save_post, _save_post),
        (bpy.app.handlers.load_post, _load_post),
    ):
        if callback not in handler:
            handler.append(callback)
    _cleanup_stale_temp()
    if not bpy.app.timers.is_registered(_initialize_status_timer):
        bpy.app.timers.register(_initialize_status_timer, first_interval=0.1)
    configure()


def unregister():
    if bpy.app.timers.is_registered(_initialize_status_timer):
        bpy.app.timers.unregister(_initialize_status_timer)
    if bpy.app.timers.is_registered(_timer_callback):
        bpy.app.timers.unregister(_timer_callback)
    # Never leave Blender without any autosave after this add-on is disabled.
    bpy.context.preferences.filepaths.use_auto_save_temporary_files = True
    for handler, callback in (
        (bpy.app.handlers.save_post, _save_post),
        (bpy.app.handlers.load_post, _load_post),
    ):
        if callback in handler:
            handler.remove(callback)
    bpy.utils.unregister_class(AIRETOPO_OT_custom_autosave_now)
