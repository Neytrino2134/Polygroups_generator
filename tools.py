from .custom_icons import icon_kwargs, tool_icon
from .operators.seam_eraser import AREA_TOOL_ID, PATH_TOOL_ID, draw_eraser_cursor, stop_erasers
import bpy
from bpy.types import WorkSpaceTool

from .localization import t
from .operators.connect_vertex_seam import TOOL_ID as VERTEX_SEAM_TOOL_ID
from .operators.connect_vertex_seam import draw_vertex_seam_cursor, _cursor_ctrl, _cursor_erase
from .operators.edge_seam_path import TOOL_ID as EDGE_SEAM_TOOL_ID
from .operators.edge_merger import TOOL_ID as EDGE_MERGER_TOOL_ID
from .operators.edge_seam_path import (
    draw_edge_seam_cursor,
    draw_edge_seam_eraser_cursor,
    draw_longitudinal_seam_cursor,
    draw_smart_seam_cursor,
    register_hover_cache,
    unregister_hover_cache,
)
from .operators.smart_angle_seams import TOOL_ID as SMART_SEAMS_TOOL_ID
from .operators.mark_longitudinal_seam import TOOL_ID as LONGITUDINAL_SEAM_TOOL_ID
from .operators.small_islands_tool import TOOL_ID as SMALL_ISLANDS_MERGER_TOOL_ID
from .operators.small_islands_tool import SELECTOR_TOOL_ID as ISLAND_SELECTOR_TOOL_ID


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


def _draw_seam_auto_uv_settings(context, layout):
    """Draw section 8 Auto UV settings in an Edit Mode tool header."""
    settings = context.scene.polygroups_seam_finalization_settings
    layout.separator(type="LINE")
    layout.prop(settings, "auto_unwrap_after_seam",
                text=t(context, "auto_unwrap"), toggle=True, icon="UV")
    average = layout.row(align=True)
    average.enabled = settings.auto_unwrap_after_seam
    average.prop(settings, "auto_average_islands_scale_after_unwrap",
                 text=t(context, "auto_average_islands_scale"),
                 toggle=True, icon="UV_SYNC_SELECT")


def _draw_smart_auto_relax_settings(context, layout):
    settings = context.scene.polygroups_seam_preparation_settings
    layout.separator(type="LINE")
    layout.prop(settings, "smart_seam_auto_relax",
                text=t(context, "smart_seam_auto_relax"),
                toggle=True, icon="MOD_SMOOTH")
    if not settings.smart_seam_auto_relax:
        return
    layout.prop(settings, "seam_relax_iterations",
                text=t(context, "seam_relax_iterations"))
    layout.label(text=t(context, "seam_relax_selected_area_only"), icon="CHECKBOX_HLT")
    corner = layout.row(align=True)
    corner.prop(settings, "seam_relax_use_corner_angle",
                text=t(context, "seam_relax_use_corner_angle"), toggle=True)
    angle = corner.row(align=True)
    angle.enabled = settings.seam_relax_use_corner_angle
    angle.prop(settings, "seam_relax_corner_angle", text="")
    layout.prop(settings, "seam_relax_protection_radius",
                text=t(context, "seam_relax_protection_radius"))


def _replace_registered_tool_icon(tool_cls, icon):
    """Replace the immutable ToolDef stored in Blender's toolbar lists."""
    tool_cls.bl_icon = icon
    old = getattr(tool_cls, "_bl_tool", None)
    if old is None or old.icon == icon:
        return
    new = old._replace(icon=icon)
    tool_cls._bl_tool = new
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active

    def replace(items):
        for index, item in enumerate(items):
            if getattr(item, "idname", None) == old.idname:
                items[index] = new
                return True
            if isinstance(item, tuple):
                group = list(item)
                if replace(group):
                    items[index] = tuple(group)
                    return True
        return False

    replace(VIEW3D_PT_tools_active._tools.get("EDIT_MESH", []))


