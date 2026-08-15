import bpy
from bpy.types import WorkSpaceTool

from .localization import t


DRAW_CUTTER_TOOL_ID = "polygroups_generator.draw_cutter_plane_tool"
DRAW_CUTTER_ARC_TOOL_ID = "polygroups_generator.draw_cutter_arc_tool"
VIEW3D_CURSOR_TOOL_ID = "builtin.cursor"


def _tool_id(item):
    return getattr(item, "idname", None)


def _remove_tool_from_items(items, tool_id):
    for index, item in enumerate(items):
        if _tool_id(item) == tool_id:
            return items.pop(index)

        if isinstance(item, tuple):
            group_items = list(item)
            for group_index, group_item in enumerate(group_items):
                if _tool_id(group_item) == tool_id:
                    tool = group_items.pop(group_index)
                    if group_items:
                        items[index] = tuple(group_items)
                    else:
                        items.pop(index)
                    return tool

    return None


def _move_draw_cutter_tool_after_cursor():
    try:
        from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    except Exception:
        return

    tools = VIEW3D_PT_tools_active._tools.get("OBJECT")
    if not tools:
        return

    tool = _remove_tool_from_items(tools, DRAW_CUTTER_TOOL_ID)
    if tool is None:
        return

    insert_index = None
    for index, item in enumerate(tools):
        if _tool_id(item) == VIEW3D_CURSOR_TOOL_ID:
            insert_index = index + 1
            break

    if insert_index is None:
        tools.append(tool)
    else:
        tools.insert(insert_index, tool)

    arc_tool = _remove_tool_from_items(tools, DRAW_CUTTER_ARC_TOOL_ID)
    if arc_tool is not None:
        tools.insert(tools.index(tool) + 1, arc_tool)


class VIEW3D_WST_polygroups_draw_cutter_plane(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_TOOL_ID
    bl_label = "Draw Cutter Plane"
    bl_description = "Draw object-mode cutter planes for applying seams to a highpoly mesh"
    bl_icon = "ops.mesh.bisect"
    bl_cursor = "CROSSHAIR"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_plane",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        del tool
        settings = context.scene.polygroups_object_seam_cutter_settings
        layout.operator(
            "object.polygroups_apply_cutter_seams",
            text=t(context, "apply_cutter_seams"),
            icon="MOD_BOOLEAN",
        )
        layout.prop(settings, "cutter_size_multiplier", text=t(context, "cutter_size"))
        layout.prop(settings, "cutter_alpha", text=t(context, "cutter_alpha"))
        layout.prop(settings, "cutter_solidify_thickness", text=t(context, "plane_thickness"))


class VIEW3D_WST_polygroups_draw_cutter_arc(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_ARC_TOOL_ID
    bl_label = "Draw Cutter Arc"
    bl_description = "Draw object-mode cutter arcs from three viewport points"
    bl_icon = "ops.curve.draw"
    bl_cursor = "CROSSHAIR"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_arc",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        del tool
        settings = context.scene.polygroups_object_seam_cutter_settings
        layout.operator(
            "object.polygroups_apply_cutter_seams",
            text=t(context, "apply_cutter_seams"),
            icon="MOD_BOOLEAN",
        )
        layout.prop(settings, "cutter_size_multiplier", text=t(context, "cutter_size"))
        layout.prop(settings, "cutter_arc_segments", text=t(context, "cylinder_segments"))
        layout.prop(settings, "cutter_alpha", text=t(context, "cutter_alpha"))
        layout.prop(settings, "cutter_solidify_thickness", text=t(context, "plane_thickness"))


class VIEW3D_WST_polygroups_knife_seam(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = "polygroups_generator.knife_seam_tool"
    bl_label = "Knife Seam"
    bl_description = "Knife cut through the entire mesh and mark the new cut edges as seams"
    bl_icon = "ops.mesh.knife_tool"
    bl_cursor = "KNIFE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "mesh.polygroups_knife_seam",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        props = tool.operator_properties("mesh.polygroups_knife_seam")
        layout.prop(props, "stable_view_cut", text=t(context, "stable_view_cut"))
        layout.prop(props, "use_occlude_geometry", text=t(context, "occlude_geometry"))
        layout.prop(props, "only_selected", text=t(context, "only_selected"))
        layout.prop(props, "xray", text=t(context, "xray"))
        layout.prop(props, "mark_seam", text=t(context, "mark_as_seam"))
        layout.prop(
            props,
            "clear_selection_after_cutting",
            text=t(context, "clear_selection_after_cutting"),
        )


class VIEW3D_WST_polygroups_quick_knife_seam(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = "polygroups_generator.quick_knife_seam_tool"
    bl_label = "Quick Knife Seam"
    bl_description = "Bisect through the full mesh, then mark the cut line as seams"
    bl_icon = "ops.mesh.bisect"
    bl_cursor = "KNIFE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "mesh.polygroups_quick_knife_seam",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        props = tool.operator_properties("mesh.polygroups_quick_knife_seam")
        layout.prop(props, "use_fill", text=t(context, "fill"))
        layout.prop(props, "threshold", text=t(context, "threshold"))
        layout.prop(props, "mark_seam", text=t(context, "mark_as_seam"))
        layout.prop(
            props,
            "clear_selection_after_cutting",
            text=t(context, "clear_selection_after_cutting"),
        )


def register():
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_plane,
        after={"builtin.cursor"},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_arc,
        after={DRAW_CUTTER_TOOL_ID},
        separator=False,
        group=False,
    )
    _move_draw_cutter_tool_after_cursor()
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_knife_seam,
        after={"builtin.bevel"},
        separator=True,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_quick_knife_seam,
        after={"polygroups_generator.knife_seam_tool"},
        separator=False,
        group=False,
    )


def unregister():
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_quick_knife_seam)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_knife_seam)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_arc)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_plane)
