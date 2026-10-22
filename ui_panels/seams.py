"""Seams section panels."""
from ..custom_icons import icon_kwargs
import bpy
from ..localization import t
from .common import (
    draw_collapsible_box,
    draw_enum_icon_toggle,
    draw_material_mode_buttons,
    draw_mesh_editing,
    draw_overlay_polygon_limit_status,
    draw_seam_gap_controls,
    draw_section_header_icon,
    draw_topic,
    section_content_visible,
)


class VIEW3D_PT_polygroups_seam_preparation(bpy.types.Panel):
    bl_label = "04 |"
    bl_text_key = "section_seam_preparation"
    bl_icon = "EDGE_SEAM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 4
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        seam_settings = context.scene.polygroups_seam_preparation_settings

        layout.prop(
            seam_settings,
            "show_seams_object_mode",
            text=t(context, "show_seams_object_mode"),
            toggle=True,
            icon="EDGE_SEAM",
        )
        if seam_settings.show_seams_object_mode:
            layout.prop(
                seam_settings,
                "seam_overlay_max_polygons",
                text=t(context, "seam_overlay_max_polygons"),
            )
            draw_overlay_polygon_limit_status(
                layout,
                context,
                seam_settings.seam_overlay_max_polygons,
                "seam_overlay_skipped",
            )

        content = draw_topic(layout, context, "seam_prep_0", "seam_group_selection", "FACESEL")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.prop(seam_settings, "prefer_linked_seam", text=t(context, "prefer_linked_seam"))
            selection_row = tools_column.row(align=True)
            selection_row.operator("mesh.select_more", text=t(context, "select_more"), icon="ADD")
            selection_row.operator("mesh.select_less", text=t(context, "select_less"), icon="REMOVE")
            linked_operator = tools_column.operator(
                "mesh.select_linked", text=t(context, "select_linked_seam"), icon="LINKED",
            )
            linked_operator.delimit = {"SEAM"}
            tools_column.separator()
            tools_column.prop(
                seam_settings,
                "selection_smooth_iterations",
                text=t(context, "smooth_iterations"),
            )

            smooth_operator = tools_column.operator(
                "mesh.polygroups_smooth_face_selection",
                text=t(context, "smooth_face_selection"),
                icon="MOD_SMOOTH",
            )
            smooth_operator.iterations = seam_settings.selection_smooth_iterations

        content = draw_topic(layout, context, "seam_prep_1", "model_preparation_group_mesh_edit", "EDITMODE_HLT")
        if content is not None:
            draw_mesh_editing(content, context, "seam_prep_1")

        content = draw_topic(layout, context, "seam_prep_2", "seam_group_mark_clear", "EDGE_SEAM")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.operator(
                "mesh.polygroups_mark_selected_edges_seam",
                text=t(context, "mark_selected_edges_seam"),
                icon="EDGESEL",
            )
            tools_column.operator(
                "mesh.polygroups_mark_selection_boundary_seam",
                text=t(context, "mark_selection_boundary_seam"),
                icon="EDGESEL",
            )
            tools_column.operator(
                "mesh.polygroups_clear_selected_edges_seam",
                text=t(context, "clear_selected_edges_seam"),
                icon="X",
            )
            tools_column.operator(
                "mesh.polygroups_clear_inside_edges_seam",
                text=t(context, "clear_inside_edges_seam"),
                icon="X",
            )

            tools_column.operator(
                "mesh.polygroups_edge_seam_path",
                text=t(context, "connect_vertices_edge_seam_path"),
                **icon_kwargs("edge_seam_path_pin" if seam_settings.seam_path_pin else "edge_seam_path", "EDGE_SEAM"),
            )

            tools_column.separator()
            tools_column.label(text=t(context, "pin_edges"))
            pin_row = tools_column.row(align=True)
            pin_row.operator("mesh.polygroups_pin_selected_seams", text=t(context, "pin_selected_seams"), **icon_kwargs("pin_vertices", "PINNED"))
            pin_row.operator("mesh.polygroups_unpin_selected_edges", text=t(context, "unpin_selected"), **icon_kwargs("unpin_vertices", "UNPINNED"))
            tools_column.operator("mesh.polygroups_clear_all_pins", text=t(context, "clear_all_pins"), **icon_kwargs("unpin_vertices", "X"))
            tools_column.prop(seam_settings, "seam_path_pin", text=t(context, "mark_as_pinned"))

        content = draw_topic(layout, context, "seam_prep_3", "seam_group_smart_mark", "EDGE_SEAM")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.prop(seam_settings, "smart_seam_angle_limit", text=t(context, "smart_seam_angle_limit"))
            tools_column.prop(seam_settings, "smart_seam_filter_iterations")
            tools_column.prop(seam_settings, "smart_seam_min_area")
            tools_column.prop(seam_settings, "smart_seam_smoothness")
            tools_column.prop(seam_settings, "smart_seam_replace")
            tools_column.prop(seam_settings, "smart_seam_pin_generated", text=t(context, "pin_generated"))
            tools_column.prop(seam_settings, "smart_seam_create_edges")
            if seam_settings.smart_seam_create_edges:
                tools_column.prop(seam_settings, "smart_seam_edge_preference")
            tools_column.prop(
                seam_settings, "smart_seam_auto_relax",
                text=t(context, "smart_seam_auto_relax"), toggle=True,
            )
            if seam_settings.smart_seam_auto_relax:
                tools_column.prop(
                    seam_settings, "seam_relax_iterations",
                    text=t(context, "seam_relax_iterations"),
                )
                tools_column.label(
                    text=t(context, "seam_relax_selected_area_only"),
                    icon="CHECKBOX_HLT",
                )
                corner_row = tools_column.row(align=True)
                corner_row.prop(
                    seam_settings, "seam_relax_use_corner_angle",
                    text=t(context, "seam_relax_use_corner_angle"), toggle=True,
                )
                corner_angle = corner_row.row(align=True)
                corner_angle.enabled = seam_settings.seam_relax_use_corner_angle
                corner_angle.prop(seam_settings, "seam_relax_corner_angle", text="")
                tools_column.prop(
                    seam_settings, "seam_relax_protection_radius",
                    text=t(context, "seam_relax_protection_radius"),
                )
            tools_column.prop(seam_settings, "smart_seam_path_turn")
            tools_column.prop(seam_settings, "smart_seam_path_corridor")
            tools_column.operator(
                "mesh.polygroups_mark_smart_angle_seams",
                text=t(context, "mark_smart_angle_seams"),
                **icon_kwargs("smart_seams_generator_pin" if seam_settings.smart_seam_pin_generated else "smart_seams_generator", "UV"),
            )

        settings = context.scene.polygroups_generator_settings
        content = draw_topic(layout, context, "seam_prep_4", "small_islands_group", "EDGE_SEAM")
        if content is not None:
            content.prop(settings, "small_island_threshold", text=t(context, "small_islands_threshold"))
            content.prop(settings, "small_island_selected_area", text=t(context, "small_islands_selected"))
            content.prop(settings, "small_island_protect_pinned", text=t(context, "small_islands_pinned"))
            content.prop(settings, "small_island_protect_sharp", text=t(context, "small_islands_sharp"))
            content.prop(settings, "small_island_protect_materials", text=t(context, "small_islands_materials"))
            row = content.row(align=True)
            row.operator("mesh.polygroups_merge_small_islands", text=t(context, "small_islands_preview"), icon="VIEWZOOM").preview = True
            row.operator(
                "mesh.polygroups_analyze_and_merge_seams",
                text=t(context, "small_islands_analyze_merge"),
                icon="AUTOMERGE_ON",
            )
            if settings.small_island_status:
                content.label(text=settings.small_island_status)

        content = draw_topic(layout, context, "seam_prep_5", "seam_group_mark_clear_tools", "TOOL_SETTINGS")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.prop(seam_settings, "seam_eraser_clear_mode", expand=True)
            edge_tool = tools_column.operator(
                "mesh.polygroups_select_seam_tool",
                text=t(context, "select_edge_seam_tool"),
                **icon_kwargs("edge_seam_path_pin" if seam_settings.seam_path_pin else "edge_seam_path", "VERTEXSEL"),
            )
            edge_tool.tool_id = "polygroups_generator.edge_seam_path_tool"
            for key, tool_id in (("seam_eraser", "polygroups_generator.seam_eraser_tool"),
                                 ("edge_seam_eraser", "polygroups_generator.edge_seam_eraser_tool")):
                icon_key = key + ("_pin" if seam_settings.seam_eraser_clear_mode == "PINNED" else "")
                button = tools_column.operator("mesh.polygroups_select_seam_tool", text=t(context, key), **icon_kwargs(icon_key, "X"))
                button.tool_id = tool_id

        content = draw_topic(layout, context, "seam_prep_6", "seam_group_check", "VIEWZOOM")
        if content is not None:
            draw_seam_gap_controls(content, context, seam_settings)
            content.separator(type="LINE")
            relax_column = content.column(align=True)
            relax_column.label(text=t(context, "seam_relax"), icon="MOD_SMOOTH")
            relax_column.prop(
                seam_settings, "seam_relax_mode",
                text=t(context, "seam_relax_mode"), expand=True,
            )
            relax_column.prop(
                seam_settings, "seam_relax_iterations",
                text=t(context, "seam_relax_iterations"),
            )
            relax_column.prop(
                seam_settings, "seam_relax_selected_area_only",
                text=t(context, "seam_relax_selected_area_only"), toggle=True,
            )
            if seam_settings.seam_relax_mode == "SMART":
                corner_row = relax_column.row(align=True)
                corner_row.prop(
                    seam_settings, "seam_relax_use_corner_angle",
                    text=t(context, "seam_relax_use_corner_angle"), toggle=True,
                )
                corner_angle = corner_row.row(align=True)
                corner_angle.enabled = seam_settings.seam_relax_use_corner_angle
                corner_angle.prop(seam_settings, "seam_relax_corner_angle", text="")
                relax_column.prop(
                    seam_settings, "seam_relax_protection_radius",
                    text=t(context, "seam_relax_protection_radius"),
                )
            relax_column.operator(
                "mesh.polygroups_relax_seams",
                text=t(context, "seam_relax"), icon="MOD_SMOOTH",
            )
            relax_column.operator(
                "mesh.polygroups_relax_seams",
                text=t(context, "smart_relax_selected_seams"), icon="MOD_SMOOTH",
            ).selected_seams_only = True

        content = draw_topic(layout, context, "seam_prep_7", "seam_group_cut", "MOD_BEVEL")
        if content is not None:
            connect_column = content.column(align=True)
            connect_column.prop(seam_settings, "seam_path_pin", text=t(context, "mark_as_pinned"))
            connect_column.operator(
                "mesh.polygroups_connect_vertex_seam",
                text=t(context, "connect_vertices_seam"),
                icon="EDGE_SEAM",
            )
            connect_tool = connect_column.operator(
                "mesh.polygroups_select_seam_tool",
                text=t(context, "select_vertex_seam_tool"),
                **icon_kwargs("connect_vertex_seam_pin" if seam_settings.seam_path_pin else "connect_vertex_seam", "VERTEXSEL"),
            )
            connect_tool.tool_id = "polygroups_generator.connect_vertex_seam_tool"
            knife_content = draw_collapsible_box(
                content,
                seam_settings,
                "show_knife_seam_settings",
                t(context, "knife_seam"),
                "MOD_BEVEL",
            )
            if knife_content is not None:
                self.draw_knife_seam(context, knife_content)

            quick_knife_content = draw_collapsible_box(
                content,
                seam_settings,
                "show_quick_knife_seam_settings",
                t(context, "quick_knife_seam"),
                "MOD_BEVEL",
            )
            if quick_knife_content is not None:
                self.draw_quick_knife_seam(context, quick_knife_content)

            object_cutter_content = draw_collapsible_box(
                content,
                seam_settings,
                "show_object_seam_cutter_settings",
                t(context, "object_seam_cutter"),
                "MESH_PLANE",
            )
            if object_cutter_content is not None:
                self.draw_object_seam_cutter(context, object_cutter_content)

    def draw_knife_seam(self, context, layout):
        settings = context.scene.polygroups_knife_seam_settings

        layout.prop(settings, "cut_mode", text=t(context, "knife_cut_mode"))
        if settings.cut_mode == "POLYLINE":
            layout.label(text=t(context, "knife_polyline_hint"), icon="INFO")
        layout.prop(settings, "xray", text=t(context, "xray"))
        layout.prop(settings, "use_occlude_geometry", text=t(context, "occlude_geometry"))
        layout.prop(settings, "only_selected", text=t(context, "only_selected"))
        layout.prop(settings, "mark_seam", text=t(context, "mark_as_seam"))
        layout.prop(
            settings,
            "clear_selection_after_cutting",
            text=t(context, "clear_selection_after_cutting"),
        )

        tool_operator = layout.operator(
            "mesh.polygroups_select_seam_tool",
            text=t(context, "select_knife_tool"),
            **icon_kwargs("knife_seam", "SCULPTMODE_HLT"),
        )
        tool_operator.tool_id = "polygroups_generator.knife_seam_tool"

    def draw_quick_knife_seam(self, context, layout):
        quick_settings = context.scene.polygroups_quick_knife_seam_settings

        layout.prop(quick_settings, "use_fill", text=t(context, "fill"))
        layout.prop(quick_settings, "threshold", text=t(context, "threshold"))
        layout.prop(quick_settings, "mark_seam", text=t(context, "mark_as_seam"))
        layout.prop(
            quick_settings,
            "clear_selection_after_cutting",
            text=t(context, "clear_selection_after_cutting"),
        )

        tool_operator = layout.operator(
            "mesh.polygroups_select_seam_tool",
            text=t(context, "select_quick_knife_tool"),
            **icon_kwargs("quick_knife_seam", "MOD_BEVEL"),
        )
        tool_operator.tool_id = "polygroups_generator.quick_knife_seam_tool"

    def draw_object_seam_cutter(self, context, layout):
        settings = context.scene.polygroups_object_seam_cutter_settings

        layout.prop(settings, "cutter_size_multiplier", text=t(context, "cutter_size"))
        layout.prop(settings, "cutter_arc_segments", text=t(context, "cylinder_segments"))
        layout.prop(settings, "cutter_local_ring_fit_mode", text=t(context, "local_ring_fit_mode"))
        layout.prop(settings, "cutter_local_ring_segments", text=t(context, "local_ring_segments"))
        layout.prop(settings, "cutter_local_ring_radius_offset", text=t(context, "local_ring_radius_offset"))
        layout.prop(settings, "cutter_contour_points", text=t(context, "contour_points"))
        layout.prop(settings, "cutter_contour_offset", text=t(context, "contour_offset"))
        layout.label(text=t(context, "cutter_apply_method"))
        draw_enum_icon_toggle(
            layout,
            "scene.polygroups_object_seam_cutter_settings",
            settings,
            "cutter_apply_method",
            (
                ("BOOLEAN", "Boolean", "MOD_BOOLEAN"),
                ("KNIFE", "Knife", "EDGESEL"),
            ),
        )
        layout.label(text=t(context, "cutter_boolean_solver"))
        draw_enum_icon_toggle(
            layout,
            "scene.polygroups_object_seam_cutter_settings",
            settings,
            "cutter_boolean_solver",
            (
                ("FLOAT", "Float", "VIEWZOOM"),
                ("EXACT", "Exact", "CHECKMARK"),
            ),
        )
        autofix_row = layout.row(align=True)
        autofix_row.prop(
            settings,
            "cutter_auto_fix_mesh",
            text=t(context, "cutter_auto_fix_mesh"),
            toggle=True,
        )
        fin_toggle = autofix_row.row(align=True)
        fin_toggle.enabled = settings.cutter_auto_fix_mesh
        fin_toggle.prop(
            settings,
            "cutter_auto_fix_fin_faces",
            text="",
            icon="FACESEL",
            toggle=True,
        )
        seam_toggle = autofix_row.row(align=True)
        seam_toggle.enabled = settings.cutter_auto_fix_mesh
        seam_toggle.prop(
            settings,
            "cutter_auto_fix_seam_check",
            text="",
            icon="VIEWZOOM",
            toggle=True,
        )
        islands_toggle = autofix_row.row(align=True)
        islands_toggle.enabled = settings.cutter_auto_fix_mesh
        islands_toggle.prop(
            settings,
            "cutter_auto_fix_small_islands",
            text="",
            icon="AUTOMERGE_ON",
            toggle=True,
        )
        islands_threshold = autofix_row.row(align=True)
        islands_threshold.enabled = (
            settings.cutter_auto_fix_mesh and settings.cutter_auto_fix_small_islands
        )
        islands_threshold.prop(
            settings,
            "cutter_auto_fix_small_islands_threshold",
            text="Threshold",
        )
        weld_toggle = autofix_row.row(align=True)
        weld_toggle.enabled = settings.cutter_auto_fix_mesh
        weld_toggle.prop(
            settings,
            "cutter_auto_fix_weld",
            text="",
            icon="AUTOMERGE_ON",
            toggle=True,
        )
        weld_distance = autofix_row.row(align=True)
        weld_distance.enabled = settings.cutter_auto_fix_mesh and settings.cutter_auto_fix_weld
        weld_distance.prop(
            settings,
            "cutter_auto_fix_weld_distance",
            text="Weld",
        )
        relax_toggle = autofix_row.row(align=True)
        relax_toggle.enabled = settings.cutter_auto_fix_mesh
        relax_toggle.prop(
            settings,
            "cutter_auto_fix_smart_relax_seams",
            text="",
            icon="MOD_SMOOTH",
            toggle=True,
        )
        triangulate_toggle = autofix_row.row(align=True)
        triangulate_toggle.enabled = settings.cutter_auto_fix_mesh
        triangulate_toggle.prop(
            settings,
            "cutter_auto_fix_triangulate_ngons",
            text="",
            icon="MOD_TRIANGULATE",
            toggle=True,
        )
        status_box = layout.box()
        status_box.label(text="Apply Cutter Seams Status", icon="MOD_BOOLEAN")
        if settings.cutter_apply_stage:
            status_box.label(text=settings.cutter_apply_message)
            status_box.progress(
                factor=settings.cutter_apply_progress / 100,
                type="BAR",
                text=f"{settings.cutter_apply_progress:.0f}%",
            )
            if settings.cutter_apply_is_running:
                status_box.label(text="Press Esc to cancel", icon="INFO")
        else:
            status_box.label(text="Ready")
        layout.prop(settings, "cutter_alpha", text=t(context, "cutter_alpha"))
        layout.prop(settings, "cutter_solidify_thickness", text=t(context, "plane_thickness"))
        layout.prop(settings, "cutter_thickness", text=t(context, "cutter_thickness"))
        layout.prop(settings, "cutter_extrude", text=t(context, "cutter_extrude"))
        layout.prop(settings, "cutter_path_render_u", text=t(context, "path_render_u"))
        tilt_row = layout.row(align=True)
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_minus"))
        tilt_operator.mode = "DECREASE"
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_plus"))
        tilt_operator.mode = "INCREASE"
        curve_row = layout.row(align=True)
        curve_row.operator("object.polygroups_bezier_cutter_paths", text=t(context, "curve_bezier"))
        curve_row.operator("object.polygroups_toggle_cyclic_cutter_paths", text=t(context, "curve_cyclic"))
        curve_row.operator("object.polygroups_smooth_cutter_paths", text=t(context, "curve_smooth"))
        curve_row.operator("object.polygroups_smooth_cutter_path_tilt", text=t(context, "curve_smooth_tilt"))
        layout.prop(settings, "continue_path_cutters", text=t(context, "continue_path_cutters"))
        layout.prop(settings, "cutter_path_join_distance", text=t(context, "path_join_distance"))
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
        layout.prop(settings, "continue_draw_strokes", text=t(context, "continue_draw_strokes"))
        layout.prop(settings, "cutter_draw_join_distance", text=t(context, "draw_join_distance"))
        layout.prop(settings, "auto_convert_draw_strokes", text=t(context, "auto_convert_draw_strokes"))
        layout.prop(
            settings,
            "auto_convert_draw_strokes_on_apply",
            text=t(context, "auto_convert_draw_strokes_on_apply"),
        )
        layout.prop(
            settings,
            "delete_draw_strokes_after_convert",
            text=t(context, "delete_draw_strokes_after_convert"),
        )
        layout.prop(
            settings,
            "hide_cutters_after_apply",
            text=t(context, "hide_cutters_after_apply"),
        )
        layout.prop(
            settings,
            "delete_cutters_after_apply",
            text=t(context, "delete_cutters_after_apply"),
        )
        layout.label(text=t(context, "ctrl_draw_hint"), icon="MOUSE_LMB")
        layout.prop(settings, "cutter_mirror_axis", text=t(context, "mirror_axis"), expand=True)
        layout.operator(
            "object.polygroups_copy_mirror_cutters",
            text=t(context, "copy_mirror_cutters"),
            icon="MOD_MIRROR",
        )
        layout.separator()
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_plane"),
            **icon_kwargs("draw_cutter_plane", "MESH_PLANE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_plane_tool"
        layout.operator(
            "object.polygroups_draw_cutter_plane",
            text=t(context, "draw_cutter_plane"),
            **icon_kwargs("draw_cutter_plane", "MESH_PLANE"),
        )
        grid_box = layout.box()
        grid_box.label(text=t(context, "draw_cutter_grid"), **icon_kwargs("draw_cutter_grid", "MESH_CUBE"))
        from ..tools import draw_grid_settings
        draw_grid_settings(context, grid_box)
        grid_box.operator("wm.tool_set_by_id", text=t(context, "select_draw_cutter_grid"),
                          **icon_kwargs("draw_cutter_grid", "MESH_CUBE")).name = "polygroups_generator.draw_cutter_grid_tool"
        grid_box.operator("object.polygroups_draw_cutter_grid", text=t(context, "draw_cutter_grid"), **icon_kwargs("draw_cutter_grid", "MESH_CUBE"))
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_arc"),
            **icon_kwargs("draw_cutter_arc", "CURVE_BEZCURVE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_arc_tool"
        layout.operator(
            "object.polygroups_draw_cutter_arc",
            text=t(context, "draw_cutter_arc"),
            **icon_kwargs("draw_cutter_arc", "CURVE_BEZCURVE"),
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_local_ring"),
            **icon_kwargs("draw_cutter_local_ring", "MESH_CIRCLE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_local_ring_tool"
        layout.operator(
            "object.polygroups_draw_cutter_local_ring",
            text=t(context, "draw_cutter_local_ring"),
            **icon_kwargs("draw_cutter_local_ring", "MESH_CIRCLE"),
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_local_contour"),
            **icon_kwargs("draw_cutter_local_contour", "MESH_CIRCLE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_local_contour_tool"
        layout.operator(
            "object.polygroups_local_contour_gesture",
            text=t(context, "draw_cutter_local_contour"),
            **icon_kwargs("draw_cutter_local_contour", "MESH_CIRCLE"),
        )
        layout.operator("object.polygroups_finalize_local_contour", text=t(context, "finalize_local_contour"), icon="CHECKMARK")
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_path"),
            **icon_kwargs("draw_cutter_path", "CURVE_PATH"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_path_tool"
        layout.operator(
            "object.polygroups_draw_cutter_path",
            text=t(context, "draw_cutter_path"),
            **icon_kwargs("draw_cutter_path", "CURVE_PATH"),
        )
        layout.operator(
            "object.polygroups_join_cutter_paths",
            text=t(context, "join_cutter_paths"),
            icon="AUTOMERGE_ON",
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_draw"),
            **icon_kwargs("draw_cutter_draw", "GREASEPENCIL"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_draw_tool"
        layout.operator(
            "object.polygroups_draw_cutter_draw",
            text=t(context, "draw_cutter_draw"),
            **icon_kwargs("draw_cutter_draw", "GREASEPENCIL"),
        )
        layout.operator(
            "object.polygroups_join_draw_strokes",
            text=t(context, "join_draw_strokes"),
            icon="AUTOMERGE_ON",
        )
        layout.operator(
            "object.polygroups_convert_draw_strokes_to_cutter_paths",
            text=t(context, "convert_draw_strokes_to_cutter_paths"),
            icon="CURVE_PATH",
        )
        tilt_row = layout.row(align=True)
        tilt_operator = tilt_row.operator(
            "object.polygroups_tilt_cutter_path",
            text=t(context, "tilt_minus"),
        )
        tilt_operator.mode = "DECREASE"
        tilt_operator = tilt_row.operator(
            "object.polygroups_tilt_cutter_path",
            text=t(context, "tilt_plus"),
        )
        tilt_operator.mode = "INCREASE"
        curve_row = layout.row(align=True)
        curve_row.operator("object.polygroups_bezier_cutter_paths", text=t(context, "curve_bezier"))
        curve_row.operator("object.polygroups_toggle_cyclic_cutter_paths", text=t(context, "curve_cyclic"))
        curve_row.operator("object.polygroups_smooth_cutter_paths", text=t(context, "curve_smooth"))
        curve_row.operator("object.polygroups_smooth_cutter_path_tilt", text=t(context, "curve_smooth_tilt"))
        apply_row = layout.row(align=True)
        apply_row.enabled = any(
            obj.type in {"MESH", "CURVE"}
            and obj.get("polygroups_object_seam_cutter")
            for obj in context.selected_objects
        ) and not settings.cutter_apply_is_running
        apply_row.operator(
            "object.polygroups_apply_cutter_seams",
            text=t(context, "apply_cutter_seams"),
            icon="MOD_BOOLEAN",
        )
        apply_row.operator(
            "object.polygroups_create_cutter_backup",
            text="",
            icon="DUPLICATE",
        )
        apply_row.operator(
            "object.polygroups_restore_cutter_backup",
            text="",
            icon="RECOVER_LAST",
        )
        layout.operator(
            "object.polygroups_restore_cutter_backup",
            text="Restore Backup",
            icon="RECOVER_LAST",
        )
        layout.operator(
            "object.polygroups_split_object_by_cutters",
            text=t(context, "split_object"),
            icon="MOD_EXPLODE",
        )

        utility_row = layout.row(align=True)
        utility_row.operator(
            "object.polygroups_select_cutter_planes",
            text=t(context, "select"),
            icon="RESTRICT_SELECT_OFF",
        )
        utility_row.operator(
            "object.polygroups_clear_cutter_planes",
            text=t(context, "clear"),
            icon="TRASH",
        )

        if settings.last_cutter_count or settings.last_marked_edge_count:
            layout.separator()
            layout.label(text=t(context, "last_cutters", value=settings.last_cutter_count))
            layout.label(text=t(context, "last_seam_edges", value=settings.last_marked_edge_count))


class VIEW3D_PT_polygroups_tools(bpy.types.Panel):
    bl_label = "05 |"
    bl_text_key = "section_polygroups"
    bl_icon = "MATERIAL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_order = 5
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_generator_settings
        content = draw_topic(layout, context, "polygroups_0", "generate_polygroups", "MATERIAL")
        if content is not None:
            column = content.column(align=True)
            draw_material_mode_buttons(column, context, settings)
            column.prop(settings, "checker_scale", text=t(context, "checker_scale"))
            column.separator()
            column.operator(
                "object.polygroups_checked_generate_polygroups",
                text=t(context, "generate_polygroups"),
                icon="MATERIAL",
            )
            column.operator(
                "object.polygroups_apply_material_mode",
                text=t(context, "apply_material_mode"),
                icon="NODE_MATERIAL",
            )
            column.operator(
                "object.polygroups_apply_checker_material",
                text=t(context, "apply_checker_material"),
                icon="TEXTURE",
            )

        content = draw_topic(layout, context, "polygroups_1", "small_islands_uv", "UV")
        if content is not None:
            column = content.column(align=True)
            column.operator(
                "mesh.polygroups_mark_material_boundaries_seam",
                text=t(context, "generate_seams_materials"),
                icon="EDGE_SEAM",
            )
            column.operator(
                "object.polygroups_unwrap_angle_based",
                text=t(context, "unwrap_angle_based"),
                icon="UV",
            )

        content = draw_topic(layout, context, "polygroups_2", "small_islands_manage", "MATERIAL")
        if content is not None:
            column = content.column(align=True)
            column.operator(
                "object.face_sets_to_materials",
                text=t(context, "face_sets_to_materials"),
                icon="SHADING_TEXTURE",
            )
            column.operator(
                "object.clear_polygroups_materials",
                text=t(context, "clear_polygroups_materials"),
                icon="TRASH",
            )
