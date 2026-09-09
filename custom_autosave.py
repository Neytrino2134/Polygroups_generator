"""Versioned autosaves that live beside the current blend file."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
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
_RECENT_CACHE_SECONDS = 5.0
_RECENT_CACHE_TIME = 0.0
_RECENT_CACHE = []
_RECOVERY_AUTOSAVE_PATH = ""
_RECOVERY_ORIGINAL_PATH = ""
_RECOVERY_RESTORED_PATH = ""
_RECOVERY_PROP_AUTOSAVE = "airetopo_recovery_autosave"
_RECOVERY_PROP_ORIGINAL = "airetopo_recovery_original"
_RECOVERY_PROP_RESTORED = "airetopo_recovery_restored"
_CHANGES_SINCE_AUTOSAVE = False


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


def _autosave_version(path):
    _prefix, separator, suffix = Path(path).name.rpartition("Autosave")
    return int(suffix) if separator and suffix.isdigit() and int(suffix) > 0 else None


def collect_recent_autosaves(temp_root, project_paths, limit=8):
    """Collect valid custom autosaves, newest first, without depending on Blender."""
    candidates = []
    root = Path(temp_root)
    if root.exists():
        try:
            candidates.extend(root.rglob("*Autosave*"))
        except OSError:
            pass

    for project_path in project_paths:
        project = Path(project_path)
        if _autosave_version(project) is not None:
            candidates.append(project)
        try:
            candidates.extend(project.parent.glob(f"{project.name}Autosave*"))
        except OSError:
            pass

    entries = []
    seen = set()
    for candidate in candidates:
        if _autosave_version(candidate) is None:
            continue
        try:
            if not candidate.is_file() or candidate.stat().st_size <= 0:
                continue
            absolute = candidate.resolve()
            key = os.path.normcase(str(absolute))
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "filepath": str(absolute),
                    "name": candidate.name,
                    "modified": candidate.stat().st_mtime,
                }
            )
        except OSError:
            continue

    entries.sort(key=lambda entry: entry["modified"], reverse=True)
    return entries[:max(0, int(limit))]


def _recent_project_paths():
    try:
        config_directory = bpy.utils.user_resource("CONFIG")
    except (AttributeError, RuntimeError):
        return []
    if not config_directory:
        return []
    recent_file = Path(config_directory) / "recent-files.txt"
    try:
        return [line.strip() for line in recent_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []


def _invalidate_recent_cache():
    global _RECENT_CACHE_TIME
    _RECENT_CACHE_TIME = 0.0


def recent_autosaves(limit=8, refresh=False):
    """Return cached recovery entries for the startup N-panel."""
    global _RECENT_CACHE, _RECENT_CACHE_TIME
    now = time.monotonic()
    if refresh or not _RECENT_CACHE_TIME or now - _RECENT_CACHE_TIME >= _RECENT_CACHE_SECONDS:
        _RECENT_CACHE = collect_recent_autosaves(
            _temp_root(),
            _recent_project_paths(),
            limit=32,
        )
        _RECENT_CACHE_TIME = now
    return _RECENT_CACHE[:max(0, int(limit))]


def _original_path_for_autosave(filepath):
    autosave = Path(filepath).resolve()
    version = _autosave_version(autosave)
    if version is None or _path_is_within(autosave, _temp_root()):
        return None
    suffix = f"Autosave{version}"
    return autosave.with_name(autosave.name[:-len(suffix)])


def _restored_path_for_autosave(filepath, timestamp=None):
    autosave = Path(filepath).resolve()
    original = _original_path_for_autosave(autosave)
    if original is None:
        directory = _temp_root() / "recovered"
        stem = "Unsaved"
    else:
        directory = original.parent
        stem = original.stem
    stamp = time.strftime(
        "%Y-%m-%d_%H-%M-%S",
        time.localtime(timestamp if timestamp is not None else time.time()),
    )
    candidate = directory / f"{stem}_restored_{stamp}.blend"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}_restored_{stamp}_{index}.blend"
        index += 1
    return candidate


def _scene_recovery_value(key):
    scene = getattr(getattr(bpy, "context", None), "scene", None)
    if scene is None:
        return ""
    try:
        return str(scene.get(key, ""))
    except (AttributeError, ReferenceError):
        return ""


def _set_recovery_state(autosave_path, original_path, restored_path):
    global _RECOVERY_AUTOSAVE_PATH, _RECOVERY_ORIGINAL_PATH, _RECOVERY_RESTORED_PATH
    _RECOVERY_AUTOSAVE_PATH = str(autosave_path or "")
    _RECOVERY_ORIGINAL_PATH = str(original_path or "")
    _RECOVERY_RESTORED_PATH = str(restored_path or "")
    scene = getattr(getattr(bpy, "context", None), "scene", None)
    if scene is not None:
        scene[_RECOVERY_PROP_AUTOSAVE] = _RECOVERY_AUTOSAVE_PATH
        scene[_RECOVERY_PROP_ORIGINAL] = _RECOVERY_ORIGINAL_PATH
        scene[_RECOVERY_PROP_RESTORED] = _RECOVERY_RESTORED_PATH


def _load_recovery_state():
    global _RECOVERY_AUTOSAVE_PATH, _RECOVERY_ORIGINAL_PATH, _RECOVERY_RESTORED_PATH
    _RECOVERY_AUTOSAVE_PATH = _scene_recovery_value(_RECOVERY_PROP_AUTOSAVE)
    _RECOVERY_ORIGINAL_PATH = _scene_recovery_value(_RECOVERY_PROP_ORIGINAL)
    _RECOVERY_RESTORED_PATH = _scene_recovery_value(_RECOVERY_PROP_RESTORED)


def _clear_recovery_state():
    global _RECOVERY_AUTOSAVE_PATH, _RECOVERY_ORIGINAL_PATH, _RECOVERY_RESTORED_PATH
    _RECOVERY_AUTOSAVE_PATH = ""
    _RECOVERY_ORIGINAL_PATH = ""
    _RECOVERY_RESTORED_PATH = ""
    scene = getattr(getattr(bpy, "context", None), "scene", None)
    if scene is not None:
        for key in (
            _RECOVERY_PROP_AUTOSAVE,
            _RECOVERY_PROP_ORIGINAL,
            _RECOVERY_PROP_RESTORED,
        ):
            try:
                del scene[key]
            except (KeyError, ReferenceError):
                pass


def recovery_snapshot():
    """Return recovery state persisted in the restored blend file."""
    if not _RECOVERY_RESTORED_PATH:
        _load_recovery_state()
    current = getattr(getattr(bpy, "data", None), "filepath", "")
    active = bool(
        current
        and _RECOVERY_RESTORED_PATH
        and os.path.normcase(str(Path(current).resolve()))
        == os.path.normcase(str(Path(_RECOVERY_RESTORED_PATH).resolve()))
    )
    return {
        "active": active,
        "autosave": _RECOVERY_AUTOSAVE_PATH,
        "original": _RECOVERY_ORIGINAL_PATH,
        "restored": _RECOVERY_RESTORED_PATH,
    }


def _clock_time(timestamp):
    return time.strftime("%H:%M:%S", time.localtime(timestamp)) if timestamp else "—"


def status_snapshot():
    """Return presentation-ready state for the N-panel status block."""
    recovery = recovery_snapshot()
    current = getattr(getattr(bpy, "data", None), "filepath", "")
    regular_path = recovery["original"] if recovery["active"] and recovery["original"] else current
    if recovery["active"] and recovery["autosave"]:
        autosave_path = recovery["autosave"]
    else:
        autosave_path = autosave_paths(
            regular_path,
            1,
            _session_temp_dir(),
        )[0]

    def existing_file(path):
        try:
            candidate = Path(path)
            return str(candidate.resolve()) if candidate.is_file() else ""
        except OSError:
            return ""

    return {
        "event": _LAST_EVENT,
        "autosave_time": _clock_time(_LAST_AUTOSAVE_TIME),
        "regular_save_time": _clock_time(_LAST_REGULAR_SAVE_TIME),
        "autosave_path": existing_file(autosave_path),
        "regular_save_path": existing_file(regular_path) if regular_path else "",
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
    global _CHANGES_SINCE_AUTOSAVE
    data = getattr(bpy, "data", None)
    if not hasattr(data, "filepath"):
        return 0.1
    _CHANGES_SINCE_AUTOSAVE = bool(getattr(data, "is_dirty", False))
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
    global _CHANGES_SINCE_AUTOSAVE, _LAST_AUTOSAVE_TIME, _LAST_EVENT, _LAST_STATUS
    preferences = _preferences()
    if preferences is None or preferences.autosave_mode != "CUSTOM":
        return False, "Custom autosave is disabled"
    if _SAVING_COPY:
        return False, "Autosave is already running"
    if not force and not bpy.data.is_dirty:
        return False, "No new changes"
    if not force and not _CHANGES_SINCE_AUTOSAVE:
        return False, "No changes since the last autosave"
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
    _CHANGES_SINCE_AUTOSAVE = False
    _LAST_EVENT = "CUSTOM"
    _LAST_STATUS = f"Saved {paths[0]}"
    _invalidate_recent_cache()
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
        _invalidate_recent_cache()


def _path_is_within(path, directory):
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except (OSError, ValueError):
        return False


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
    global _CHANGES_SINCE_AUTOSAVE, _LAST_REGULAR_SAVE_TIME, _LAST_EVENT, _LAST_STATUS
    if _SAVING_COPY:
        return
    if bpy.data.filepath:
        _CHANGES_SINCE_AUTOSAVE = False
        _LAST_REGULAR_SAVE_TIME = time.time()
        _LAST_EVENT = "REGULAR"
        _LAST_STATUS = f"Saved {bpy.data.filepath}"
        _cleanup_session_temp()
        _tag_redraw()


@persistent
def _load_post(_unused):
    global _CHANGES_SINCE_AUTOSAVE
    _CHANGES_SINCE_AUTOSAVE = False
    # Keep a recovered temp autosave alive until the user saves it elsewhere.
    filepath = getattr(bpy.data, "filepath", "")
    if not filepath or not _path_is_within(filepath, _session_temp_dir()):
        _cleanup_session_temp()
    _read_status_from_disk()
    _load_recovery_state()


@persistent
def _depsgraph_update_post(_scene, _depsgraph):
    """Remember real scene/data activity after the most recent autosave copy."""
    global _CHANGES_SINCE_AUTOSAVE
    if not _SAVING_COPY:
        _CHANGES_SINCE_AUTOSAVE = True


def configure(context=None):
    """Apply the selected mode and restart the interval from this moment."""
    preferences = _preferences()
    if preferences is None:
        return
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


class AIRETOPO_OT_clear_temp_unsaved_files(bpy.types.Operator):
    bl_idname = "wm.airetopo_clear_temp_unsaved_files"
    bl_label = "Clear Temp Unsaved Files"
    bl_description = "Delete custom autosaves for unsaved files from the add-on temporary folder"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, _context):
        root = _temp_root()
        removed = 0
        if root.exists():
            try:
                removed = sum(1 for path in root.rglob("*") if path.is_file())
                shutil.rmtree(root)
            except OSError as error:
                self.report({"ERROR"}, f"Could not clear temporary autosaves: {error}")
                return {"CANCELLED"}

        _invalidate_recent_cache()
        recent_autosaves(refresh=True)
        _tag_redraw()
        self.report({"INFO"}, f"Removed {removed} temporary autosave file(s)")
        return {"FINISHED"}


class AIRETOPO_OT_open_recent_autosave(bpy.types.Operator):
    bl_idname = "wm.airetopo_open_recent_autosave"
    bl_label = "Open Recent Autosave"
    bl_description = "Open this custom autosave as the current Blender file"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})

    @classmethod
    def description(cls, _context, properties):
        return f"Open autosave: {properties.filepath}"

    def invoke(self, context, _event):
        if getattr(bpy.data, "is_dirty", False):
            return context.window_manager.invoke_confirm(self, _event)
        return self.execute(context)

    def execute(self, _context):
        global _LAST_EVENT, _LAST_STATUS, _LAST_REGULAR_SAVE_TIME
        filepath = Path(self.filepath)
        if not filepath.is_file():
            self.report({"ERROR"}, f"Autosave not found: {filepath}")
            _invalidate_recent_cache()
            return {"CANCELLED"}
        original = _original_path_for_autosave(filepath)
        restored = _restored_path_for_autosave(filepath)
        try:
            result = bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            if "FINISHED" not in result:
                return result
            restored.parent.mkdir(parents=True, exist_ok=True)
            _set_recovery_state(filepath, original, restored)
            result = bpy.ops.wm.save_as_mainfile(
                filepath=str(restored),
                check_existing=False,
            )
            if "FINISHED" not in result:
                raise RuntimeError("Blender cancelled creation of the restored copy")
        except RuntimeError as error:
            self.report({"ERROR"}, f"Could not restore autosave: {error}")
            return {"CANCELLED"}

        _LAST_REGULAR_SAVE_TIME = time.time()
        _LAST_EVENT = "RECOVERY"
        _LAST_STATUS = f"Recovered as {restored}"
        _tag_redraw()
        return {"FINISHED"}


class AIRETOPO_OT_open_saved_file(bpy.types.Operator):
    bl_idname = "wm.airetopo_open_saved_file"
    bl_label = "Open Saved File"
    bl_description = "Open the last saved project file"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})

    @classmethod
    def description(cls, _context, properties):
        return f"Open saved file: {properties.filepath}"

    def invoke(self, context, event):
        if getattr(bpy.data, "is_dirty", False):
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, _context):
        filepath = Path(self.filepath)
        if not filepath.is_file():
            self.report({"ERROR"}, f"Saved file not found: {filepath}")
            return {"CANCELLED"}
        try:
            return bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
        except RuntimeError as error:
            self.report({"ERROR"}, f"Could not open saved file: {error}")
            return {"CANCELLED"}


class AIRETOPO_OT_show_file_in_browser(bpy.types.Operator):
    bl_idname = "wm.airetopo_show_file_in_browser"
    bl_label = "Show File in Browser"
    bl_description = "Show this file in the system file browser"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})

    @classmethod
    def description(cls, _context, properties):
        return f"Show in file browser: {properties.filepath}"

    def execute(self, _context):
        filepath = Path(bpy.path.abspath(self.filepath)).resolve()
        if not filepath.is_file():
            self.report({"ERROR"}, f"File not found: {filepath}")
            return {"CANCELLED"}
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer.exe", "/select,", str(filepath)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(filepath)])
            else:
                subprocess.Popen(["xdg-open", str(filepath.parent)])
        except OSError as error:
            self.report({"ERROR"}, f"Could not open file browser: {error}")
            return {"CANCELLED"}
        return {"FINISHED"}


class AIRETOPO_OT_save_recovery_to_original(bpy.types.Operator):
    bl_idname = "wm.airetopo_save_recovery_to_original"
    bl_label = "Save Recovery to Original"
    bl_description = "Overwrite the original blend file and delete the restored copy"

    @classmethod
    def poll(cls, _context):
        state = recovery_snapshot()
        return state["active"] and bool(state["original"])

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, _context):
        global _LAST_EVENT, _LAST_STATUS, _LAST_REGULAR_SAVE_TIME
        state = recovery_snapshot()
        if not state["active"] or not state["original"]:
            self.report({"ERROR"}, "There is no original project for this recovery")
            return {"CANCELLED"}

        original = Path(state["original"])
        restored = Path(state["restored"])
        _clear_recovery_state()
        try:
            result = bpy.ops.wm.save_as_mainfile(
                filepath=str(original),
                check_existing=False,
            )
            if "FINISHED" not in result:
                raise RuntimeError("Blender cancelled saving to the original")
        except RuntimeError as error:
            _set_recovery_state(state["autosave"], original, restored)
            self.report({"ERROR"}, f"Could not save to original: {error}")
            return {"CANCELLED"}

        try:
            if restored.is_file() and restored.resolve() != original.resolve():
                restored.unlink()
        except OSError as error:
            self.report({"WARNING"}, f"Original saved, but restored copy remains: {error}")
            return {"FINISHED"}

        _LAST_REGULAR_SAVE_TIME = time.time()
        _LAST_EVENT = "REGULAR"
        _LAST_STATUS = f"Saved recovery to {original}"
        _invalidate_recent_cache()
        _tag_redraw()
        self.report({"INFO"}, f"Saved to original: {original}")
        return {"FINISHED"}


CLASSES = (
    AIRETOPO_OT_custom_autosave_now,
    AIRETOPO_OT_clear_temp_unsaved_files,
    AIRETOPO_OT_open_recent_autosave,
    AIRETOPO_OT_open_saved_file,
    AIRETOPO_OT_show_file_in_browser,
    AIRETOPO_OT_save_recovery_to_original,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    for handler, callback in (
        (bpy.app.handlers.save_post, _save_post),
        (bpy.app.handlers.load_post, _load_post),
        (bpy.app.handlers.depsgraph_update_post, _depsgraph_update_post),
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
        (bpy.app.handlers.depsgraph_update_post, _depsgraph_update_post),
    ):
        if callback in handler:
            handler.remove(callback)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
