import bpy

from .localization import get_preferences
from .localization import t
from .tools import DRAW_CUTTER_ARC_TOOL_ID
from .tools import DRAW_CUTTER_DRAW_TOOL_ID
from .tools import DRAW_CUTTER_PATH_TOOL_ID
from .tools import DRAW_CUTTER_TOOL_ID
from .tools import CUTTER_TOOL_ORDER


KEYMAP_ITEMS = []

CUTTER_TOOL_ITEMS = (
    (DRAW_CUTTER_TOOL_ID, "Plane", "Start cycling from the cutter plane tool"),
    (DRAW_CUTTER_ARC_TOOL_ID, "Arc", "Start cycling from the cutter arc tool"),
    (DRAW_CUTTER_PATH_TOOL_ID, "Path", "Start cycling from the cutter path tool"),
    (DRAW_CUTTER_DRAW_TOOL_ID, "Draw", "Start cycling from the freehand cutter draw tool"),
)

PIE_COMMAND_ITEMS = (
    ("NONE", "Empty", "Leave this pie slot empty"),
    ("IMPORT_FILES", "Import Files", "Open the multi-file import browser"),
    ("APPLY_CUTTER_SEAMS", "Apply Cutter Seams", "Apply selected cutter seams to the active mesh"),
    ("GENERATE_POLYGROUPS", "Generate PolyGroups", "Generate PolyGroups on the active mesh"),
    ("RENAME_WELD", "Rename + Weld", "Rename selected meshes and apply Weld"),
    ("REMESH", "Remesh It", "Run Quad Remesher through the safety check"),
    ("UV_PACK", "UVPackmaster PACK", "Run UVPackmaster Pack"),
    ("CHECK_MATERIALS", "Check Material/Textures", "Fix material texture connections"),
    ("PREPARE_BAKE", "Prepare And Bake", "Prepare selected-to-active baking and bake"),
    ("SAVE_TEXTURES", "Save Textures", "Save active bake textures"),
    ("CLEAR_BAKE_IMAGES", "Clear Bake Images", "Delete Bake_Temp images"),
    ("CUTTER_TWEAK", "Cutter Tweak Tool", "Select the configured Cutter Tweak tool"),
)

PIE_COMMANDS = {
    "IMPORT_FILES": {
        "label": "import_files",
        "icon": "FILE_FOLDER",
        "operator": "object.polygroups_batch_import",
        "properties": {"use_file_selection": True},
    },
    "APPLY_CUTTER_SEAMS": {
        "label": "apply_cutter_seams",
        "icon": "MOD_BOOLEAN",
        "operator": "object.polygroups_apply_cutter_seams",
    },
    "GENERATE_POLYGROUPS": {
        "label": "generate_polygroups",
        "icon": "GROUP_VERTEX",
        "operator": "object.polygroups_checked_generate_polygroups",
    },
    "RENAME_WELD": {
        "label": "rename_apply_weld",
        "icon": "AUTOMERGE_ON",
        "operator": "object.polygroups_rename_and_apply_weld",
    },
    "REMESH": {
        "label": "remesh_it",
        "icon": "MOD_REMESH",
        "operator": "object.polygroups_checked_quad_remesh",
    },
    "UV_PACK": {
        "label": "uvpackmaster_pack",
        "icon": "UV",
        "operator": "uvpackmaster4.pack",
        "properties": {"mode_id": "__active__", "pack_op_type": "0"},
    },
    "CHECK_MATERIALS": {
        "label": "check_material_textures",
        "icon": "NODE_MATERIAL",
        "operator": "object.polygroups_check_material_textures",
    },
    "PREPARE_BAKE": {
        "label": "prepare_and_bake",
        "icon": "RENDER_RESULT",
        "operator": "object.polygroups_checked_prepare_and_bake",
    },
    "SAVE_TEXTURES": {
        "label": "save_textures",
        "icon": "FILE_FOLDER",
        "operator": "object.polygroups_save_bake_textures",
    },
    "CLEAR_BAKE_IMAGES": {
        "label": "clear_all_bake_images",
        "icon": "TRASH",
        "operator": "object.polygroups_clear_bake_temp_images",
    },
    "CUTTER_TWEAK": {
        "label": "select_cutter_tweak_tool",
        "icon": "TOOL_SETTINGS",
        "operator": "wm.airetopo_select_cutter_tweak",
    },
}


def _operator_exists(operator_id):
    module_name, operator_name = operator_id.split(".", 1)
    module = getattr(bpy.ops, module_name, None)
    return module is not None and hasattr(module, operator_name)


def _event_kwargs(key, ctrl, shift, alt):
    kwargs = {
        "type": key,
        "value": "PRESS",
    }
    if ctrl:
        kwargs["ctrl"] = True
    if shift:
        kwargs["shift"] = True
    if alt:
        kwargs["alt"] = True
    return kwargs


