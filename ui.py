from .ui_state import state
from .ui_panels.common import (
    _FilteredLayout,
    _NullLayout,
    _SearchProbeLayout,
    _SearchResult,
    _normalized_search_terms,
    _probe_panel,
    _search_text_matches,
    addon_version_string,
    collect_window_groups,
    draw_ai_input_image_controls,
    draw_batch_processing,
    draw_batch_stage_heading,
    draw_collapsible_box,
    draw_detached_group,
    draw_enum_icon_toggle,
    draw_fab_variant_visibility,
    draw_import_progress,
    draw_import_remesh_options,
    draw_material_mode_buttons,
    draw_mesh_editing,
    draw_optional_prop,
    draw_overlay_polygon_limit_status,
    draw_seam_gap_controls,
    draw_section_fold_actions,
    draw_section_header_icon,
    draw_section_panel_content,
    draw_session_subgroup,
    draw_studio_position,
    draw_topic,
    quad_remesher_status,
    section_content_visible,
    update_panel_labels,
    uvpackmaster_status,
)
from .ui_panels.preparation import (
    VIEW3D_PT_polygroups_model_preparation,
    VIEW3D_PT_polygroups_import,
    VIEW3D_PT_polygroups_batch_import,
    VIEW3D_PT_polygroups_remesh,
)
from .ui_panels.seams import (
    VIEW3D_PT_polygroups_seam_preparation,
    VIEW3D_PT_polygroups_tools,
)
from .ui_panels.baking import (
    VIEW3D_PT_polygroups_baking,
    VIEW3D_PT_polygroups_uv_preparation,
)
from .ui_panels.ai import (
    VIEW3D_PT_airetopo_ai_generation,
    VIEW3D_PT_polygroups_resculpting,
)
from .ui_panels.finalization import (
    VIEW3D_PT_polygroups_seam_finalization,
    VIEW3D_PT_polygroups_mesh_finalization,
)
from .ui_panels.render import (
    VIEW3D_PT_polygroups_render,
)

from .custom_icons import icon_kwargs
import os
import json
import sys
import time
from types import SimpleNamespace

import bpy

from .localization import get_preferences
from .localization import t
from .properties import SECTION_VISIBILITY_PROPERTIES
from .core.remesh_defaults import get_remesh_preset_counts
from .core.import_timing import format_duration


