from .operators.seam_eraser import AREA_TOOL_ID, PATH_TOOL_ID, draw_eraser_cursor, stop_erasers
import bpy
from bpy.types import WorkSpaceTool

from .localization import t
from .operators.connect_vertex_seam import TOOL_ID as VERTEX_SEAM_TOOL_ID
from .operators.connect_vertex_seam import draw_vertex_seam_cursor, _cursor_ctrl
from .operators.edge_seam_path import TOOL_ID as EDGE_SEAM_TOOL_ID
from .operators.edge_seam_path import draw_edge_seam_cursor, register_hover_cache, unregister_hover_cache


DRAW_CUTTER_GRID_TOOL_ID = "polygroups_generator.draw_cutter_grid_tool"
DRAW_CUTTER_TOOL_ID = "polygroups_generator.draw_cutter_plane_tool"
DRAW_CUTTER_ARC_TOOL_ID = "polygroups_generator.draw_cutter_arc_tool"
DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID = "polygroups_generator.draw_cutter_local_contour_tool"
DRAW_CUTTER_LOCAL_RING_TOOL_ID = "polygroups_generator.draw_cutter_local_ring_tool"
DRAW_CUTTER_PATH_TOOL_ID = "polygroups_generator.draw_cutter_path_tool"
DRAW_CUTTER_DRAW_TOOL_ID = "polygroups_generator.draw_cutter_draw_tool"
VIEW3D_CURSOR_TOOL_ID = "builtin.cursor"
CUTTER_TOOL_ORDER = (
    DRAW_CUTTER_TOOL_ID,
    DRAW_CUTTER_LOCAL_RING_TOOL_ID,
    DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID,
    DRAW_CUTTER_ARC_TOOL_ID,
    DRAW_CUTTER_PATH_TOOL_ID,
    DRAW_CUTTER_DRAW_TOOL_ID,
    DRAW_CUTTER_GRID_TOOL_ID,
)


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

    cutter_tools = {
        tool_id: _remove_tool_from_items(tools, tool_id)
        for tool_id in CUTTER_TOOL_ORDER
    }
    if cutter_tools[DRAW_CUTTER_TOOL_ID] is None:
        return

    insert_index = None
    for index, item in enumerate(tools):
        if _tool_id(item) == VIEW3D_CURSOR_TOOL_ID:
            insert_index = index + 1
            break

    cutter_group = tuple(
        cutter_tools[tool_id]
        for tool_id in CUTTER_TOOL_ORDER
        if cutter_tools[tool_id] is not None
    )
    if not cutter_group:
        return

    if insert_index is None:
        tools.append(cutter_group)
    else:
        tools.insert(insert_index, cutter_group)


def _active_cutter_label_key(tool_id):
    if tool_id == DRAW_CUTTER_GRID_TOOL_ID:
        return "draw_cutter_grid"
    if tool_id == DRAW_CUTTER_ARC_TOOL_ID:
        return "draw_cutter_arc"
    if tool_id == DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID:
        return "draw_cutter_local_contour"
    if tool_id == DRAW_CUTTER_LOCAL_RING_TOOL_ID:
        return "draw_cutter_local_ring"
    if tool_id == DRAW_CUTTER_PATH_TOOL_ID:
        return "draw_cutter_path"
    if tool_id == DRAW_CUTTER_DRAW_TOOL_ID:
        return "draw_cutter_draw"
    return "draw_cutter_plane"