def _set_operator_properties(operator, properties):
    if not properties:
        return

    for name, value in properties.items():
        try:
            setattr(operator, name, value)
        except Exception:
            pass


def _draw_pie_command(layout, context, command_id):
    command = PIE_COMMANDS.get(command_id)
    if command is None:
        layout.separator()
        return

    operator_id = command["operator"]
    label = t(context, command["label"])
    if not _operator_exists(operator_id):
        row = layout.row()
        row.enabled = False
        row.label(text=label, icon="ERROR")
        return

    operator = layout.operator(
        operator_id,
        text=label,
        icon=command.get("icon", "NONE"),
    )
    _set_operator_properties(operator, command.get("properties"))


def refresh_keymaps(context=None):
    unregister_keymaps()
    register_keymaps()


def _preference_value(preferences, name, default):
    return getattr(preferences, name, default) if preferences is not None else default


def _active_workspace_tool_id(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except Exception:
        return ""

    return getattr(tool, "idname", "")


def _next_cutter_tool_id(context, preferences):
    active_tool_id = _active_workspace_tool_id(context)
    if active_tool_id in CUTTER_TOOL_ORDER:
        active_index = CUTTER_TOOL_ORDER.index(active_tool_id)
        return CUTTER_TOOL_ORDER[(active_index + 1) % len(CUTTER_TOOL_ORDER)]

    start_tool_id = _preference_value(
        preferences,
        "cutter_tweak_tool",
        DRAW_CUTTER_TOOL_ID,
    )
    if start_tool_id in CUTTER_TOOL_ORDER:
        return start_tool_id

    return DRAW_CUTTER_TOOL_ID


class AIRETOPO_OT_select_cutter_tweak(bpy.types.Operator):
    bl_idname = "wm.airetopo_select_cutter_tweak"
    bl_label = "Cycle Cutter Tweak Tool"
    bl_description = "Cycle through Cutter Tweak Plane, Arc, and Path workspace tools"
    bl_options = {"REGISTER"}

    def execute(self, context):
        preferences = get_preferences(context)
        tool_id = _next_cutter_tool_id(context, preferences)
        try:
            bpy.ops.wm.tool_set_by_id(name=tool_id)
        except Exception as error:
            self.report({"ERROR"}, f"Could not select Cutter Tweak tool: {error}")
            return {"CANCELLED"}

        self.report({"INFO"}, "Cutter Tweak tool selected")
        return {"FINISHED"}


class VIEW3D_MT_airetopo_pie(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_airetopo_pie"
    bl_label = "AI Retopo Pie"

    def draw(self, context):
        preferences = get_preferences(context)
        pie = self.layout.menu_pie()
        slots = (
            "pie_slot_1",
            "pie_slot_2",
            "pie_slot_3",
            "pie_slot_4",
            "pie_slot_5",
            "pie_slot_6",
            "pie_slot_7",
            "pie_slot_8",
        )
        for slot in slots:
            command_id = getattr(preferences, slot, "NONE") if preferences is not None else "NONE"
            _draw_pie_command(pie, context, command_id)


CLASSES = (
    AIRETOPO_OT_select_cutter_tweak,
    VIEW3D_MT_airetopo_pie,
)


def register_keymaps():
    preferences = get_preferences(bpy.context)

    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is None:
        return

    keymap = keyconfig.keymaps.new(name="3D View", space_type="VIEW_3D")

    if _preference_value(preferences, "enable_cutter_tweak_hotkey", True):
        item = keymap.keymap_items.new(
            AIRETOPO_OT_select_cutter_tweak.bl_idname,
            **_event_kwargs(
                _preference_value(preferences, "cutter_tweak_key", "D"),
                _preference_value(preferences, "cutter_tweak_ctrl", False),
                _preference_value(preferences, "cutter_tweak_shift", False),
                _preference_value(preferences, "cutter_tweak_alt", False),
            ),
        )
        KEYMAP_ITEMS.append((keymap, item))

    if _preference_value(preferences, "enable_pie_menu_hotkey", True):
        item = keymap.keymap_items.new(
            "wm.call_menu_pie",
            **_event_kwargs(
                _preference_value(preferences, "pie_menu_key", "C"),
                _preference_value(preferences, "pie_menu_ctrl", False),
                _preference_value(preferences, "pie_menu_shift", True),
                _preference_value(preferences, "pie_menu_alt", False),
            ),
        )
        item.properties.name = VIEW3D_MT_airetopo_pie.bl_idname
        KEYMAP_ITEMS.append((keymap, item))


def unregister_keymaps():
    for keymap, item in reversed(KEYMAP_ITEMS):
        try:
            keymap.keymap_items.remove(item)
        except Exception:
            pass
    KEYMAP_ITEMS.clear()


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    register_keymaps()


def unregister():
    unregister_keymaps()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