class VIEW3D_PT_polygroups_generator(bpy.types.Panel):
    bl_label = f"AI Retopo Toolkit v{addon_version_string()}"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_order = 0

    def draw(self, context):
        preferences = get_preferences(context)
        if not state.custom_capturing:
            self.layout.prop(preferences, 'ui_mode', expand=True) if preferences else None
            if preferences and preferences.ui_mode == 'CUSTOM':
                split = self.layout.split(factor=.12)
                rail = split.column(align=True)
                body = split.column()
                rail.operator('wm.airetopo_custom_section', text='', icon='FILE_REFRESH',
                    depress=preferences.custom_ui_show_session).section = 13
                for index, panel in enumerate(SECTION_PANEL_CLASSES):
                    item = rail.operator('wm.airetopo_custom_section', text='', icon=panel.bl_icon,
                        depress=not preferences.custom_ui_show_session and index == preferences.custom_ui_section)
                    item.section = index
                if preferences.custom_ui_show_session:
                    old_flags = state.custom_capturing, state.custom_header_only
                    state.custom_capturing, state.custom_header_only = True, True
                    try:
                        VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=body), context)
                    finally:
                        state.custom_capturing, state.custom_header_only = old_flags
                else:
                    panel, visibility_property = SECTION_PANEL_VISIBILITY[preferences.custom_ui_section]
                    heading = body.row(align=True)
                    heading.label(text=f'{panel.bl_order:02d} | {t(context, panel.bl_text_key)}', icon=panel.bl_icon)
                    draw_section_fold_actions(heading, visibility_property)
                    draw_section_panel_content(panel, context, body, '')
                return
        if not state.custom_capturing and preferences and preferences.ui_mode == 'UI_PANEL':
            self.layout.operator('wm.airetopo_custom_ui', text='Open UI Panel', icon='WINDOW')
            from .custom_ui.lifecycle import SESSIONS, key_for
            session = SESSIONS.get(key_for(context))
            if session:
                self.layout.operator('wm.airetopo_custom_placement',
                    text='Detach' if session.docked else 'Dock on Right', icon='WINDOW').placement = 'FLOATING' if session.docked else 'DOCKED'
                if session.docked:
                    # Reserve native UI content beneath Detach. Without a real
                    # block here Blender treats the GPU-only area as viewport,
                    # so the sidebar resize action-zone ends at the buttons.
                    ui_scale = context.preferences.system.ui_scale
                    reserve = self.layout.row()
                    reserve.scale_y = max(1, (context.region.height-160)/(20*ui_scale))
                    reserve.label(text=' ')
            return
        layout = self.layout
        visible_layout = layout
        visibility = context.scene.airetopo_panel_visibility_settings
        search_query = '' if state.custom_header_only else visibility.panel_search.strip()
        if search_query:
            # Filter workflow sections only. The session card stays above the
            # search results and keeps its own independent fold state.
            layout = _NullLayout()
        if preferences is not None:
            from .preferences import draw_global_notices

            draw_global_notices(layout, context, preferences)
        from . import custom_autosave

        session_box = visible_layout.box()
        session_expanded = bool(
            preferences is None or preferences.show_panel_session_status
        )
        session_header = session_box.row(align=True)
        if preferences is not None:
            session_header.prop(
                preferences,
                "show_panel_session_status",
                text=t(context, "panel_session_status"),
                icon="TRIA_DOWN" if session_expanded else "TRIA_RIGHT",
                emboss=False,
            )
        else:
            session_header.label(text=t(context, "panel_session_status"), icon="TRIA_DOWN")

        if session_expanded:
            save_status = custom_autosave.status_snapshot()
            save_group = draw_session_subgroup(session_box, context, preferences, 'show_panel_save_restart', 'save_and_restart_group', 'FILE_TICK')
            if save_group is not None:
                save_group.operator('wm.airetopo_relocate_project',
                    text=t(context, 'relocate_project'), icon='FILE_NEW')
                regular_row = save_group.row(align=True)
                regular_row.label(
                    text=t(context, "last_regular_save_time", value=save_status["regular_save_time"]),
                    icon="FILE_TICK",
                )
                regular_actions = regular_row.row(align=True)
                regular_actions.enabled = bool(save_status["regular_save_path"])
                open_regular = regular_actions.operator(
                    "wm.airetopo_open_saved_file",
                    text=t(context, "load_latest_save"),
                    icon="FILE_BLEND",
                )
                open_regular.filepath = save_status["regular_save_path"]
                show_regular = regular_actions.operator(
                    "wm.airetopo_show_file_in_browser",
                    text="",
                    icon="FILE_FOLDER",
                )
                show_regular.filepath = save_status["regular_save_path"]
                if preferences and preferences.enable_dev_mode:
                    save_group.separator()
                    restart_column = save_group.column(align=True)
                    restart_column.operator(
                        "wm.airetopo_dev_restart",
                        text=t(context, "dev_restart"),
                        icon="FILE_REFRESH",
                    )
                    restart_column.operator(
                        "wm.airetopo_dev_restart_current",
                        text=t(context, "dev_restart_current"),
                        icon="FILE_TICK",
                    )
                    restart_column.operator(
                        "wm.airetopo_dev_restart_without_saving",
                        text=t(context, "dev_restart_without_saving"),
                        icon="LOOP_BACK",
                    )

            autosave_group = draw_session_subgroup(session_box, context, preferences, 'show_panel_autosave', 'autosave_group', 'RECOVER_LAST')
            if autosave_group is not None:
                status_row = autosave_group.row(align=True)
                event = save_status["event"]
                if event == "CUSTOM":
                    status_row.label(text=t(context, "autosave_status_success"), icon="CHECKMARK")
                elif event == "REGULAR":
                    status_row.label(text=t(context, "regular_save_status_success"), icon="CHECKMARK")
                elif event == "ERROR":
                    status_row.alert = True
                    status_row.label(text=t(context, "autosave_status_error"), icon="ERROR")
                elif event == "RECOVERY":
                    status_row.label(text=t(context, "autosave_recovery_created"), icon="RECOVER_LAST")
                else:
                    status_row.label(text=t(context, "save_status_waiting"), icon="TIME")
                autosave_row = autosave_group.row(align=True)
                autosave_row.label(
                    text=t(context, "last_autosave_time", value=save_status["autosave_time"]),
                    icon="RECOVER_LAST",
                )
                autosave_actions = autosave_row.row(align=True)
                autosave_actions.enabled = bool(save_status["autosave_path"])
                open_autosave = autosave_actions.operator(
                    "wm.airetopo_open_recent_autosave",
                    text=t(context, "load_latest_autosave"),
                    icon="FILE_REFRESH",
                )
                open_autosave.filepath = save_status["autosave_path"]
                show_autosave = autosave_actions.operator(
                    "wm.airetopo_show_file_in_browser",
                    text="",
                    icon="FILE_FOLDER",
                )
                show_autosave.filepath = save_status["autosave_path"]

                recovery = custom_autosave.recovery_snapshot()
                if recovery["active"]:
                    autosave_group.separator()
                    recovery_box = autosave_group.box()
                    recovery_box.label(
                        text=t(context, "recovered_file", value=os.path.basename(recovery["restored"])),
                        icon="FILE_BLEND",
                    )
                    if recovery["original"]:
                        recovery_box.label(
                            text=t(context, "original_file", value=os.path.basename(recovery["original"])),
                            icon="FILE_TICK",
                        )
                        save_original = recovery_box.row(align=True)
                        save_original.alert = True
                        save_original.operator(
                            "wm.airetopo_save_recovery_to_original",
                            text=t(context, "save_recovery_to_original"),
                            icon="FILE_TICK",
                        )
                        recovery_box.label(text=t(context, "save_recovery_warning"), icon="ERROR")
                    else:
                        recovery_box.operator(
                            "wm.save_as_mainfile",
                            text=t(context, "save_recovery_as"),
                            icon="FILE_NEW",
                        )
                if not getattr(bpy.data, "filepath", ""):
                    autosave_group.separator()
                    recent_box = autosave_group.box()
                    recent_expanded = bool(
                        preferences is None or preferences.show_panel_recent_autosaves
                    )
                    recent_header = recent_box.row(align=True)
                    if preferences is not None:
                        recent_header.prop(
                            preferences,
                            "show_panel_recent_autosaves",
                            text=t(context, "recent_autosaves"),
                            icon="TRIA_DOWN" if recent_expanded else "TRIA_RIGHT",
                            emboss=False,
                        )
                    else:
                        recent_header.label(text=t(context, "recent_autosaves"), icon="TRIA_DOWN")
                    if recent_expanded:
                        recent_entries = custom_autosave.recent_autosaves()
                        if recent_entries:
                            recent_column = recent_box.column(align=True)
                            for entry in recent_entries:
                                modified = time.strftime(
                                    "%d.%m.%Y %H:%M",
                                    time.localtime(entry["modified"]),
                                )
                                entry_row = recent_column.row(align=True)
                                operator = entry_row.operator(
                                    "wm.airetopo_open_recent_autosave",
                                    text=f'{entry["name"]}  ·  {modified}',
                                    icon="FILE_BLEND",
                                )
                                operator.filepath = entry["filepath"]
                                show_file = entry_row.operator(
                                    "wm.airetopo_show_file_in_browser",
                                    text="",
                                    icon="FILE_FOLDER",
                                )
                                show_file.filepath = entry["filepath"]
                            recent_box.label(text=t(context, "recent_autosave_save_as_hint"), icon="INFO")
                        else:
                            recent_box.label(text=t(context, "no_recent_autosaves"), icon="INFO")

        header = layout.row(align=True)
        expand_operator = header.operator(
            "object.airetopo_set_all_section_visibility",
            text=t(context, "show_all_sections"),
            icon="TRIA_DOWN",
        )
        expand_operator.visible = True
        collapse_operator = header.operator(
            "object.airetopo_set_all_section_visibility",
            text=t(context, "hide_all_sections"),
            icon="TRIA_RIGHT",
        )
        collapse_operator.visible = False
        header.separator()
        header.prop(
            visibility,
            "single_section_mode",
            text="",
            icon="SOLO_ON" if visibility.single_section_mode else "SOLO_OFF",
            toggle=True,
        )
        header.separator()
        settings_operator = header.operator(
            "wm.airetopo_toggle_panel_settings",
            text="",
            icon="PREFERENCES",
            depress=bool(preferences and preferences.show_panel_settings),
        )
        del settings_operator

        if preferences is not None and preferences.show_panel_settings:
            box = layout.box()
            box.prop(preferences, "interface_language", text=t(context, "language"))
            box.label(text=t(context, "main_description"))
            box.operator(
                "object.airetopo_restore_panel_defaults",
                text=t(context, "restore_defaults"),
                icon="LOOP_BACK",
            )
            box.separator()
            box.label(text=t(context, "preferences_pie_menu"), icon="MENU_PANEL")
            box.prop(preferences, "active_pie_preset", text=t(context, "pie_active_preset"))
            box.separator()
            box.label(text=t(context, "updates"), icon="FILE_REFRESH")
            update_row = box.row(align=True)
            update_row.operator(
                "wm.airetopo_check_updates",
                text=t(context, "check_updates"),
                icon="VIEWZOOM",
            )
            update_row.operator(
                "wm.airetopo_update_addon",
                text=t(context, "update_addon"),
                icon="IMPORT",
            )
            box.label(text=t(context, "update_status", value=preferences.update_status))
            if (
                preferences.update_branch
                or preferences.update_current_commit
                or preferences.update_remote_commit
            ):
                box.label(
                    text=t(
                        context,
                        "update_commits",
                        branch=preferences.update_branch or "-",
                        current=preferences.update_current_commit or "-",
                        remote=preferences.update_remote_commit or "-",
                    ),
                )
            if preferences.update_last_checked:
                box.label(
                    text=t(
                        context,
                        "update_last_checked",
                        value=preferences.update_last_checked,
                    ),
                )
            box.separator()
            box.prop(
                preferences,
                "use_env_openai_api_key",
                text=t(context, "use_env_openai_api_key"),
            )
            box.prop(preferences, "openai_api_key", text=t(context, "openai_api_key"))
            box.separator()
            box.prop(
                preferences,
                "use_env_gemini_api_key",
                text=t(context, "use_env_gemini_api_key"),
            )
            box.prop(preferences, "gemini_api_key", text=t(context, "gemini_api_key"))

        if state.custom_header_only:
            return
        layout = visible_layout
        search_row = layout.row(align=True)
        search_row.prop(
            visibility,
            "panel_search",
            text="",
            icon="VIEWZOOM",
            placeholder=t(context, "panel_search"),
        )
        if search_query:
            clear_search = search_row.operator("wm.context_set_string", text="", icon="X")
            clear_search.data_path = "scene.airetopo_panel_visibility_settings.panel_search"
            clear_search.value = ""
        search_match_count = 0
        for panel_class, visibility_property in SECTION_PANEL_VISIBILITY:
            search_result = None
            if search_query:
                search_result = _probe_panel(panel_class, context, search_query)
                if not search_result.section_match:
                    continue
                search_match_count += 1
                outer_key = visibility.path_from_id() + "." + visibility_property
                search_result.groups.add(outer_key)
                state.search_filter_groups = search_result.groups
                state.search_filter_terms = search_result.terms
            try:
                content = draw_collapsible_box(
                    layout,
                    visibility,
                    visibility_property,
                    f"{panel_class.bl_order:02d} | {t(context, panel_class.bl_text_key)}",
                    panel_class.bl_icon,
                )
                if content is not None:
                    draw_section_panel_content(panel_class, context, content, visibility_property)
            finally:
                state.search_filter_groups = None
                state.search_filter_terms = ()
        if search_query and search_match_count == 0:
            layout.label(text=t(context, "panel_search_no_results"), icon="INFO")


