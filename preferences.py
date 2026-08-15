import bpy

from .localization import LANGUAGE_ITEMS
from .localization import t


def _update_interface_language(self, context):
    try:
        from . import ui

        ui.update_panel_labels(context)
    except Exception:
        pass


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

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "interface_language", text=t(context, "language"))
        layout.separator()
        layout.prop(self, "use_env_openai_api_key", text=t(context, "use_env_openai_api_key"))
        layout.prop(self, "openai_api_key", text=t(context, "openai_api_key"))


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


CLASSES = (
    AIRETOPO_Preferences,
    AIRETOPO_OT_toggle_panel_settings,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