def _draw_cutter_tool_settings(context, layout, tool, cutter_type):
    settings = context.scene.polygroups_object_seam_cutter_settings

    def draw_enum_icon_toggle(row, property_name, items):
        current_value = getattr(settings, property_name)
        for value, label, icon in items:
            operator = row.operator(
                "wm.context_set_enum",
                text=label,
                icon=icon,
                depress=current_value == value,
            )
            operator.data_path = f"scene.polygroups_object_seam_cutter_settings.{property_name}"
            operator.value = value

    row = layout.row(align=True)
    apply_button_row = row.row(align=True)
    apply_button_row.enabled = any(
        obj.type in {"MESH", "CURVE"}
        and obj.get("polygroups_object_seam_cutter")
        for obj in context.selected_objects
    )
    apply_button_row.operator(
        "object.polygroups_apply_cutter_seams",
        text=t(context, "apply_cutter_seams"),
        icon="MOD_BOOLEAN",
    )
    row.menu(
        "VIEW3D_MT_polygroups_cutter_tool_type",
        text=t(context, _active_cutter_label_key(tool.idname)),
        icon="TOOL_SETTINGS",
    )
    if cutter_type == "GRID_PLANE":
        draw_grid_actions(context, row)
        draw_enum_icon_toggle(
            row, "cutter_grid_apply_method",
            (("BISECT", "Bisect", "MOD_BOOLEAN"),
             ("KNIFE_INTERSECT", "Knife Intersect", "EDGESEL")),
        )
    if cutter_type in {"ARC", "LOCAL_RING", "LOCAL_CONTOUR", "PATH", "DRAW"}:
        draw_enum_icon_toggle(
            row,
            "cutter_apply_method",
            (
                ("BOOLEAN", "Boolean", "MOD_BOOLEAN"),
                ("KNIFE", "Knife", "EDGESEL"),
            ),
        )
        draw_enum_icon_toggle(
            row,
            "cutter_boolean_solver",
            (
                ("FLOAT", "Float", "VIEWZOOM"),
                ("EXACT", "Exact", "CHECKMARK"),
            ),
        )
        row.prop(settings, "cutter_auto_fix_mesh", text=t(context, "cutter_auto_fix_mesh"), toggle=True)
    row.label(text=t(context, "ctrl_draw_hint"))
    axis_row = row.row(align=True)
    for axis in ("X", "Y", "Z"):
        axis_row.prop_enum(settings, "cutter_mirror_axis", axis, text=axis)
    row.operator(
        "object.polygroups_copy_mirror_cutters",
        text=t(context, "copy_mirror_cutters"),
        icon="MOD_MIRROR",
    )

    if cutter_type in {"PATH", "DRAW"}:
        layout.prop(settings, "cutter_extrude", text=t(context, "cutter_extrude"))
        layout.prop(settings, "cutter_thickness", text=t(context, "cutter_thickness"))
        layout.prop(settings, "cutter_path_render_u", text=t(context, "path_render_u"))

    if cutter_type in {"PLANE", "ARC"}:
        layout.prop(settings, "cutter_size_multiplier", text=t(context, "cutter_size"))
        layout.prop(settings, "fill_split_cutters", text=t(context, "fill_cutter"))
        layout.operator(
            "object.polygroups_split_object_by_cutters",
            text=t(context, "split_object"),
            icon="MOD_EXPLODE",
        )
    if cutter_type == "GRID_PLANE":
        draw_grid_settings(context, layout, show_actions=False)
    if cutter_type == "ARC":
        layout.prop(settings, "cutter_arc_segments", text=t(context, "cylinder_segments"))
    if cutter_type == "LOCAL_CONTOUR":
        layout.prop(settings, "cutter_contour_points", text=t(context, "contour_points"))
        layout.prop(settings, "cutter_contour_offset", text=t(context, "contour_offset"))
    if cutter_type == "LOCAL_RING":
        layout.prop(settings, "cutter_local_ring_fit_mode", text=t(context, "local_ring_fit_mode"))
        layout.prop(settings, "cutter_local_ring_segments", text=t(context, "local_ring_segments"))
        layout.prop(settings, "cutter_local_ring_radius_offset", text=t(context, "local_ring_radius_offset"))
    if cutter_type == "PATH":
        tilt_row = layout.row(align=True)
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_minus"))
        tilt_operator.mode = "DECREASE"
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_plus"))
        tilt_operator.mode = "INCREASE"
        edit_row = layout.row(align=True)
        edit_row.operator("object.polygroups_bezier_cutter_paths", text=t(context, "curve_bezier"))
        edit_row.operator("object.polygroups_toggle_cyclic_cutter_paths", text=t(context, "curve_cyclic"))
        edit_row.operator("object.polygroups_smooth_cutter_paths", text=t(context, "curve_smooth"))
        edit_row.operator("object.polygroups_smooth_cutter_path_tilt", text=t(context, "curve_smooth_tilt"))
        layout.prop(settings, "continue_path_cutters", text=t(context, "continue_path_cutters"))
        layout.prop(settings, "cutter_path_join_distance", text=t(context, "path_join_distance"))
        layout.operator(
            "object.polygroups_join_cutter_paths",
            text=t(context, "join_cutter_paths"),
            icon="AUTOMERGE_ON",
        )
    if cutter_type == "DRAW":
        tilt_row = layout.row(align=True)
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_minus"))
        tilt_operator.mode = "DECREASE"
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_plus"))
        tilt_operator.mode = "INCREASE"
        edit_row = layout.row(align=True)
        edit_row.operator("object.polygroups_bezier_cutter_paths", text=t(context, "curve_bezier"))
        edit_row.operator("object.polygroups_toggle_cyclic_cutter_paths", text=t(context, "curve_cyclic"))
        edit_row.operator("object.polygroups_smooth_cutter_paths", text=t(context, "curve_smooth"))
        edit_row.operator("object.polygroups_smooth_cutter_path_tilt", text=t(context, "curve_smooth_tilt"))
        layout.prop(settings, "cutter_draw_min_point_distance", text=t(context, "draw_point_distance"))
        layout.prop(settings, "cutter_draw_simplify_distance", text=t(context, "draw_simplify_distance"))
        layout.prop(settings, "continue_path_cutters", text=t(context, "continue_path_cutters"))
        layout.prop(settings, "cutter_path_join_distance", text=t(context, "path_join_distance"))
        layout.operator(
            "object.polygroups_join_cutter_paths",
            text=t(context, "join_cutter_paths"),
            icon="AUTOMERGE_ON",
        )
    layout.prop(settings, "cutter_alpha", text=t(context, "cutter_alpha"))
    if cutter_type == "PLANE":
        layout.prop(settings, "cutter_solidify_thickness", text=t(context, "plane_thickness"))
    if cutter_type in {"ARC", "LOCAL_RING", "LOCAL_CONTOUR"}:
        layout.prop(settings, "cutter_thickness", text=t(context, "cutter_thickness"))