class WM_OT_airetopo_toggle_view_assists(bpy.types.Operator):
    bl_idname = "wm.airetopo_toggle_view_assists"
    bl_label = "Toggle View Assists"
    bl_description = "Show or hide Object Mode seams and the Solid Mode checker together"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        seam_settings = context.scene.polygroups_seam_preparation_settings
        checker_settings = context.scene.polygroups_seam_finalization_settings
        enable = not (
            seam_settings.show_seams_object_mode
            and checker_settings.show_checker_solid_mode
        )
        seam_settings.show_seams_object_mode = enable
        checker_settings.show_checker_solid_mode = enable
        if not enable:
            from .seam_object_overlay import clear_cache as clear_seam_overlay_cache
            from .uv_checker_overlay import clear_cache as clear_checker_overlay_cache

            clear_seam_overlay_cache()
            clear_checker_overlay_cache()
        self.report(
            {"INFO"},
            t(context, "view_assists_enabled" if enable else "view_assists_disabled"),
        )
        return {"FINISHED"}


SECTION_PANEL_CLASSES = (
    VIEW3D_PT_polygroups_import,
    VIEW3D_PT_polygroups_batch_import,
    VIEW3D_PT_polygroups_model_preparation,
    VIEW3D_PT_polygroups_seam_preparation,
    VIEW3D_PT_polygroups_tools,
    VIEW3D_PT_polygroups_remesh,
    VIEW3D_PT_polygroups_resculpting,
    VIEW3D_PT_polygroups_seam_finalization,
    VIEW3D_PT_polygroups_uv_preparation,
    VIEW3D_PT_polygroups_baking,
    VIEW3D_PT_airetopo_ai_generation,
    VIEW3D_PT_polygroups_mesh_finalization,
    VIEW3D_PT_polygroups_render,
)

