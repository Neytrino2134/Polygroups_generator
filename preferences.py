import os
import subprocess
import time

import bpy

from .localization import LANGUAGE_ITEMS
from .localization import t


def _update_interface_language(self, context):
    try:
        from . import ui

        ui.update_panel_labels(context)
    except Exception:
        pass


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

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "interface_language", text=t(context, "language"))
        layout.separator()
        layout.prop(self, "use_env_openai_api_key", text=t(context, "use_env_openai_api_key"))
        layout.prop(self, "openai_api_key", text=t(context, "openai_api_key"))
        layout.separator()
        layout.prop(self, "use_env_gemini_api_key", text=t(context, "use_env_gemini_api_key"))
        layout.prop(self, "gemini_api_key", text=t(context, "gemini_api_key"))
        layout.separator()
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
            state, message = _repo_state(preferences)
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
            if not _working_tree_clean():
                preferences.update_status = "Local changes detected. Commit or stash them first."
                self.report({"ERROR"}, preferences.update_status)
                return {"CANCELLED"}

            state, message = _repo_state(preferences)
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

            _run_git(["merge", "--ff-only", preferences.update_upstream])
            state, message = _repo_state(preferences)
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