def draw_grid_actions(context, layout):
    settings = context.scene.polygroups_object_seam_cutter_settings
    actions = layout.row(align=True)
    actions.operator("object.polygroups_generate_cutter_grid", text=t(context, "grid_generate_auto"), icon="MESH_CUBE")
    actions.prop(settings, "cutter_grid_auto_rotate", text=t(context, "grid_auto_rotate"), toggle=True)


def draw_grid_settings(context, layout, show_actions=True):
    settings = context.scene.polygroups_object_seam_cutter_settings
    if show_actions:
        draw_grid_actions(context, layout)
        layout.prop(settings, "cutter_grid_apply_method", text=t(context, "cutter_apply_method"), expand=True)
    row = layout.row(align=True)
    row.label(text=t(context, "grid_planes"))
    for index, axis in enumerate("XYZ"):
        row.prop(settings, "cutter_grid_axes", index=index, text=axis, toggle=True)
        count = row.row(align=True)
        count.enabled = settings.cutter_grid_axes[index]
        count.prop(settings, "cutter_grid_counts", index=index, text="")


class VIEW3D_MT_polygroups_cutter_tool_type(bpy.types.Menu):
    bl_label = "Cutter Type"

    def draw(self, context):
        layout = self.layout
        items = (
            (DRAW_CUTTER_TOOL_ID, "draw_cutter_plane", "MESH_PLANE"),
            (DRAW_CUTTER_LOCAL_RING_TOOL_ID, "draw_cutter_local_ring", "MESH_CIRCLE"),
            (DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID, "draw_cutter_local_contour", "MESH_CIRCLE"),
            (DRAW_CUTTER_ARC_TOOL_ID, "draw_cutter_arc", "CURVE_BEZCURVE"),
            (DRAW_CUTTER_PATH_TOOL_ID, "draw_cutter_path", "CURVE_PATH"),
            (DRAW_CUTTER_DRAW_TOOL_ID, "draw_cutter_draw", "GREASEPENCIL"),
            (DRAW_CUTTER_GRID_TOOL_ID, "draw_cutter_grid", "MESH_CUBE"),
        )
        for tool_id, text_key, icon in items:
            operator = layout.operator(
                "wm.tool_set_by_id",
                text=t(context, text_key),
                icon=icon,
            )
            operator.name = tool_id