state.section_panel_classes = SECTION_PANEL_CLASSES


CLASSES = (
    VIEW3D_PT_polygroups_generator,
    WM_OT_airetopo_toggle_view_assists,
)

SECTION_PANEL_VISIBILITY = (
    (VIEW3D_PT_polygroups_import, "show_import_section"),
    (VIEW3D_PT_polygroups_batch_import, "show_batch_import_section"),
    (VIEW3D_PT_polygroups_model_preparation, "show_model_preparation_section"),
    (VIEW3D_PT_polygroups_seam_preparation, "show_seam_preparation_section"),
    (VIEW3D_PT_polygroups_tools, "show_polygroups_section"),
    (VIEW3D_PT_polygroups_remesh, "show_remesh_section"),
    (VIEW3D_PT_polygroups_resculpting, "show_resculpting_section"),
    (VIEW3D_PT_polygroups_seam_finalization, "show_seam_finalization_section"),
    (VIEW3D_PT_polygroups_uv_preparation, "show_uv_preparation_section"),
    (VIEW3D_PT_polygroups_baking, "show_baking_section"),
    (VIEW3D_PT_airetopo_ai_generation, "show_ai_generation_section"),
    (VIEW3D_PT_polygroups_mesh_finalization, "show_mesh_finalization_section"),
    (VIEW3D_PT_polygroups_render, "show_render_section"),
)