def update_dynamic_seam_tool_icons(settings, context=None):
    """Refresh toolbar icons immediately when a pin-mode option changes."""
    path_suffix = "_pin" if settings.seam_path_pin else ""
    eraser_suffix = "_pin" if settings.seam_eraser_clear_mode == "PINNED" else ""
    smart_suffix = "_pin" if settings.smart_seam_pin_generated else ""
    finalization = (getattr(getattr(context, "scene", None),
                            "polygroups_seam_finalization_settings", None)
                    if context is not None else None)
    longitudinal_suffix = "_pin" if (
        finalization is not None and finalization.pin_longitudinal_seam
    ) else ""
    for cls, key, fallback in (
        (VIEW3D_WST_polygroups_connect_vertex_seam, "connect_vertex_seam" + path_suffix, "ops.mesh.dupli_extrude_cursor"),
        (VIEW3D_WST_polygroups_edge_seam_path, "edge_seam_path" + path_suffix, "ops.mesh.dupli_extrude_cursor"),
        (VIEW3D_WST_polygroups_seam_eraser, "seam_eraser" + eraser_suffix, "ops.generic.select_circle"),
        (VIEW3D_WST_polygroups_edge_seam_eraser, "edge_seam_eraser" + eraser_suffix, "ops.mesh.dupli_extrude_cursor"),
        (VIEW3D_WST_polygroups_smart_seams_generator, "smart_seams_generator" + smart_suffix, "ops.mesh.mark_seam"),
        (VIEW3D_WST_polygroups_longitudinal_seam, "longitudinal_seam" + longitudinal_suffix, "ops.mesh.mark_seam"),
    ):
        _replace_registered_tool_icon(cls, tool_icon(key, fallback))
    if context is not None:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in {"VIEW_3D", "PROPERTIES"}:
                    area.tag_redraw()


def update_small_islands_merger_tool_icon(settings, context=None):
    icons = {
        "BOX": "ops.generic.select_box",
        "LASSO": "ops.generic.select_lasso",
        "CIRCLE": "ops.generic.select_circle",
    }
    _replace_registered_tool_icon(
        VIEW3D_WST_polygroups_small_islands_merger,
        icons.get(settings.small_islands_merger_shape, icons["BOX"]),
    )
    if context is not None:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()


