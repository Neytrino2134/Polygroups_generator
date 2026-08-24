import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from urllib.error import URLError
from urllib.request import urlopen
import shutil

import bpy

from .hotkeys import CUTTER_TOOL_ITEMS
from .hotkeys import PIE_COMMAND_ITEMS
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


class AIRETOPO_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

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
        default=False,
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
    pie_slot_1: bpy.props.EnumProperty(
        name="Slot 1",
        items=PIE_COMMAND_ITEMS,
        default="IMPORT_FILES",
    )
    pie_slot_2: bpy.props.EnumProperty(
        name="Slot 2",
        items=PIE_COMMAND_ITEMS,
        default="APPLY_CUTTER_SEAMS",
    )
    pie_slot_3: bpy.props.EnumProperty(
        name="Slot 3",
        items=PIE_COMMAND_ITEMS,
        default="GENERATE_POLYGROUPS",
    )
    pie_slot_4: bpy.props.EnumProperty(
        name="Slot 4",
        items=PIE_COMMAND_ITEMS,
        default="CUTTER_TWEAK",
    )
    pie_slot_5: bpy.props.EnumProperty(
        name="Slot 5",
        items=PIE_COMMAND_ITEMS,
        default="UV_PACK",
    )
    pie_slot_6: bpy.props.EnumProperty(
        name="Slot 6",
        items=PIE_COMMAND_ITEMS,
        default="REMESH",
    )
    pie_slot_7: bpy.props.EnumProperty(
        name="Slot 7",
        items=PIE_COMMAND_ITEMS,
        default="CHECK_MATERIALS",
    )
    pie_slot_8: bpy.props.EnumProperty(
        name="Slot 8",
        items=PIE_COMMAND_ITEMS,
        default="PREPARE_BAKE",
    )

    def draw(self, context):
        layout = self.layout
        self.draw_info(context, layout.box())
        self.draw_updates(context, layout.box())
        self.draw_language(context, layout.box())
        self.draw_api(context, layout.box())
        self.draw_hotkeys(context, layout.box())
        self.draw_pie_menu(context, layout.box())

    def draw_info(self, context, layout):
        addon_name, version = _addon_info()
        layout.label(text=t(context, "preferences_info"), icon="INFO")
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
        layout.label(text=t(context, "preferences_language"), icon="WORLD")
        column = layout.column(align=True)
        column.prop(self, "interface_language", text=t(context, "language"))
        column.prop(self, "show_panel_settings", text=t(context, "show_panel_settings"))

    def draw_api(self, context, layout):
        layout.label(text=t(context, "preferences_api"), icon="KEYINGSET")
        column = layout.column(align=True)
        column.prop(self, "use_env_openai_api_key", text=t(context, "use_env_openai_api_key"))
        column.prop(self, "openai_api_key", text=t(context, "openai_api_key"))
        column.separator()
        column.prop(self, "use_env_gemini_api_key", text=t(context, "use_env_gemini_api_key"))
        column.prop(self, "gemini_api_key", text=t(context, "gemini_api_key"))

    def draw_hotkeys(self, context, layout):
        layout.label(text=t(context, "hotkeys"), icon="KEYINGSET")
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

    def draw_pie_menu(self, context, layout):
        layout.label(text=t(context, "preferences_pie_menu"), icon="MENU_PANEL")
        layout.label(text=t(context, "pie_menu_slots"))
        slot_column = layout.column(align=True)
        for index in range(1, 9):
            slot_column.prop(
                self,
                f"pie_slot_{index}",
                text=t(context, "pie_slot", index=index),
            )

    def draw_updates(self, context, layout):
        layout.label(text=t(context, "updates"), icon="FILE_REFRESH")
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


class AIRETOPO_OT_check_updates(bpy.types.Operator):
    bl_idname = "wm.airetopo_check_updates"
    bl_label = "Check Updates"
    bl_description = "Check GitHub for AI Retopo Toolkit updates"
    bl_options = {"REGISTER"}

    def execute(self, context):
        preferences = context.preferences.addons[__package__].preferences
        try:
            try:
                state, message = _repo_state(preferences)
            except RuntimeError:
                state, message = _zip_repo_state(preferences)
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
        except RuntimeError as error:
            preferences.update_available = False
            preferences.update_status = str(error)
            self.report({"ERROR"}, preferences.update_status)
            return {"CANCELLED"}

        preferences.update_available = state == "UPDATE_AVAILABLE"
        preferences.update_status = "Updated. Restart Blender or reload the add-on."
        self.report({"INFO"}, preferences.update_status)
        return {"FINISHED"}


CLASSES = (
    AIRETOPO_Preferences,
    AIRETOPO_OT_toggle_panel_settings,
    AIRETOPO_OT_check_updates,
    AIRETOPO_OT_update_addon,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