for section_class, visibility_property in SECTION_PANEL_VISIBILITY:
    section_class.visibility_property = visibility_property


def draw_edge_menu(self, context):
    """AI Retopo seam and pinned-edge commands in Edge (Ctrl+E)."""
    layout = self.layout
    layout.separator()
    layout.label(text=t(context, "edge_menu_group"), icon="EDGE_SEAM")
    layout.prop(
        context.scene.polygroups_seam_preparation_settings,
        "seam_path_pin",
        text=t(context, "mark_as_pinned"),
    )
    layout.prop(
        context.scene.polygroups_seam_finalization_settings,
        "auto_unwrap_after_seam",
        text=t(context, "auto_unwrap"),
        toggle=True,
        icon="UV",
    )
    layout.operator(
        "mesh.polygroups_connect_vertex_seam",
        text=t(context, "connect_vertices_seam"),
        icon="EDGE_SEAM",
    )
    layout.operator(
        "mesh.polygroups_edge_seam_path",
        text=t(context, "connect_vertices_edge_seam_path"),
        **icon_kwargs("edge_seam_path", "EDGE_SEAM"),
    )
    layout.separator()
    layout.operator(
        "mesh.polygroups_mark_selected_edges_seam",
        text=t(context, "mark_selected_edges_seam"),
        icon="EDGESEL",
    )
    layout.operator(
        "mesh.polygroups_mark_selection_boundary_seam",
        text=t(context, "mark_selection_boundary_seam"),
        icon="FACESEL",
    )
    layout.operator(
        "mesh.polygroups_clear_selected_edges_seam",
        text=t(context, "clear_selected_edges_seam"),
        icon="X",
    )
    layout.operator(
        "mesh.polygroups_clear_inside_edges_seam",
        text=t(context, "clear_inside_edges_seam"),
        icon="X",
    )
    layout.separator()
    layout.operator("mesh.polygroups_pin_selected_seams", text=t(context, "pin_selected_seams"), **icon_kwargs("pin_vertices", "PINNED"))
    layout.operator("mesh.polygroups_unpin_selected_edges", text=t(context, "unpin_selected"), **icon_kwargs("unpin_vertices", "UNPINNED"))
    layout.operator("mesh.polygroups_clear_all_pins", text=t(context, "clear_all_pins"), **icon_kwargs("unpin_vertices", "X"))