class VIEW3D_WST_polygroups_draw_cutter_plane(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_TOOL_ID
    bl_label = "Cutter Tweak: Plane"
    bl_description = "Select normally; hold Ctrl and click to draw object-mode cutter planes"
    bl_icon = "ops.mesh.primitive_grid_add_gizmo"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_plane",
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        _draw_cutter_tool_settings(context, layout, tool, "PLANE")


class VIEW3D_WST_polygroups_draw_cutter_grid(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_GRID_TOOL_ID
    bl_label = "Cutter Tweak: Grid Volume"
    bl_description = "Ctrl-click the first base corner, click the opposite corner, then set depth and click"
    bl_icon = "ops.mesh.primitive_cube_add_gizmo"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_grid",
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        _draw_cutter_tool_settings(context, layout, tool, "GRID_PLANE")


class VIEW3D_WST_polygroups_draw_cutter_arc(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_ARC_TOOL_ID
    bl_label = "Cutter Tweak: Arc"
    bl_description = "Select normally; hold Ctrl and click to draw object-mode cutter arcs"
    bl_icon = "ops.gpencil.primitive_arc"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_arc",
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        _draw_cutter_tool_settings(context, layout, tool, "ARC")


class VIEW3D_WST_polygroups_draw_cutter_local_ring(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_LOCAL_RING_TOOL_ID
    bl_label = "Cutter Tweak: Local Ring"
    bl_description = "Select normally; hold Ctrl and click two points to draw a local ring cutter"
    bl_icon = "ops.mesh.primitive_cylinder_add_gizmo"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_local_ring",
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        _draw_cutter_tool_settings(context, layout, tool, "LOCAL_RING")


class VIEW3D_WST_polygroups_draw_cutter_local_contour(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID
    bl_label = "Cutter Tweak: Local Contour"
    bl_description = "Select normally; hold Ctrl and click across a local mesh section to draw a fitted contour cutter"
    bl_icon = "ops.mesh.primitive_cylinder_add_gizmo"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_local_contour",
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        _draw_cutter_tool_settings(context, layout, tool, "LOCAL_CONTOUR")


class VIEW3D_WST_polygroups_draw_cutter_path(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_PATH_TOOL_ID
    bl_label = "Cutter Tweak: Path"
    bl_description = "Select normally; hold Ctrl and click to draw object-mode cutter paths"
    bl_icon = "ops.curve.draw"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_path",
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        _draw_cutter_tool_settings(context, layout, tool, "PATH")


class VIEW3D_WST_polygroups_draw_cutter_draw(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = DRAW_CUTTER_DRAW_TOOL_ID
    bl_label = "Cutter Tweak: Draw"
    bl_description = "Select normally; hold Ctrl and drag to draw object-mode cutter strokes on the mesh surface"
    bl_icon = "ops.curve.draw"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "object.polygroups_draw_cutter_draw",
            {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True},
            {"properties": [("use_event_as_start", True)]},
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        _draw_cutter_tool_settings(context, layout, tool, "DRAW")


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
        props = context.scene.polygroups_knife_seam_settings
        layout.prop(props, "cut_mode", text=t(context, "knife_cut_mode"))
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


class VIEW3D_WST_polygroups_connect_vertex_seam(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = VERTEX_SEAM_TOOL_ID
    bl_label = "Vertex Seam Path"
    bl_description = "Select normally; Ctrl-click A, B, C to connect vertices with seams; Space/Esc/right-click finishes the chain"
    bl_icon = "ops.mesh.dupli_extrude_cursor"
    bl_cursor = "CROSSHAIR"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("mesh.polygroups_connect_vertex_seam_click", {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True}, None),
        # Pass-through observers update the preview even when Ctrl changes without mouse motion.
        ("mesh.polygroups_seam_cursor_modifier", {"type": "MOUSEMOVE", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "LEFT_CTRL", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "RIGHT_CTRL", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "WINDOW_DEACTIVATE", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_connect_vertex_seam_click", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("reset", True)]}),
        ("mesh.polygroups_connect_vertex_seam_click", {"type": "ESC", "value": "PRESS"},
         {"properties": [("reset", True)]}),
        ("mesh.polygroups_connect_vertex_seam_click", {"type": "SPACE", "value": "PRESS"},
         {"properties": [("reset", True)]}),
    )
    draw_cursor = staticmethod(draw_vertex_seam_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        layout.label(text=t(context, "connect_seam_hint_next"))


class VIEW3D_WST_polygroups_edge_seam_path(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = EDGE_SEAM_TOOL_ID
    bl_label = "Edge Seam Path"
    bl_description = "Select normally; Ctrl-click A, B, C to mark existing edge rows with seams; Space/Esc/right-click finishes the chain"
    bl_icon = "ops.mesh.dupli_extrude_cursor"
    bl_cursor = "NONE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("mesh.polygroups_edge_seam_path_click", {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True}, None),
        ("mesh.polygroups_edge_seam_path_click", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("reset", True)]}),
        ("mesh.polygroups_edge_seam_path_click", {"type": "ESC", "value": "PRESS"},
         {"properties": [("reset", True)]}),
        ("mesh.polygroups_edge_seam_path_click", {"type": "SPACE", "value": "PRESS"},
         {"properties": [("reset", True)]}),
    )
    draw_cursor = staticmethod(draw_edge_seam_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        layout.label(text=t(context, "connect_seam_hint_next"))


class VIEW3D_WST_polygroups_seam_eraser(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = AREA_TOOL_ID
    bl_label = "Seam Eraser"
    bl_description = "Erase seams with Circle or Lasso; drag with the left mouse button"
    bl_icon = "ops.generic.select_circle"
    bl_cursor = "CROSSHAIR"
    bl_widget = None
    bl_keymap = (
        ("mesh.polygroups_seam_eraser", {"type": "LEFTMOUSE", "value": "PRESS"}, None),
        ("mesh.polygroups_seam_eraser_resize", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True}, None),
        ("mesh.polygroups_seam_eraser_resize", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True}, None),
    )
    draw_cursor = staticmethod(draw_eraser_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        props = tool.operator_properties("mesh.polygroups_seam_eraser")
        layout.prop(props, "shape", expand=True)
        if props.shape == "CIRCLE":
            layout.prop(props, "radius")


class VIEW3D_WST_polygroups_edge_seam_eraser(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = PATH_TOOL_ID
    bl_label = "Edge Seam Eraser"
    bl_description = "Ctrl-click vertices to erase seams along existing edge rows"
    bl_icon = "ops.mesh.dupli_extrude_cursor"
    bl_cursor = "NONE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("mesh.polygroups_edge_seam_eraser_click", {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True}, None),
        ("mesh.polygroups_edge_seam_eraser_click", {"type": "RIGHTMOUSE", "value": "PRESS"}, {"properties": [("reset", True)]}),
        ("mesh.polygroups_edge_seam_eraser_click", {"type": "ESC", "value": "PRESS"}, {"properties": [("reset", True)]}),
        ("mesh.polygroups_edge_seam_eraser_click", {"type": "SPACE", "value": "PRESS"}, {"properties": [("reset", True)]}),
    )
    draw_cursor = staticmethod(draw_edge_seam_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        layout.label(text=t(context, "seam_erase_path_hint"))


def draw_seam_status(self, context):
    if context.mode != "EDIT_MESH":
        return
    tool = context.workspace.tools.from_space_view3d_mode("EDIT_MESH", create=False)
    if tool is not None and tool.idname in {AREA_TOOL_ID, PATH_TOOL_ID}:
        self.layout.label(text=t(context, "seam_erase_drag_hint" if tool.idname == AREA_TOOL_ID else "seam_erase_path_hint"))
    elif tool is not None and tool.idname in {VERTEX_SEAM_TOOL_ID, EDGE_SEAM_TOOL_ID}:
        self.layout.label(text=t(context, "seam_ctrl_status"))


def register():
    bpy.types.STATUSBAR_HT_header.prepend(draw_seam_status)
    register_hover_cache()
    bpy.utils.register_class(VIEW3D_MT_polygroups_cutter_tool_type)
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_plane,
        after={"builtin.cursor"},
        separator=False,
        group=True,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_local_ring,
        after={DRAW_CUTTER_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_local_contour,
        after={DRAW_CUTTER_LOCAL_RING_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_arc,
        after={DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_path,
        after={DRAW_CUTTER_ARC_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_draw,
        after={DRAW_CUTTER_PATH_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_draw_cutter_grid,
        after={DRAW_CUTTER_DRAW_TOOL_ID}, separator=False, group=False,
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
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_connect_vertex_seam,
        after={"polygroups_generator.quick_knife_seam_tool"},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_edge_seam_path,
        after={VERTEX_SEAM_TOOL_ID},
        separator=False,
        group=False,
    )

    bpy.utils.register_tool(VIEW3D_WST_polygroups_seam_eraser, after={EDGE_SEAM_TOOL_ID}, separator=True)
    bpy.utils.register_tool(VIEW3D_WST_polygroups_edge_seam_eraser, after={AREA_TOOL_ID})

def unregister():
    stop_erasers()
    bpy.types.STATUSBAR_HT_header.remove(draw_seam_status)
    _cursor_ctrl.clear()
    unregister_hover_cache()
    # Switching tools removes Blender's cursor callback before unregister_tool
    # removes the definition and keymap (it does not remove the callback itself).
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            with bpy.context.temp_override(window=window, area=area, region=region):
                if bpy.context.mode != "EDIT_MESH":
                    continue
                tool = window.workspace.tools.from_space_view3d_mode("EDIT_MESH", create=False)
                if tool is not None and tool.idname in {VERTEX_SEAM_TOOL_ID, EDGE_SEAM_TOOL_ID, AREA_TOOL_ID, PATH_TOOL_ID}:
                    bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_edge_seam_eraser)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_seam_eraser)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_edge_seam_path)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_connect_vertex_seam)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_quick_knife_seam)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_knife_seam)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_draw)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_path)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_local_contour)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_local_ring)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_arc)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_grid)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_draw_cutter_plane)
    bpy.utils.unregister_class(VIEW3D_MT_polygroups_cutter_tool_type)
