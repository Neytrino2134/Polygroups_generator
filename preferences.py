import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from urllib.error import URLError
from urllib.request import urlopen
import shutil

import bpy

from .hotkeys import CUTTER_TOOL_ITEMS
from .hotkeys import PIE_COMMAND_ITEMS
from . import pie_presets
from .localization import LANGUAGE_ITEMS
from .localization import t


ADDON_AUTHOR = "Meowmaster"
ADDON_CONTACT_EMAIL = "meowmasterart@gmail.com"
ADDON_GITHUB_URL = "https://github.com/Neytrino2134"
ADDON_REPOSITORY_URL = "https://github.com/Neytrino2134/Polygroups_generator"
ADDON_RAW_INIT_URL = (
    "https://raw.githubusercontent.com/Neytrino2134/Polygroups_generator/master/__init__.py"
)
ADDON_ZIP_URL = (
    "https://github.com/Neytrino2134/Polygroups_generator/archive/refs/heads/master.zip"
)

_AUTO_CHECK_RESULT = None
_AUTO_CHECK_THREAD = None


def _update_interface_language(self, context):
    try:
        from . import ui

        ui.update_panel_labels(context)
    except Exception:
        pass


def _update_hotkeys(self, context):
    try:
        from . import hotkeys

        hotkeys.refresh_keymaps(context)
    except Exception:
        pass


def _update_custom_autosave(self, context):
    try:
        from . import custom_autosave

        custom_autosave.configure(context)
    except Exception:
        pass


NUMBER_KEY_ITEMS = (
    ("ZERO", "0", "0 key"),
    ("ONE", "1", "1 key"),
    ("TWO", "2", "2 key"),
    ("THREE", "3", "3 key"),
    ("FOUR", "4", "4 key"),
    ("FIVE", "5", "5 key"),
    ("SIX", "6", "6 key"),
    ("SEVEN", "7", "7 key"),
    ("EIGHT", "8", "8 key"),
    ("NINE", "9", "9 key"),
)