def draw_delete_menu(self, context):
    """Add the topology-preserving patch replacement to Edit Mesh Delete (X)."""
    self.layout.separator()
    self.layout.operator(
        "mesh.polygroups_delete_and_fill",
        text=t(context, "delete_and_fill"),
        icon="MESH_GRID",
    )


def draw_outliner_header(self, context):
    """Compact duplicates of Management controls in the Outliner header."""
    row = self.layout.row(align=True)
    row.separator()
    previous = row.operator(
        "object.polygroups_generated_collection",
        text="Prev",
        icon="TRIA_LEFT",
    )
    previous.action = "PREVIOUS"
    following = row.operator(
        "object.polygroups_generated_collection",
        text="Next",
        icon="TRIA_RIGHT",
    )
    following.action = "NEXT"
    isolate = row.operator(
        "object.polygroups_generated_collection",
        text="",
        icon="OUTLINER_COLLECTION",
    )
    isolate.action = "ISOLATE"
    row.separator()
    hide_highpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_ON",
    )
    hide_highpoly.prefix = "Highpoly_"
    hide_highpoly.hidden = True
    show_highpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_OFF",
    )
    show_highpoly.prefix = "Highpoly_"
    show_highpoly.hidden = False
    row.separator()
    hide_lowpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_ON",
    )
    hide_lowpoly.prefix = "Retopo_"
    hide_lowpoly.hidden = True
    show_lowpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_OFF",
    )
    show_lowpoly.prefix = "Retopo_"
    show_lowpoly.hidden = False


def draw_view_assists_header(self, context):
    """Combined seam/checker overlay toggle in every 3D View header."""
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    seam_settings = getattr(scene, "polygroups_seam_preparation_settings", None)
    checker_settings = getattr(scene, "polygroups_seam_finalization_settings", None)
    if seam_settings is None or checker_settings is None:
        return
    enabled = bool(
        seam_settings.show_seams_object_mode
        and checker_settings.show_checker_solid_mode
    )
    row = self.layout.row(align=True)
    row.separator()
    row.operator(
        "wm.airetopo_toggle_view_assists",
        text="",
        icon="HIDE_OFF" if enabled else "HIDE_ON",
        depress=enabled,
    )