def update_island_selector_tool_icon(settings, context=None):
    icons = {
        "TWEAK": "ops.generic.select",
        "BOX": "ops.generic.select_box",
        "LASSO": "ops.generic.select_lasso",
        "CIRCLE": "ops.generic.select_circle",
    }
    _replace_registered_tool_icon(
        VIEW3D_WST_polygroups_island_selector,
        icons.get(settings.island_selector_shape, icons["TWEAK"]),
    )
    if context is not None:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()


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

    def draw_enum_icon_toggle(row, property_name, items, show_text=True):
        current_value = getattr(settings, property_name)
        for value, label, icon in items:
            operator = row.operator(
                "wm.context_set_enum",
                text=label if show_text else "",
                icon=icon,
                depress=current_value == value,
            )
            operator.data_path = f"scene.polygroups_object_seam_cutter_settings.{property_name}"
            operator.value = value

    row = layout.row(align=True)
    row.menu(
        "VIEW3D_MT_polygroups_cutter_tool_type",
        text="",
        **icon_kwargs(_active_cutter_label_key(tool.idname), "TOOL_SETTINGS"),
    )
    row.separator(type="LINE")
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
    row.operator(
        "object.polygroups_create_cutter_backup",
        text="",
        icon="DUPLICATE",
    )
    row.operator(
        "object.polygroups_restore_cutter_backup",
        text="",
        icon="RECOVER_LAST",
    )
    row.separator(type="LINE")
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
            show_text=False,
        )
    if cutter_type in {"PLANE", "ARC", "LOCAL_RING", "LOCAL_CONTOUR", "PATH", "DRAW"}:
        row.separator(type="LINE")
        if cutter_type == "LOCAL_RING":
            row.prop(
                settings, "cutter_local_ring_mark_pinned",
                text=t(context, "mark_as_pinned"), toggle=True, icon="PINNED",
            )
        elif cutter_type == "LOCAL_CONTOUR":
            row.prop(
                settings, "cutter_local_contour_mark_pinned",
                text=t(context, "mark_as_pinned"), toggle=True, icon="PINNED",
            )
        elif cutter_type == "PATH":
            row.prop(
                settings, "cutter_path_mark_pinned",
                text=t(context, "mark_as_pinned"), toggle=True, icon="PINNED",
            )
        elif cutter_type == "DRAW":
            row.prop(
                settings, "cutter_draw_mark_pinned",
                text=t(context, "mark_as_pinned"), toggle=True, icon="PINNED",
            )
        row.prop(
            settings, "cutter_auto_fix_mesh",
            text=t(context, "cutter_auto_fix_mesh"), toggle=True,
        )
        fin_toggle = row.row(align=True)
        fin_toggle.enabled = settings.cutter_auto_fix_mesh
        fin_toggle.prop(settings, "cutter_auto_fix_fin_faces", text="", icon="FACESEL", toggle=True)
        seam_toggle = row.row(align=True)
        seam_toggle.enabled = settings.cutter_auto_fix_mesh
        seam_toggle.prop(settings, "cutter_auto_fix_seam_check", text="", icon="VIEWZOOM", toggle=True)
        islands_toggle = row.row(align=True)
        islands_toggle.enabled = settings.cutter_auto_fix_mesh
        islands_toggle.prop(settings, "cutter_auto_fix_small_islands", text="", icon="AUTOMERGE_ON", toggle=True)
        islands_threshold = row.row(align=True)
        islands_threshold.enabled = settings.cutter_auto_fix_mesh and settings.cutter_auto_fix_small_islands
        islands_threshold.ui_units_x = 3.5
        islands_threshold.prop(settings, "cutter_auto_fix_small_islands_threshold", text="")
        weld_toggle = row.row(align=True)
        weld_toggle.enabled = settings.cutter_auto_fix_mesh
        weld_toggle.prop(settings, "cutter_auto_fix_weld", text="", icon="AUTOMERGE_ON", toggle=True)
        weld_distance = row.row(align=True)
        weld_distance.enabled = settings.cutter_auto_fix_mesh and settings.cutter_auto_fix_weld
        weld_distance.ui_units_x = 3.5
        weld_distance.prop(settings, "cutter_auto_fix_weld_distance", text="")
        relax_toggle = row.row(align=True)
        relax_toggle.enabled = settings.cutter_auto_fix_mesh
        relax_toggle.prop(
            settings, "cutter_auto_fix_smart_relax_seams",
            text="", icon="MOD_SMOOTH", toggle=True,
        )
        triangulate_toggle = row.row(align=True)
        triangulate_toggle.enabled = settings.cutter_auto_fix_mesh
        triangulate_toggle.prop(
            settings, "cutter_auto_fix_triangulate_ngons",
            text="", icon="MOD_TRIANGULATE", toggle=True,
        )
    row.separator(type="LINE")
    row.operator(
        "object.polygroups_copy_mirror_cutters",
        text=t(context, "copy_mirror_cutters"),
        icon="MOD_MIRROR",
    )
    axis_row = row.row(align=True)
    for axis in ("X", "Y", "Z"):
        axis_row.prop_enum(settings, "cutter_mirror_axis", axis, text=axis)

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
        stabilize_row = layout.row(align=True)
        stabilize_row.prop(settings, "cutter_draw_stabilize_stroke",
                           text=t(context, "draw_stabilize_stroke"), toggle=True)
        stabilize_settings = stabilize_row.row(align=True)
        stabilize_settings.enabled = settings.cutter_draw_stabilize_stroke
        stabilize_settings.prop(settings, "cutter_draw_stabilize_radius",
                                text=t(context, "draw_stabilize_radius"))
        stabilize_settings.prop(settings, "cutter_draw_stabilize_factor",
                                text=t(context, "draw_stabilize_factor"))
        layout.prop(settings, "continue_path_cutters", text=t(context, "continue_path_cutters"))
        layout.prop(settings, "cutter_path_join_distance", text=t(context, "path_join_distance"))
        layout.operator(
            "object.polygroups_join_cutter_paths",
            text=t(context, "join_cutter_paths"),
            icon="AUTOMERGE_ON",
        )
    layout.separator(type="LINE")
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
    bl_description = "Choose the cutter tool; hold Ctrl and click in the viewport to draw"

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
                **icon_kwargs(text_key, icon),
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
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
        (
            "mesh.polygroups_knife_seam",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        props = context.scene.polygroups_knife_seam_settings
        mode_row = layout.row(align=True)
        mode_row.scale_x = 1.2
        mode_row.prop_enum(props, "cut_mode", "PLANE", text="Plane Cut", icon="MESH_PLANE")
        mode_row.prop_enum(props, "cut_mode", "POLYLINE", text="Multi Point", icon="IPO_LINEAR")
        _draw_seam_auto_uv_settings(context, layout)
        layout.prop(props, "use_occlude_geometry", text=t(context, "occlude_geometry"))
        layout.prop(props, "only_selected", text=t(context, "only_selected"))
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
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
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
        _draw_seam_auto_uv_settings(context, layout)


class VIEW3D_WST_polygroups_connect_vertex_seam(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = VERTEX_SEAM_TOOL_ID
    bl_label = "Vertex Seam Path"
    bl_description = "Select normally; Ctrl-click A, B, C to connect vertices with seams; Space/Esc/right-click finishes the chain"
    bl_icon = "ops.mesh.dupli_extrude_cursor"
    bl_cursor = "NONE"
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
        layout.prop(context.scene.polygroups_seam_preparation_settings, "seam_path_pin", text=t(context, "mark_as_pinned"))
        _draw_seam_auto_uv_settings(context, layout)
        layout.label(text=t(context, "connect_seam_hint_next"))


class VIEW3D_WST_polygroups_edge_seam_path(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = EDGE_SEAM_TOOL_ID
    bl_label = "Edge Seam Path"
    bl_description = "Ctrl-click vertices to mark a seam path; Ctrl-Shift-click to erase a seam path"
    bl_icon = "ops.mesh.dupli_extrude_cursor"
    bl_cursor = "NONE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("mesh.polygroups_edge_seam_eraser_click",
         {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True, "shift": True}, None),
        ("mesh.polygroups_edge_seam_path_click", {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True}, None),
        # Modifier observers switch the cursor badge between Edge and Eraser.
        ("mesh.polygroups_seam_cursor_modifier", {"type": "MOUSEMOVE", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "LEFT_CTRL", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "RIGHT_CTRL", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "LEFT_SHIFT", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "RIGHT_SHIFT", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "WINDOW_DEACTIVATE", "value": "ANY", "any": True}, None),
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
        layout.prop(context.scene.polygroups_seam_preparation_settings, "seam_path_pin", text=t(context, "mark_as_pinned"))
        _draw_seam_auto_uv_settings(context, layout)
        layout.label(text="Ctrl+LMB: mark path   Ctrl+Shift+LMB: erase path")


class VIEW3D_WST_polygroups_smart_seams_generator(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = SMART_SEAMS_TOOL_ID
    bl_label = "Smart Seams Generator"
    bl_description = "Click a vertex to select its seam-bounded island and generate smart seams"
    bl_icon = "ops.mesh.mark_seam"
    bl_cursor = "NONE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
        ("mesh.polygroups_smart_seams_generator_click",
         {"type": "LEFTMOUSE", "value": "PRESS"}, None),
    )
    draw_cursor = staticmethod(draw_smart_seam_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        settings = context.scene.polygroups_seam_preparation_settings
        layout.prop(settings, "smart_seam_pin_generated", text=t(context, "pin_generated"), toggle=True)
        _draw_seam_auto_uv_settings(context, layout)
        _draw_smart_auto_relax_settings(context, layout)
        layout.prop(settings, "smart_seam_angle_limit", text=t(context, "smart_seam_angle_limit"))
        layout.prop(settings, "smart_seam_filter_iterations")
        layout.prop(settings, "smart_seam_min_area")
        layout.prop(settings, "smart_seam_smoothness")
        layout.prop(settings, "smart_seam_path_turn")
        layout.prop(settings, "smart_seam_path_corridor")
        layout.prop(settings, "smart_seam_create_edges")
        if settings.smart_seam_create_edges:
            layout.prop(settings, "smart_seam_edge_preference")
        layout.prop(settings, "smart_seam_replace")


class VIEW3D_WST_polygroups_longitudinal_seam(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = LONGITUDINAL_SEAM_TOOL_ID
    bl_label = "Longitudinal Seam"
    bl_description = "Click a vertex to select its seam-bounded island and create a longitudinal seam"
    bl_icon = "ops.mesh.mark_seam"
    bl_cursor = "NONE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
        ("mesh.polygroups_longitudinal_seam_tool_click",
         {"type": "LEFTMOUSE", "value": "PRESS"}, None),
    )
    draw_cursor = staticmethod(draw_longitudinal_seam_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        settings = context.scene.polygroups_seam_finalization_settings
        layout.prop(settings, "pin_longitudinal_seam", text=t(context, "mark_as_pinned"), toggle=True)
        layout.prop(settings, "double_longitudinal_seam",
                    text=t(context, "double_longitudinal_seam"), toggle=True)
        layout.prop(settings, "prefer_backside_longitudinal_seam",
                    text=t(context, "prefer_backside_longitudinal_seam"), toggle=True)
        _draw_seam_auto_uv_settings(context, layout)


class VIEW3D_WST_polygroups_small_islands_merger(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = SMALL_ISLANDS_MERGER_TOOL_ID
    bl_label = "Small Islands Merger"
    bl_description = "Select seam islands with Box, Lasso, or Circle and merge small seams"
    bl_icon = "ops.generic.select_box"
    bl_cursor = "CROSSHAIR"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
        ("mesh.polygroups_small_islands_merger_gesture",
         {"type": "LEFTMOUSE", "value": "PRESS"}, None),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        props = tool.operator_properties("mesh.polygroups_small_islands_merger_gesture")
        settings = context.scene.polygroups_generator_settings
        layout.prop(settings, "small_islands_merger_shape", expand=True)
        if settings.small_islands_merger_shape == "CIRCLE":
            layout.prop(props, "radius")
        layout.prop(settings, "small_island_threshold", text=t(context, "small_islands_threshold"))
        layout.prop(settings, "small_island_protect_pinned", text=t(context, "small_islands_pinned"), toggle=True)
        layout.prop(settings, "small_island_protect_sharp", text=t(context, "small_islands_sharp"), toggle=True)
        layout.prop(settings, "small_island_protect_materials", text=t(context, "small_islands_materials"), toggle=True)


class VIEW3D_WST_polygroups_island_selector(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = ISLAND_SELECTOR_TOOL_ID
    bl_label = "Island Selector"
    bl_description = "Select complete UV islands; hold Shift to add islands to the current selection"
    bl_icon = "ops.generic.select"
    bl_cursor = "CROSSHAIR"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
        ("mesh.polygroups_island_selector_gesture",
         {"type": "LEFTMOUSE", "value": "PRESS", "shift": True}, None),
        ("mesh.polygroups_island_selector_gesture",
         {"type": "LEFTMOUSE", "value": "PRESS"}, None),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        props = tool.operator_properties("mesh.polygroups_island_selector_gesture")
        settings = context.scene.polygroups_generator_settings
        layout.prop(settings, "island_selector_shape", expand=True)
        layout.prop(settings, "island_selector_selection_mode", expand=True)
        if settings.island_selector_shape == "CIRCLE":
            layout.prop(props, "radius")
        layout.separator(type="LINE")
        layout.prop(settings, "small_island_threshold", text=t(context, "small_islands_threshold"))
        merge = layout.operator(
            "mesh.polygroups_merge_small_islands",
            text=t(context, "small_islands_merge"),
            icon="AUTOMERGE_ON",
        )
        merge.preview = False
        layout.operator(
            "mesh.polygroups_clear_inside_edges_seam",
            text=t(context, "clear_inside_edges_seam"),
            icon="X",
        )
        layout.label(text="Shift + LMB: Add linked island")


class VIEW3D_WST_polygroups_edge_merger(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = EDGE_MERGER_TOOL_ID
    bl_label = "Edge Merger"
    bl_description = "Click one edge to merge its vertices at the center"
    bl_icon = "ops.mesh.bisect"
    bl_cursor = "DEFAULT"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
        ("mesh.polygroups_edge_merger_click",
         {"type": "LEFTMOUSE", "value": "PRESS"}, None),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        # WorkSpaceTool has no activation callback. Its settings are drawn as
        # soon as the tool becomes active, so keep edge selection enforced here
        # as well as in the click operator.
        if context.mode == "EDIT_MESH":
            context.tool_settings.mesh_select_mode = (False, True, False)


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
        ("wm.tool_set_by_id", {"type": "RIGHTMOUSE", "value": "PRESS"},
         {"properties": [("name", "builtin.select_box")]}),
        ("mesh.polygroups_seam_eraser", {"type": "LEFTMOUSE", "value": "PRESS"}, None),
        ("mesh.polygroups_seam_eraser_resize", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True}, None),
        ("mesh.polygroups_seam_eraser_resize", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True}, None),
    )
    draw_cursor = staticmethod(draw_eraser_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        props = tool.operator_properties("mesh.polygroups_seam_eraser")
        layout.prop(context.scene.polygroups_seam_preparation_settings, "seam_eraser_clear_mode", expand=True)
        layout.prop(props, "shape", expand=True)
        if props.shape == "CIRCLE":
            layout.prop(props, "radius")
        _draw_seam_auto_uv_settings(context, layout)


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
        ("mesh.polygroups_seam_cursor_modifier", {"type": "MOUSEMOVE", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "LEFT_CTRL", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "RIGHT_CTRL", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_seam_cursor_modifier", {"type": "WINDOW_DEACTIVATE", "value": "ANY", "any": True}, None),
        ("mesh.polygroups_edge_seam_eraser_click", {"type": "RIGHTMOUSE", "value": "PRESS"}, {"properties": [("reset", True)]}),
        ("mesh.polygroups_edge_seam_eraser_click", {"type": "ESC", "value": "PRESS"}, {"properties": [("reset", True)]}),
        ("mesh.polygroups_edge_seam_eraser_click", {"type": "SPACE", "value": "PRESS"}, {"properties": [("reset", True)]}),
    )
    draw_cursor = staticmethod(draw_edge_seam_eraser_cursor)

    @staticmethod
    def draw_settings(context, layout, tool):
        layout.prop(context.scene.polygroups_seam_preparation_settings, "seam_eraser_clear_mode", expand=True)
        _draw_seam_auto_uv_settings(context, layout)
        layout.label(text=t(context, "seam_erase_path_hint"))


def draw_seam_status(self, context):
    if context.mode != "EDIT_MESH":
        return
    tool = context.workspace.tools.from_space_view3d_mode("EDIT_MESH", create=False)
    if tool is not None and tool.idname in {AREA_TOOL_ID, PATH_TOOL_ID}:
        self.layout.label(text=t(context, "seam_erase_drag_hint" if tool.idname == AREA_TOOL_ID else "seam_erase_path_hint"))
    elif tool is not None and tool.idname == SMART_SEAMS_TOOL_ID:
        self.layout.label(text="LMB: select seam island and generate smart seams")
    elif tool is not None and tool.idname == LONGITUDINAL_SEAM_TOOL_ID:
        self.layout.label(text="LMB: select seam island and create a longitudinal seam")
    elif tool is not None and tool.idname == SMALL_ISLANDS_MERGER_TOOL_ID:
        self.layout.label(text="LMB drag: select seam islands and merge small seams")
    elif tool is not None and tool.idname == ISLAND_SELECTOR_TOOL_ID:
        self.layout.label(text="LMB: select complete UV islands")
    elif tool is not None and tool.idname == EDGE_MERGER_TOOL_ID:
        self.layout.label(text="LMB: merge edge at center")
    elif tool is not None and tool.idname == EDGE_SEAM_TOOL_ID:
        self.layout.label(text="Ctrl+LMB: mark path   Ctrl+Shift+LMB: erase path")
    elif tool is not None and tool.idname == VERTEX_SEAM_TOOL_ID:
        self.layout.label(text=t(context, "seam_ctrl_status"))


def register():
    register_hover_cache()
    VIEW3D_WST_polygroups_draw_cutter_plane.bl_icon = tool_icon("draw_cutter_plane", "ops.mesh.primitive_grid_add_gizmo")
    VIEW3D_WST_polygroups_draw_cutter_grid.bl_icon = tool_icon("draw_cutter_grid", "ops.mesh.primitive_cube_add_gizmo")
    VIEW3D_WST_polygroups_draw_cutter_arc.bl_icon = tool_icon("draw_cutter_arc", "ops.gpencil.primitive_arc")
    VIEW3D_WST_polygroups_draw_cutter_local_ring.bl_icon = tool_icon("draw_cutter_local_ring", "ops.mesh.primitive_cylinder_add_gizmo")
    VIEW3D_WST_polygroups_draw_cutter_local_contour.bl_icon = tool_icon("draw_cutter_local_contour", "ops.mesh.primitive_cylinder_add_gizmo")
    VIEW3D_WST_polygroups_draw_cutter_path.bl_icon = tool_icon("draw_cutter_path", "ops.curve.draw")
    VIEW3D_WST_polygroups_draw_cutter_draw.bl_icon = tool_icon("draw_cutter_draw", "ops.curve.draw")
    VIEW3D_WST_polygroups_knife_seam.bl_icon = tool_icon("knife_seam", "ops.mesh.knife_tool")
    VIEW3D_WST_polygroups_quick_knife_seam.bl_icon = tool_icon("quick_knife_seam", "ops.mesh.bisect")
    VIEW3D_WST_polygroups_connect_vertex_seam.bl_icon = tool_icon("connect_vertex_seam", "ops.mesh.dupli_extrude_cursor")
    VIEW3D_WST_polygroups_edge_seam_path.bl_icon = tool_icon("edge_seam_path", "ops.mesh.dupli_extrude_cursor")
    VIEW3D_WST_polygroups_smart_seams_generator.bl_icon = tool_icon("smart_seams_generator", "ops.mesh.mark_seam")
    VIEW3D_WST_polygroups_longitudinal_seam.bl_icon = tool_icon("longitudinal_seam", "ops.mesh.mark_seam")
    VIEW3D_WST_polygroups_small_islands_merger.bl_icon = "ops.generic.select_box"
    VIEW3D_WST_polygroups_island_selector.bl_icon = "ops.generic.select"
    VIEW3D_WST_polygroups_edge_merger.bl_icon = "ops.mesh.bisect"
    VIEW3D_WST_polygroups_seam_eraser.bl_icon = tool_icon("seam_eraser", "ops.generic.select_circle")
    VIEW3D_WST_polygroups_edge_seam_eraser.bl_icon = tool_icon("edge_seam_eraser", "ops.mesh.dupli_extrude_cursor")
    bpy.types.STATUSBAR_HT_header.prepend(draw_seam_status)
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
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_smart_seams_generator,
        after={EDGE_SEAM_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_longitudinal_seam,
        after={SMART_SEAMS_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_island_selector,
        after={LONGITUDINAL_SEAM_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_small_islands_merger,
        after={ISLAND_SELECTOR_TOOL_ID},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_edge_merger,
        after={SMALL_ISLANDS_MERGER_TOOL_ID},
        separator=False,
        group=False,
    )

    bpy.utils.register_tool(VIEW3D_WST_polygroups_seam_eraser, after={EDGE_MERGER_TOOL_ID}, separator=True)
    bpy.utils.register_tool(VIEW3D_WST_polygroups_edge_seam_eraser, after={AREA_TOOL_ID})
    scene = getattr(bpy.context, "scene", None)
    if scene is not None:
        update_dynamic_seam_tool_icons(scene.polygroups_seam_preparation_settings, bpy.context)
        update_small_islands_merger_tool_icon(scene.polygroups_generator_settings, bpy.context)
        update_island_selector_tool_icon(scene.polygroups_generator_settings, bpy.context)

def unregister():
    unregister_hover_cache()
    stop_erasers()
    bpy.types.STATUSBAR_HT_header.remove(draw_seam_status)
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
                if tool is not None and tool.idname in {VERTEX_SEAM_TOOL_ID, EDGE_SEAM_TOOL_ID, SMART_SEAMS_TOOL_ID, LONGITUDINAL_SEAM_TOOL_ID, SMALL_ISLANDS_MERGER_TOOL_ID, ISLAND_SELECTOR_TOOL_ID, EDGE_MERGER_TOOL_ID, AREA_TOOL_ID, PATH_TOOL_ID}:
                    bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_edge_seam_eraser)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_seam_eraser)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_edge_merger)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_small_islands_merger)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_island_selector)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_longitudinal_seam)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_smart_seams_generator)
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
    _cursor_ctrl.clear()
    _cursor_erase.clear()