KEY_ITEMS = tuple(
    [(letter, letter, f"{letter} key") for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    + list(NUMBER_KEY_ITEMS)
    + [(f"NUMPAD_{number}", f"Numpad {number}", f"Numpad {number} key") for number in range(10)]
    + [(f"F{number}", f"F{number}", f"F{number} key") for number in range(1, 13)]
)


def _addon_root():
    return os.path.dirname(os.path.abspath(__file__))


def _run_git(args, timeout=90):
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_addon_root(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError("Git executable was not found") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Git command timed out") from error

    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(output or "Git command failed")

    return output


def _is_git_repository():
    return _run_git(["rev-parse", "--is-inside-work-tree"]) == "true"


def _current_branch():
    branch = _run_git(["branch", "--show-current"])
    if branch:
        return branch
    return "master"


def _upstream_ref(branch):
    try:
        upstream = _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    except RuntimeError:
        upstream = ""
    return upstream or f"origin/{branch}"


def _commit_short(commit):
    return commit[:8] if commit else ""


def _repo_state(preferences):
    _is_git_repository()
    branch = _current_branch()
    upstream = _upstream_ref(branch)
    _run_git(["fetch", "origin"])

    local_commit = _run_git(["rev-parse", "HEAD"])
    remote_commit = _run_git(["rev-parse", upstream])
    merge_base = _run_git(["merge-base", "HEAD", upstream])

    preferences.update_branch = branch
    preferences.update_upstream = upstream
    preferences.update_current_commit = _commit_short(local_commit)
    preferences.update_remote_commit = _commit_short(remote_commit)
    preferences.update_last_checked = time.strftime("%Y-%m-%d %H:%M:%S")

    if local_commit == remote_commit:
        return "UP_TO_DATE", "Add-on is up to date"
    if merge_base == local_commit:
        return "UPDATE_AVAILABLE", "Update available"
    if merge_base == remote_commit:
        return "LOCAL_AHEAD", "Local repository is ahead of the remote"
    return "DIVERGED", "Local and remote branches have diverged"


def _working_tree_clean():
    return _run_git(["status", "--porcelain"]) == ""


def _version_tuple_from_text(text):
    match = re.search(r'"version"\s*:\s*\(([^)]*)\)', text)
    if match is None:
        return None

    parts = []
    for item in match.group(1).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            parts.append(int(item))
        except ValueError:
            return None

    return tuple(parts)


def _current_version_tuple():
    addon_module = sys.modules.get(__package__)
    return tuple(getattr(addon_module, "bl_info", {}).get("version", (0, 0, 0)))


def _version_string(version):
    return ".".join(str(item) for item in version)


def _download_text(url, timeout=30):
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except URLError as error:
        raise RuntimeError(f"Network error: {error}") from error


def _download_file(url, filepath, timeout=120):
    try:
        with urlopen(url, timeout=timeout) as response:
            with open(filepath, "wb") as output_file:
                shutil.copyfileobj(response, output_file)
    except URLError as error:
        raise RuntimeError(f"Network error: {error}") from error


def _zip_root_directory(zip_file):
    roots = {
        item.filename.split("/", 1)[0]
        for item in zip_file.infolist()
        if item.filename and "/" in item.filename
    }
    if not roots:
        raise RuntimeError("Downloaded update archive has no root folder")
    return sorted(roots)[0]


def _copy_update_tree(source_dir, target_dir):
    skip_names = {".git", "__pycache__"}
    for name in os.listdir(source_dir):
        if name in skip_names:
            continue

        source_path = os.path.join(source_dir, name)
        target_path = os.path.join(target_dir, name)
        if os.path.isdir(source_path):
            shutil.copytree(
                source_path,
                target_path,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        else:
            shutil.copy2(source_path, target_path)


def _zip_repo_state(preferences):
    remote_text = _download_text(ADDON_RAW_INIT_URL)
    remote_version = _version_tuple_from_text(remote_text)
    if remote_version is None:
        raise RuntimeError("Could not read remote add-on version")

    current_version = _current_version_tuple()
    preferences.update_branch = "master"
    preferences.update_upstream = "GitHub ZIP"
    preferences.update_current_commit = _version_string(current_version)
    preferences.update_remote_commit = _version_string(remote_version)
    preferences.update_last_checked = time.strftime("%Y-%m-%d %H:%M:%S")

    if remote_version > current_version:
        return "UPDATE_AVAILABLE", "Update available"
    if remote_version == current_version:
        return "UP_TO_DATE", "Add-on is up to date"
    return "LOCAL_AHEAD", "Installed version is newer than GitHub master"


def _update_from_zip():
    with tempfile.TemporaryDirectory(prefix="airetopo_update_") as temp_dir:
        archive_path = os.path.join(temp_dir, "update.zip")
        _download_file(ADDON_ZIP_URL, archive_path)

        extract_dir = os.path.join(temp_dir, "extract")
        with zipfile.ZipFile(archive_path, "r") as zip_file:
            root_name = _zip_root_directory(zip_file)
            zip_file.extractall(extract_dir)

        source_dir = os.path.join(extract_dir, root_name)
        if not os.path.isfile(os.path.join(source_dir, "__init__.py")):
            raise RuntimeError("Downloaded archive does not look like the add-on")

        _copy_update_tree(source_dir, _addon_root())


def _addon_info():
    addon_module = sys.modules.get(__package__)
    bl_info = getattr(addon_module, "bl_info", {})
    version = ".".join(str(item) for item in bl_info.get("version", (0, 0, 0)))
    return bl_info.get("name", "AI Retopo Toolkit"), version


def _copy_update_state(source, target):
    for name in (
        "update_branch",
        "update_upstream",
        "update_current_commit",
        "update_remote_commit",
        "update_last_checked",
    ):
        setattr(target, name, getattr(source, name, ""))


def _check_update_state(preferences):
    try:
        return _repo_state(preferences)
    except RuntimeError:
        return _zip_repo_state(preferences)


def _tag_preferences_redraw():
    window_manager = getattr(bpy.context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()):
        for area in window.screen.areas:
            area.tag_redraw()


def _auto_check_worker():
    global _AUTO_CHECK_RESULT
    state_holder = type("UpdateState", (), {})()
    try:
        state, message = _check_update_state(state_holder)
        _AUTO_CHECK_RESULT = (state, message, state_holder, "")
    except Exception as error:
        _AUTO_CHECK_RESULT = ("ERROR", "", state_holder, str(error))


def _auto_check_timer():
    global _AUTO_CHECK_RESULT, _AUTO_CHECK_THREAD
    context = getattr(bpy, "context", None)
    addons = getattr(getattr(context, "preferences", None), "addons", None)
    addon = addons.get(__package__) if addons is not None else None
    if addon is None:
        return None
    preferences = addon.preferences
    if not preferences.auto_check_updates:
        return None

    if _AUTO_CHECK_THREAD is None:
        preferences.update_status = "Checking for updates..."
        _AUTO_CHECK_THREAD = threading.Thread(
            target=_auto_check_worker,
            name="AI Retopo update check",
            daemon=True,
        )
        _AUTO_CHECK_THREAD.start()
        return 0.25
    if _AUTO_CHECK_THREAD.is_alive():
        return 0.25

    result = _AUTO_CHECK_RESULT
    _AUTO_CHECK_RESULT = None
    _AUTO_CHECK_THREAD = None
    if result is None:
        return None
    state, message, state_holder, error = result
    if error:
        preferences.update_available = False
        preferences.update_status = error
    else:
        _copy_update_state(state_holder, preferences)
        preferences.update_available = state == "UPDATE_AVAILABLE"
        preferences.update_status = message
    _tag_preferences_redraw()
    return None


def autosave_configuration_state(context, preferences):
    custom_enabled = preferences.autosave_mode == "CUSTOM"
    native_enabled = bool(context.preferences.filepaths.use_auto_save_temporary_files)
    if custom_enabled and native_enabled:
        return "BOTH"
    if not custom_enabled and not native_enabled:
        return "NONE"
    return "OK"


def draw_global_notices(layout, context, preferences):
    if preferences.update_available:
        box = layout.box()
        box.alert = True
        box.label(text=t(context, "update_available_notice"), icon="IMPORT")
        box.operator("wm.airetopo_update_addon", text=t(context, "update_addon"), icon="IMPORT")
    if preferences.update_restart_required:
        box = layout.box()
        box.alert = True
        box.label(text=t(context, "update_restart_notice"), icon="FILE_REFRESH")
        box.operator(
            "wm.airetopo_dev_restart_current",
            text=t(context, "save_and_restart_blender"),
            icon="FILE_TICK",
        )

    autosave_state = autosave_configuration_state(context, preferences)
    if autosave_state == "BOTH":
        box = layout.box()
        box.alert = True
        box.label(text=t(context, "autosave_both_enabled"), icon="ERROR")
        row = box.row(align=True)
        native = row.operator(
            "wm.airetopo_set_autosave_configuration",
            text=t(context, "disable_native_autosave"),
        )
        native.action = "DISABLE_NATIVE"
        custom = row.operator(
            "wm.airetopo_set_autosave_configuration",
            text=t(context, "disable_custom_autosave"),
        )
        custom.action = "DISABLE_CUSTOM"
    elif autosave_state == "NONE":
        box = layout.box()
        box.alert = True
        box.label(text=t(context, "autosave_both_disabled"), icon="ERROR")
        row = box.row(align=True)
        native = row.operator(
            "wm.airetopo_set_autosave_configuration",
            text=t(context, "enable_native_autosave"),
        )
        native.action = "ENABLE_NATIVE"
        custom = row.operator(
            "wm.airetopo_set_autosave_configuration",
            text=t(context, "enable_custom_autosave"),
        )
        custom.action = "ENABLE_CUSTOM"


class AIRETOPO_Preferences(bpy.types.AddonPreferences):
    panel_python_executable: bpy.props.StringProperty(
        name="Development Python Fallback", subtype='FILE_PATH', default='',
        description="Optional Python with Tkinter, used only when the bundled window client is missing",
    )
    bl_idname = __package__

    show_preferences_info: bpy.props.BoolProperty(default=True)
    show_preferences_updates: bpy.props.BoolProperty(default=False)
    show_preferences_icons: bpy.props.BoolProperty(default=False)
    show_preferences_language: bpy.props.BoolProperty(default=True)
    show_preferences_operations: bpy.props.BoolProperty(default=False)
    show_preferences_autosave: bpy.props.BoolProperty(default=False)
    show_preferences_remesh: bpy.props.BoolProperty(default=False)
    show_preferences_api: bpy.props.BoolProperty(default=False)
    show_preferences_hotkeys: bpy.props.BoolProperty(default=True)
    show_preferences_pie_menu: bpy.props.BoolProperty(default=False)
    show_preferences_windows: bpy.props.BoolProperty(default=False)
    show_preferences_dev: bpy.props.BoolProperty(default=False)
    show_panel_session_status: bpy.props.BoolProperty(
        name="Session and Autosave",
        description="Show autosave status and Blender restart controls in the N-panel",
        default=True,
    )
    enable_dev_mode: bpy.props.BoolProperty(
        name="Enable Dev Mode",
        description="Show developer restart controls in the AI Retopo N-panel",
        default=True,
    )

    enable_section_number_hotkeys: bpy.props.BoolProperty(
        name="Section Number Hotkeys", default=True, update=_update_hotkeys,
    )
    enable_collection_navigation_hotkeys: bpy.props.BoolProperty(
        name="Collection Navigation Hotkeys",
        description="Use Ctrl+Numpad Plus/Minus in Outliner and the AI Retopo sidebar",
        default=True,
        update=_update_hotkeys,
    )
    section_digit_interval: bpy.props.FloatProperty(
        name="Digit Interval", default=0.15, min=0.15, max=1.0, precision=2,
        description="Seconds to wait for a second digit after 1", update=_update_hotkeys,
    )
    section_hotkey_scope: bpy.props.EnumProperty(
        name="Scope", default="SIDEBAR", update=_update_hotkeys,
        items=(("SIDEBAR", "AI Retopo Sidebar", "Only over the AI Retopo sidebar"),
               ("VIEWPORT", "Entire 3D View", "Override number shortcuts in the 3D View, including Edit Mode")),
    )

    remesh_low_count: bpy.props.IntProperty(
        name="LOW", description="Default target quad count for LOW remesh",
        default=1000, min=1,
    )
    remesh_mid_count: bpy.props.IntProperty(
        name="MID", description="Default target quad count for MID remesh and new scenes",
        default=3000, min=1,
    )
    remesh_high_count: bpy.props.IntProperty(
        name="HIGH", description="Default target quad count for HIGH remesh",
        default=50000, min=1,
    )

    interface_language: bpy.props.EnumProperty(
        name="Interface Language",
        description="Language used by AI Retopo Toolkit UI labels",
        items=LANGUAGE_ITEMS,
        default="EN",
        update=_update_interface_language,
    )
    show_panel_settings: bpy.props.BoolProperty(
        name="Show Panel Settings",
        description="Show language and add-on description in the main panel",
        default=False,
    )
    play_sound_after_operations: bpy.props.BoolProperty(
        name="Play Sound After Operations",
        description="Play the bundled notification sound after long operations finish",
        default=True,
    )
    use_env_openai_api_key: bpy.props.BoolProperty(
        name="Use OPENAI_API_KEY",
        description="Prefer the OPENAI_API_KEY environment variable when it is available",
        default=True,
    )
    openai_api_key: bpy.props.StringProperty(
        name="OpenAI API Key",
        description="Fallback OpenAI API key used when OPENAI_API_KEY is disabled or empty",
        default="",
        subtype="PASSWORD",
    )
    use_env_gemini_api_key: bpy.props.BoolProperty(
        name="Use GEMINI_API_KEY",
        description="Prefer the GEMINI_API_KEY environment variable when it is available",
        default=True,
    )
    gemini_api_key: bpy.props.StringProperty(
        name="Google Gemini API Key",
        description="Fallback Google Gemini API key used when GEMINI_API_KEY is disabled or empty",
        default="",
        subtype="PASSWORD",
    )
    update_status: bpy.props.StringProperty(
        name="Update Status",
        default="Not checked",
    )
    update_branch: bpy.props.StringProperty(
        name="Branch",
        default="",
    )
    update_upstream: bpy.props.StringProperty(
        name="Upstream",
        default="",
    )
    update_current_commit: bpy.props.StringProperty(
        name="Current",
        default="",
    )
    update_remote_commit: bpy.props.StringProperty(
        name="Remote",
        default="",
    )
    update_last_checked: bpy.props.StringProperty(
        name="Last Checked",
        default="",
    )
    update_available: bpy.props.BoolProperty(
        name="Update Available",
        default=False,
    )
    auto_check_updates: bpy.props.BoolProperty(
        name="Check for Updates on Startup",
        description="Check for a newer add-on version after Blender starts",
        default=True,
    )
    update_restart_required: bpy.props.BoolProperty(
        name="Restart Required",
        default=False,
        options={"HIDDEN"},
    )
    cutter_tweak_tool: bpy.props.EnumProperty(
        name="Cutter Tweak Tool",
        description="Workspace tool selected by the Cutter Tweak hotkey",
        items=CUTTER_TOOL_ITEMS,
        default="polygroups_generator.draw_cutter_plane_tool",
    )
    enable_cutter_tweak_hotkey: bpy.props.BoolProperty(
        name="Enable Cutter Tweak Hotkey",
        description="Enable a shortcut for selecting the configured Cutter Tweak tool",
        default=True,
        update=_update_hotkeys,
    )
    cutter_tweak_key: bpy.props.EnumProperty(
        name="Key",
        description="Key used to select Cutter Tweak",
        items=KEY_ITEMS,
        default="D",
        update=_update_hotkeys,
    )
    cutter_tweak_ctrl: bpy.props.BoolProperty(
        name="Ctrl",
        default=True,
        update=_update_hotkeys,
    )
    cutter_tweak_shift: bpy.props.BoolProperty(
        name="Shift",
        default=False,
        update=_update_hotkeys,
    )
    cutter_tweak_alt: bpy.props.BoolProperty(
        name="Alt",
        default=False,
        update=_update_hotkeys,
    )
    enable_pie_menu_hotkey: bpy.props.BoolProperty(
        name="Enable Pie Menu Hotkey",
        description="Enable a shortcut for the AI Retopo pie menu",
        default=True,
        update=_update_hotkeys,
    )
    pie_menu_key: bpy.props.EnumProperty(
        name="Key",
        description="Key used to open the AI Retopo pie menu",
        items=KEY_ITEMS,
        default="C",
        update=_update_hotkeys,
    )
    pie_menu_ctrl: bpy.props.BoolProperty(
        name="Ctrl",
        default=False,
        update=_update_hotkeys,
    )
    pie_menu_shift: bpy.props.BoolProperty(
        name="Shift",
        default=True,
        update=_update_hotkeys,
    )
    pie_menu_alt: bpy.props.BoolProperty(
        name="Alt",
        default=False,
        update=_update_hotkeys,
    )
    enable_cutter_tweak_pie_hotkey: bpy.props.BoolProperty(
        name="Enable Cutter Tweak Pie Hotkey", default=True, update=_update_hotkeys,
    )
    cutter_tweak_pie_key: bpy.props.EnumProperty(
        name="Key", items=KEY_ITEMS, default="D", update=_update_hotkeys,
    )
    cutter_tweak_pie_ctrl: bpy.props.BoolProperty(
        name="Ctrl", default=False, update=_update_hotkeys,
    )
    cutter_tweak_pie_shift: bpy.props.BoolProperty(
        name="Shift", default=False, update=_update_hotkeys,
    )
    cutter_tweak_pie_alt: bpy.props.BoolProperty(
        name="Alt", default=False, update=_update_hotkeys,
    )
    pie_presets: bpy.props.CollectionProperty(type=pie_presets.AIRETOPO_PG_pie_preset)
    pie_current_slots: bpy.props.StringProperty(options={"HIDDEN"})
    pie_next_preset_number: bpy.props.IntProperty(default=3, min=3, options={"HIDDEN"})
    active_pie_preset: bpy.props.EnumProperty(
        name="Active Preset",
        description="Choose and load a pie menu layout",
        items=pie_presets.preset_items,
        default=0,
        update=pie_presets.preset_updated,
    )
    use_edit_mode_preset: bpy.props.BoolProperty(
        name="Use Edit Mode Preset in Edit Mode",
        description="Use a separate Pie Menu layout while the active object is in Edit Mode",
        default=True,
    )
    autosave_mode: bpy.props.EnumProperty(
        name="Autosave System",
        description="Choose Blender's temporary autosave or versioned copies beside the blend file",
        items=(
            ("NATIVE", "Native", "Use Blender's standard temporary-file autosave"),
            ("CUSTOM", "Custom", "Store rotating autosave copies beside the saved blend file"),
        ),
        default="NATIVE",
        update=_update_custom_autosave,
    )
    autosave_interval_minutes: bpy.props.FloatProperty(
        name="Interval (Minutes)",
        description="Minutes between custom autosave checks",
        default=2.0,
        min=1.0,
        max=120.0,
        step=60,
        precision=1,
        update=_update_custom_autosave,
    )
    autosave_versions: bpy.props.IntProperty(
        name="Autosave Versions",
        description="Number of rotating custom autosave copies to keep",
        default=3,
        min=1,
        max=20,
    )
    edit_pie_current_slots: bpy.props.StringProperty(options={"HIDDEN"})
    active_edit_pie_preset: bpy.props.EnumProperty(
        name="Active Edit Mode Preset",
        description="Choose and load the Pie Menu layout used in Edit Mode",
        items=pie_presets.preset_items,
        default=1000000,
        update=pie_presets.edit_preset_updated,
    )

    pie_slot_1: bpy.props.EnumProperty(
        name="Slot 1",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="IMPORT_FILES",
    )
    pie_slot_2: bpy.props.EnumProperty(
        name="Slot 2",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="APPLY_CUTTER_SEAMS",
    )
    pie_slot_3: bpy.props.EnumProperty(
        name="Slot 3",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="GENERATE_POLYGROUPS",
    )
    pie_slot_4: bpy.props.EnumProperty(
        name="Slot 4",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="CUTTER_TWEAK",
    )
    pie_slot_5: bpy.props.EnumProperty(
        name="Slot 5",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="UV_PACK",
    )
    pie_slot_6: bpy.props.EnumProperty(
        name="Slot 6",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="REMESH",
    )
    pie_slot_7: bpy.props.EnumProperty(
        name="Slot 7",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="CHECK_MATERIALS",
    )
    pie_slot_8: bpy.props.EnumProperty(
        name="Slot 8",
        items=PIE_COMMAND_ITEMS,
        update=pie_presets.slot_updated,
        default="PREPARE_BAKE",
    )
    edit_pie_slot_1: bpy.props.EnumProperty(
        name="Edit Slot 1", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="SELECT_LESS",
    )
    edit_pie_slot_2: bpy.props.EnumProperty(
        name="Edit Slot 2", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="SELECT_MORE",
    )
    edit_pie_slot_3: bpy.props.EnumProperty(
        name="Edit Slot 3", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="DELETE_FILL",
    )
    edit_pie_slot_4: bpy.props.EnumProperty(
        name="Edit Slot 4", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="SELECT_LINKED_SEAM",
    )
    edit_pie_slot_5: bpy.props.EnumProperty(
        name="Edit Slot 5", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="MARK_SEAM",
    )
    edit_pie_slot_6: bpy.props.EnumProperty(
        name="Edit Slot 6", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="CLEAR_SELECTED_SEAMS",
    )
    edit_pie_slot_7: bpy.props.EnumProperty(
        name="Edit Slot 7", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="EDGE_SEAM_TOOL",
    )
    edit_pie_slot_8: bpy.props.EnumProperty(
        name="Edit Slot 8", items=PIE_COMMAND_ITEMS, update=pie_presets.edit_slot_updated,
        default="KNIFE_SEAM_TOOL",
    )

    def draw(self, context):
        layout = self.layout
        draw_global_notices(layout, context, self)
        sections = (
            ("show_preferences_info", t(context, "preferences_info"), self.draw_info),
            ("show_preferences_updates", t(context, "updates"), self.draw_updates),
            ("show_preferences_icons", "Custom Icons", self.draw_icons),
            ("show_preferences_language", t(context, "preferences_language"), self.draw_language),
            ("show_preferences_operations", t(context, "preferences_operations"), self.draw_operations),
            ("show_preferences_autosave", t(context, "preferences_autosave"), self.draw_autosave),
            ("show_preferences_remesh", t(context, "preferences_remesh"), self.draw_remesh),
            ("show_preferences_api", t(context, "preferences_api"), self.draw_api),
            ("show_preferences_hotkeys", t(context, "hotkeys"), self.draw_hotkeys),
            ("show_preferences_pie_menu", t(context, "preferences_pie_menu"), self.draw_pie_menu),
            ("show_preferences_windows", "Floating Windows", self.draw_windows),
            ("show_preferences_dev", "Dev", self.draw_dev),
        )
        for property_name, label, draw_content in sections:
            box = layout.box()
            header = box.row(align=True)
            expanded = getattr(self, property_name)
            header.prop(self, property_name, text=label, icon="TRIA_DOWN" if expanded else "TRIA_RIGHT", emboss=False)
            if expanded:
                draw_content(context, box.column())

    def draw_icons(self, context, layout):
        layout.operator("wm.airetopo_update_icons", text="Update icons", icon="FILE_REFRESH")

    def draw_windows(self, context, layout):
        layout.label(text="The standalone client is included with the add-on.", icon="CHECKMARK")
        layout.label(text="Drag the title to move; use the bottom-right grip to resize.")
        layout.operator('wm.airetopo_group_window_control')

    def draw_dev(self, context, layout):
        layout.prop(self, "enable_dev_mode", text=t(context, "enable_dev_mode"))
        layout.label(text=t(context, "dev_restart_hint"))
        layout.operator("wm.airetopo_dev_cleanup", text=t(context, "dev_cleanup"), icon="TRASH")
        layout.operator(
            "wm.airetopo_clear_temp_unsaved_files",
            text=t(context, "clear_temp_unsaved_files"),
            icon="TRASH",
        )

    def draw_info(self, context, layout):
        addon_name, version = _addon_info()
        column = layout.column(align=True)
        column.label(text=t(context, "addon_name", value=addon_name))
        column.label(text=t(context, "addon_version", value=version))
        column.label(text=t(context, "addon_author", value=ADDON_AUTHOR))
        column.label(text=t(context, "addon_contact", value=ADDON_CONTACT_EMAIL))
        github_row = column.row(align=True)
        github_row.label(text=t(context, "addon_github", value=ADDON_GITHUB_URL))
        github_operator = github_row.operator(
            "wm.url_open",
            text=t(context, "open_link"),
            icon="WORLD",
        )
        github_operator.url = ADDON_GITHUB_URL

    def draw_language(self, context, layout):
        column = layout.column(align=True)
        column.prop(self, "interface_language", text=t(context, "language"))
        column.prop(self, "show_panel_settings", text=t(context, "show_panel_settings"))

    def draw_operations(self, context, layout):
        column = layout.column(align=True)
        column.prop(
            self,
            "play_sound_after_operations",
            text=t(context, "play_sound_after_operations"),
        )

    def draw_autosave(self, context, layout):
        column = layout.column(align=True)
        column.prop(self, "autosave_mode", text=t(context, "autosave_system"))
        if self.autosave_mode == "CUSTOM":
            column.prop(self, "autosave_interval_minutes", text=t(context, "autosave_interval"))
            column.prop(self, "autosave_versions", text=t(context, "autosave_versions"))
            column.separator()
            column.label(text=t(context, "autosave_custom_description_1"), icon="INFO")
            column.label(text=t(context, "autosave_custom_description_2"))
            column.label(text=t(context, "autosave_custom_description_3"))
            column.operator(
                "wm.airetopo_custom_autosave_now",
                text=t(context, "autosave_now"),
                icon="FILE_TICK",
            )
        else:
            column.label(text=t(context, "autosave_native_description"), icon="INFO")

    def draw_remesh(self, context, layout):
        column = layout.column(align=True)
        column.prop(self, "remesh_low_count")
        column.prop(self, "remesh_mid_count")
        column.prop(self, "remesh_high_count")

    def draw_api(self, context, layout):
        column = layout.column(align=True)
        column.prop(self, "use_env_openai_api_key", text=t(context, "use_env_openai_api_key"))
        column.prop(self, "openai_api_key", text=t(context, "openai_api_key"))
        column.separator()
        column.prop(self, "use_env_gemini_api_key", text=t(context, "use_env_gemini_api_key"))
        column.prop(self, "gemini_api_key", text=t(context, "gemini_api_key"))

    def draw_hotkeys(self, context, layout):
        section_box = layout.box()
        section_box.prop(self, "enable_section_number_hotkeys", text=t(context, "section_number_hotkeys"))
        section_options = section_box.column(align=True)
        section_options.enabled = self.enable_section_number_hotkeys
        section_options.prop(self, "section_hotkey_scope", text=t(context, "section_hotkey_scope"))
        section_options.prop(self, "section_digit_interval", text=t(context, "section_digit_interval"))
        section_options.label(text=t(context, "section_number_hint"))
        navigation_box = layout.box()
        navigation_box.prop(
            self,
            "enable_collection_navigation_hotkeys",
            text=t(context, "collection_navigation_hotkeys"),
        )
        navigation_box.label(text=t(context, "collection_navigation_hotkeys_hint"))
        column = layout.column(align=True)
        column.prop(self, "cutter_tweak_tool", text=t(context, "cutter_tweak_tool"))
        cutter_box = column.box()
        cutter_box.prop(
            self,
            "enable_cutter_tweak_hotkey",
            text=t(context, "enable_cutter_tweak_hotkey"),
        )
        cutter_row = cutter_box.row(align=True)
        cutter_row.enabled = self.enable_cutter_tweak_hotkey
        cutter_row.prop(self, "cutter_tweak_key", text=t(context, "hotkey_key"))
        cutter_row.prop(self, "cutter_tweak_ctrl", text="Ctrl")
        cutter_row.prop(self, "cutter_tweak_shift", text="Shift")
        cutter_row.prop(self, "cutter_tweak_alt", text="Alt")

        pie_hotkey_box = column.box()
        pie_hotkey_box.prop(
            self,
            "enable_pie_menu_hotkey",
            text=t(context, "enable_pie_menu_hotkey"),
        )
        pie_row = pie_hotkey_box.row(align=True)
        pie_row.enabled = self.enable_pie_menu_hotkey
        pie_row.prop(self, "pie_menu_key", text=t(context, "hotkey_key"))
        pie_row.prop(self, "pie_menu_ctrl", text="Ctrl")
        pie_row.prop(self, "pie_menu_shift", text="Shift")
        pie_row.prop(self, "pie_menu_alt", text="Alt")

        cutter_pie_box = column.box()
        cutter_pie_box.prop(self, "enable_cutter_tweak_pie_hotkey", text=t(context, "enable_cutter_tweak_pie_hotkey"))
        cutter_pie_row = cutter_pie_box.row(align=True)
        cutter_pie_row.enabled = self.enable_cutter_tweak_pie_hotkey
        cutter_pie_row.prop(self, "cutter_tweak_pie_key", text=t(context, "hotkey_key"))
        cutter_pie_row.prop(self, "cutter_tweak_pie_ctrl", text="Ctrl")
        cutter_pie_row.prop(self, "cutter_tweak_pie_shift", text="Shift")
        cutter_pie_row.prop(self, "cutter_tweak_pie_alt", text="Alt")

    def draw_pie_menu(self, context, layout):
        pie_presets.draw_pie_settings(self, context, layout)

    def draw_updates(self, context, layout):
        layout.prop(self, "auto_check_updates", text=t(context, "auto_check_updates"))
        update_row = layout.row(align=True)
        update_row.operator(
            "wm.airetopo_check_updates",
            text=t(context, "check_updates"),
            icon="VIEWZOOM",
        )
        update_button = update_row.operator(
            "wm.airetopo_update_addon",
            text=t(context, "update_addon"),
            icon="IMPORT",
        )
        del update_button
        layout.label(text=t(context, "update_status", value=self.update_status))
        if self.update_branch or self.update_current_commit or self.update_remote_commit:
            layout.label(
                text=t(
                    context,
                    "update_commits",
                    branch=self.update_branch or "-",
                    current=self.update_current_commit or "-",
                    remote=self.update_remote_commit or "-",
                ),
            )
        if self.update_last_checked:
            layout.label(text=t(context, "update_last_checked", value=self.update_last_checked))
        if self.update_restart_required:
            layout.operator(
                "wm.airetopo_dev_restart_current",
                text=t(context, "save_and_restart_blender"),
                icon="FILE_TICK",
            )


class AIRETOPO_OT_toggle_panel_settings(bpy.types.Operator):
    bl_idname = "wm.airetopo_toggle_panel_settings"
    bl_label = "Toggle AI Retopo Panel Settings"
    bl_description = "Show or hide language and description in the AI Retopo Toolkit panel"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        addon = context.preferences.addons.get(__package__)
        if addon is None:
            return {"CANCELLED"}

        preferences = addon.preferences
        preferences.show_panel_settings = not preferences.show_panel_settings
        return {"FINISHED"}


class AIRETOPO_OT_update_icons(bpy.types.Operator):
    bl_idname = "wm.airetopo_update_icons"
    bl_label = "Update icons"
    bl_description = "Rebuild icons from the PNG files in the add-on icons folder and refresh the interface"

    def execute(self, context):
        from .custom_icons import update_icons
        try:
            count = update_icons(context)
        except Exception as error:
            self.report({"ERROR"}, f"Could not update icons: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Updated {count} icons")
        return {"FINISHED"}


class AIRETOPO_OT_check_updates(bpy.types.Operator):
    bl_idname = "wm.airetopo_check_updates"
    bl_label = "Check Updates"
    bl_description = "Check GitHub for AI Retopo Toolkit updates"
    bl_options = {"REGISTER"}

    def execute(self, context):
        preferences = context.preferences.addons[__package__].preferences
        try:
            state, message = _check_update_state(preferences)
        except RuntimeError as error:
            preferences.update_available = False
            preferences.update_status = str(error)
            self.report({"ERROR"}, preferences.update_status)
            return {"CANCELLED"}

        preferences.update_available = state == "UPDATE_AVAILABLE"
        preferences.update_status = message
        report_type = {"INFO"} if state in {"UP_TO_DATE", "UPDATE_AVAILABLE"} else {"WARNING"}
        self.report(report_type, message)
        return {"FINISHED"}


class AIRETOPO_OT_set_autosave_configuration(bpy.types.Operator):
    bl_idname = "wm.airetopo_set_autosave_configuration"
    bl_label = "Set Autosave Configuration"
    bl_description = "Resolve the conflicting or disabled autosave configuration"

    action: bpy.props.EnumProperty(
        items=(
            ("DISABLE_NATIVE", "Disable Native", "Keep custom autosave only"),
            ("DISABLE_CUSTOM", "Disable Custom", "Keep native autosave only"),
            ("ENABLE_NATIVE", "Enable Native", "Enable native autosave"),
            ("ENABLE_CUSTOM", "Enable Custom", "Enable custom autosave"),
        ),
        options={"SKIP_SAVE"},
    )

    def execute(self, context):
        preferences = context.preferences.addons[__package__].preferences
        filepaths = context.preferences.filepaths
        if self.action == "DISABLE_NATIVE":
            filepaths.use_auto_save_temporary_files = False
        elif self.action in {"DISABLE_CUSTOM", "ENABLE_NATIVE"}:
            preferences.autosave_mode = "NATIVE"
            filepaths.use_auto_save_temporary_files = True
        elif self.action == "ENABLE_CUSTOM":
            filepaths.use_auto_save_temporary_files = False
            preferences.autosave_mode = "CUSTOM"
        from . import custom_autosave
        custom_autosave.configure(context)
        _tag_preferences_redraw()
        return {"FINISHED"}


class AIRETOPO_OT_update_addon(bpy.types.Operator):
    bl_idname = "wm.airetopo_update_addon"
    bl_label = "Update Add-on"
    bl_description = "Fast-forward this add-on from its GitHub remote"
    bl_options = {"REGISTER"}

    def execute(self, context):
        preferences = context.preferences.addons[__package__].preferences

        try:
            use_git_update = True
            try:
                if not _working_tree_clean():
                    preferences.update_status = "Local changes detected. Commit or stash them first."
                    self.report({"ERROR"}, preferences.update_status)
                    return {"CANCELLED"}

                state, message = _repo_state(preferences)
            except RuntimeError:
                use_git_update = False
                state, message = _zip_repo_state(preferences)

            if state == "UP_TO_DATE":
                preferences.update_available = False
                preferences.update_status = message
                self.report({"INFO"}, message)
                return {"FINISHED"}

            if state != "UPDATE_AVAILABLE":
                preferences.update_available = False
                preferences.update_status = message
                self.report({"ERROR"}, message)
                return {"CANCELLED"}

            if use_git_update:
                _run_git(["merge", "--ff-only", preferences.update_upstream])
                state, message = _repo_state(preferences)
            else:
                _update_from_zip()
                state = "UP_TO_DATE"
        except RuntimeError as error:
            preferences.update_available = False
            preferences.update_status = str(error)
            self.report({"ERROR"}, preferences.update_status)
            return {"CANCELLED"}

        preferences.update_available = state == "UPDATE_AVAILABLE"
        preferences.update_restart_required = True
        preferences.update_status = "Updated. Restart Blender or reload the add-on."
        self.report({"INFO"}, preferences.update_status)
        return {"FINISHED"}


CLASSES = (
    *pie_presets.CLASSES,
    AIRETOPO_Preferences,
    AIRETOPO_OT_toggle_panel_settings,
    AIRETOPO_OT_check_updates,
    AIRETOPO_OT_set_autosave_configuration,
    AIRETOPO_OT_update_icons,
    AIRETOPO_OT_update_addon,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    addon = getattr(bpy.context.preferences, "addons", {}).get(__package__)
    if addon is not None:
        addon.preferences.update_restart_required = False
        if addon.preferences.auto_check_updates and not bpy.app.background:
            bpy.app.timers.register(_auto_check_timer, first_interval=2.0)


def unregister():
    if bpy.app.timers.is_registered(_auto_check_timer):
        bpy.app.timers.unregister(_auto_check_timer)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