OBJECT_SELECT_TOOL_IDS = {
    "builtin.select",
    "builtin.select_box",
    "builtin.select_circle",
    "builtin.select_lasso",
}


def draw_object_select_tool_actions(self, context):
    """AI Retopo actions beside native Object Mode selection-tool settings."""
    if context.mode != "OBJECT":
        return
    tool = context.workspace.tools.from_space_view3d_mode("OBJECT", create=False)
    if tool is None or tool.idname not in OBJECT_SELECT_TOOL_IDS:
        return

    layout = self.layout
    layout.separator()
    remesh_row = layout.row(align=True)
    previous = remesh_row.operator(
        "object.polygroups_generated_collection",
        text="Prev",
        icon="TRIA_LEFT",
    )
    previous.action = "PREVIOUS"
    following = remesh_row.operator(
        "object.polygroups_generated_collection",
        text="Next",
        icon="TRIA_RIGHT",
    )
    following.action = "NEXT"
    remesh_row.separator()
    remesh_row.label(text="Remesh:")
    for label, quad_count in get_remesh_preset_counts(context):
        operator = remesh_row.operator(
            "object.polygroups_checked_quad_remesh",
            text=label,
        )
        operator.quad_count = quad_count

    layout.separator()
    layout.operator(
        "object.polygroups_unwrap_angle_based",
        text="Unwrap",
        icon="UV",
    )
    layout.operator(
        "object.polygroups_uvpackmaster_pack",
        text="Pack",
        icon="UV_SYNC_SELECT",
    )
    layout.operator(
        "object.polygroups_checked_prepare_and_bake",
        text="Auto Bake",
        icon="RENDER_RESULT",
    )


def draw_edit_select_tool_actions(self, context):
    """Seam actions beside native Edit Mode Box Select and Tweak settings."""
    if context.mode != "EDIT_MESH":
        return
    tool = context.workspace.tools.from_space_view3d_mode("EDIT_MESH", create=False)
    if tool is None or tool.idname not in {"builtin.select", "builtin.select_box"}:
        return

    settings = context.scene.polygroups_generator_settings
    layout = self.layout
    layout.separator()
    merge_row = layout.row(align=True)
    merge_row.operator(
        "mesh.polygroups_merge_small_islands",
        text=t(context, "small_islands_merge"),
        icon="AUTOMERGE_ON",
    ).preview = False
    merge_row.prop(settings, "small_island_threshold", text=t(context, "small_islands_threshold"))
    layout.operator(
        "mesh.polygroups_check_seam_gaps",
        text=t(context, "check_seam_gaps"),
        icon="VIEWZOOM",
    ).mode = "SELECT"
    layout.operator(
        "mesh.polygroups_relax_seams",
        text=t(context, "cutter_auto_fix_smart_relax_seams"),
        icon="MOD_SMOOTH",
    ).mode_override = "SMART"
    layout.operator(
        "mesh.polygroups_relax_seams",
        text=t(context, "smart_relax_selected_seams"),
        icon="MOD_SMOOTH",
    ).selected_seams_only = True
    pin_row = layout.row(align=True)
    pin_row.operator(
        "mesh.polygroups_pin_selected_seams",
        text=t(context, "pin_selected_seams"),
        **icon_kwargs("pin_vertices", "PINNED"),
    )
    pin_row.operator(
        "mesh.polygroups_unpin_selected_edges",
        text=t(context, "unpin_selected"),
        **icon_kwargs("unpin_vertices", "UNPINNED"),
    )


def draw_view_assists_shading_pie(self, context):
    """Add Object Mode overlay toggles to the standard Z shading pie."""
    if context.mode != "OBJECT":
        return
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    seam_settings = getattr(scene, "polygroups_seam_preparation_settings", None)
    checker_settings = getattr(scene, "polygroups_seam_finalization_settings", None)
    if seam_settings is None or checker_settings is None:
        return
    pie = self.layout.menu_pie()
    enabled = bool(
        seam_settings.show_seams_object_mode
        and checker_settings.show_checker_solid_mode
    )
    pie.operator(
        "wm.airetopo_toggle_view_assists",
        text="Toggle Assists",
        icon="HIDE_OFF" if enabled else "HIDE_ON",
        depress=enabled,
    )
    pie.prop(
        seam_settings,
        "show_seams_object_mode",
        text=t(context, "show_seams_object_mode"),
        icon="EDGE_SEAM",
        toggle=True,
    )
    pie.prop(
        checker_settings,
        "show_checker_solid_mode",
        text=t(context, "show_checker_solid_mode"),
        icon="TEXTURE",
        toggle=True,
    )


def draw_object_apply_menu(self, context):
    """Add the cutter workflow to Object Mode's Ctrl+A menu."""
    self.layout.separator()
    self.layout.operator(
        "object.polygroups_apply_cutter_seams",
        text=t(context, "apply_cutter_seams"),
        icon="EDGE_SEAM",
    )


def draw_move_to_collection_menu(self, context):
    self.layout.separator()
    self.layout.operator(
        "object.polygroups_move_to_new_generated_collection",
        text="New Generated.N Collection",
        icon="COLLECTION_NEW",
    )


class VIEW3D_MT_polygroups_move_to_collection(bpy.types.Menu):
    bl_label = "Move to Collection"
    bl_options = {"SEARCH_ON_KEY_PRESS"}

    def draw(self, context):
        self.layout.menu_contents("OBJECT_MT_move_to_collection")
        draw_move_to_collection_menu(self, context)


_move_collection_keymaps = []


def register():
    update_panel_labels(bpy.context)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_edit_mesh_edges.append(draw_edge_menu)
    bpy.types.VIEW3D_MT_edit_mesh_delete.append(draw_delete_menu)
    bpy.types.VIEW3D_MT_object_apply.append(draw_object_apply_menu)
    bpy.utils.register_class(VIEW3D_MT_polygroups_move_to_collection)
    bpy.types.VIEW3D_MT_object_collection.append(draw_move_to_collection_menu)
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is not None:
        keymap = keyconfig.keymaps.new(name="Object Mode", space_type="EMPTY")
        item = keymap.keymap_items.new("wm.call_menu", "M", "PRESS")
        item.properties.name = "VIEW3D_MT_polygroups_move_to_collection"
        _move_collection_keymaps.append((keymap, item))
    bpy.types.VIEW3D_MT_shading_pie.append(draw_view_assists_shading_pie)
    bpy.types.OUTLINER_HT_header.prepend(draw_outliner_header)
    bpy.types.VIEW3D_HT_header.append(draw_view_assists_header)
    bpy.types.VIEW3D_HT_tool_header.append(draw_object_select_tool_actions)
    bpy.types.VIEW3D_HT_tool_header.prepend(draw_edit_select_tool_actions)


def unregister():
    bpy.types.VIEW3D_HT_tool_header.remove(draw_edit_select_tool_actions)
    bpy.types.VIEW3D_HT_tool_header.remove(draw_object_select_tool_actions)
    bpy.types.VIEW3D_HT_header.remove(draw_view_assists_header)
    bpy.types.OUTLINER_HT_header.remove(draw_outliner_header)
    bpy.types.VIEW3D_MT_shading_pie.remove(draw_view_assists_shading_pie)
    bpy.types.VIEW3D_MT_object_apply.remove(draw_object_apply_menu)
    for keymap, item in _move_collection_keymaps:
        keymap.keymap_items.remove(item)
    _move_collection_keymaps.clear()
    bpy.types.VIEW3D_MT_object_collection.remove(draw_move_to_collection_menu)
    bpy.utils.unregister_class(VIEW3D_MT_polygroups_move_to_collection)
    bpy.types.VIEW3D_MT_edit_mesh_delete.remove(draw_delete_menu)
    bpy.types.VIEW3D_MT_edit_mesh_edges.remove(draw_edge_menu)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
