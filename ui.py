import os
import sys
from types import SimpleNamespace

import bpy

from .localization import get_preferences
from .localization import t


def quad_remesher_status(context):
    try:
        import addon_utils
    except ImportError:
        addon_utils = None

    installed = addon_utils is not None and any(
        module.__name__ == "quad_remesher"
        for module in addon_utils.modules()
    )
    loaded = False
    enabled = False

    if addon_utils is not None:
        try:
            loaded, enabled = addon_utils.check("quad_remesher")
        except Exception:
            loaded = False
            enabled = False

    has_settings = hasattr(context.scene, "qremesher")
    has_operator = hasattr(bpy.ops, "qremesher") and hasattr(
        bpy.ops.qremesher,
        "remesh",
    )

    return installed, enabled or loaded, has_settings and has_operator


def uvpackmaster_status(context):
    try:
        import addon_utils
    except ImportError:
        addon_utils = None

    installed = addon_utils is not None and any(
        module.__name__ == "uvpackmaster4"
        for module in addon_utils.modules()
    )
    loaded = False
    enabled = False

    if addon_utils is not None:
        try:
            loaded, enabled = addon_utils.check("uvpackmaster4")
        except Exception:
            loaded = False
            enabled = False

    has_settings = hasattr(context.scene, "uvpm4_props") and hasattr(
        context.scene.uvpm4_props,
        "default_main_props",
    )
    has_operator = hasattr(bpy.ops, "uvpackmaster4") and hasattr(
        bpy.ops.uvpackmaster4,
        "pack",
    )

    return installed, enabled or loaded, has_settings and has_operator


def draw_collapsible_box(layout, settings, property_name, label, icon):
    box = layout.box()
    header = box.row(align=True)
    header.alignment = "LEFT"
    is_open = getattr(settings, property_name)
    header.prop(
        settings,
        property_name,
        text="",
        icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
        emboss=False,
    )
    title = header.row(align=True)
    title.alignment = "LEFT"
    title.prop(
        settings,
        property_name,
        text=label,
        icon=icon,
        emboss=False,
    )

    if not is_open:
        return None

    content = box.column(align=True)
    content.separator()
    return content


def draw_section_header_icon(self, context):
    self.layout.label(text="", icon=self.bl_icon)


def addon_version_string():
    package_name = __package__.split(".")[0]
    addon_module = sys.modules.get(package_name)
    version = getattr(addon_module, "bl_info", {}).get("version", (0, 0, 0))
    return ".".join(str(item) for item in version)


def update_panel_labels(context=None):
    for cls in SECTION_PANEL_CLASSES:
        text_key = getattr(cls, "bl_text_key", None)
        if text_key is None:
            continue

        cls.bl_label = f"{cls.bl_order:02d} | {t(context, text_key)}"


def section_content_visible(panel, context):
    settings = getattr(context.scene, "airetopo_panel_visibility_settings", None)
    if settings is None:
        return True

    property_name = getattr(panel, "visibility_property", "")
    return bool(getattr(settings, property_name, True))


def draw_section_panel_content(panel_class, context, layout, visibility_property):
    panel = SimpleNamespace(
        layout=layout,
        visibility_property=visibility_property,
    )
    for name in dir(panel_class):
        if not name.startswith("draw"):
            continue

        value = getattr(panel_class, name, None)
        if callable(value):
            setattr(panel, name, value.__get__(panel, panel_class))

    try:
        panel_class.draw(panel, context)
    except Exception as error:
        print(f"AI Retopo Toolkit: failed to draw {panel_class.__name__}: {error}")
        layout.label(text="Section draw error. Check console.", icon="ERROR")


def draw_material_mode_buttons(layout, context, settings):
    layout.label(text=t(context, "material_mode"))

    first_row = layout.row(align=True)
    source_operator = first_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_source_texture"),
        depress=settings.material_mode == "TEXTURE_ONLY",
    )
    source_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    source_operator.value = "TEXTURE_ONLY"

    tint_operator = first_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_texture_color"),
        depress=settings.material_mode == "TEXTURE_TINT",
    )
    tint_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    tint_operator.value = "TEXTURE_TINT"

    second_row = layout.row(align=True)
    color_operator = second_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_random_color"),
        depress=settings.material_mode == "COLOR_ONLY",
    )
    color_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    color_operator.value = "COLOR_ONLY"

    checker_operator = second_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_checker_texture"),
        depress=settings.material_mode == "CHECKER_TEXTURE",
    )
    checker_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    checker_operator.value = "CHECKER_TEXTURE"


def draw_optional_prop(layout, data, property_name, text="", **kwargs):
    if data is None or not hasattr(data, property_name):
        return False

    try:
        layout.prop(data, property_name, text=text, **kwargs)
    except Exception:
        return False

    return True


def draw_ai_input_image_controls(layout, context, settings, provider):
    layout.prop_search(
        settings,
        "input_image_name",
        bpy.data,
        "images",
        text=t(context, "ai_input_image"),
    )

    image_row = layout.row(align=True)
    base_operator = image_row.operator(
        "object.airetopo_select_material_image",
        text=t(context, "select_base_color_image"),
        icon="MATERIAL",
    )
    base_operator.provider = provider
    base_operator.image_kind = "BASE_COLOR"

    normal_operator = image_row.operator(
        "object.airetopo_select_material_image",
        text=t(context, "select_normal_map_image"),
        icon="NORMALS_FACE",
    )
    normal_operator.provider = provider
    normal_operator.image_kind = "NORMAL"

    preview_operator = image_row.operator(
        "object.airetopo_preview_input_image",
        text=t(context, "preview_input_image"),
        icon="IMAGE",
    )
    preview_operator.provider = provider


class VIEW3D_PT_polygroups_generator(bpy.types.Panel):
    bl_label = f"AI Retopo Toolkit v{addon_version_string()}"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_order = 0

    def draw(self, context):
        preferences = get_preferences(context)
        layout = self.layout
        header = layout.row(align=True)
        collapse_operator = header.operator(
            "object.airetopo_set_all_section_visibility",
            text=t(context, "hide_all_sections"),
            icon="TRIA_RIGHT",
        )
        collapse_operator.visible = False
        expand_operator = header.operator(
            "object.airetopo_set_all_section_visibility",
            text=t(context, "show_all_sections"),
            icon="TRIA_DOWN",
        )
        expand_operator.visible = True
        header.separator()
        visibility = context.scene.airetopo_panel_visibility_settings
        header.prop(
            visibility,
            "single_section_mode",
            text=t(context, "single_section_mode"),
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

        for panel_class, visibility_property in SECTION_PANEL_VISIBILITY:
            content = draw_collapsible_box(
                layout,
                visibility,
                visibility_property,
                f"{panel_class.bl_order:02d} | {t(context, panel_class.bl_text_key)}",
                panel_class.bl_icon,
            )
            if content is not None:
                draw_section_panel_content(panel_class, context, content, visibility_property)


class VIEW3D_PT_polygroups_model_preparation(bpy.types.Panel):
    bl_label = "03 |"
    bl_text_key = "section_model_preparation"
    bl_icon = "AUTOMERGE_ON"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 3
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_model_preparation_settings

        column = layout.column(align=True)
        column.operator(
            "object.polygroups_rename_and_apply_weld",
            text=t(context, "rename_apply_weld"),
            icon="AUTOMERGE_ON",
        )
        column.separator()
        column.operator(
            "object.polygroups_rename_objects",
            text=t(context, "rename_objects"),
            icon="OUTLINER_COLLECTION",
        )
        column.prop(settings, "weld_distance", text=t(context, "weld_distance"))
        column.operator(
            "object.polygroups_apply_weld",
            text=t(context, "apply_weld"),
            icon="AUTOMERGE_ON",
        )


class VIEW3D_PT_polygroups_import(bpy.types.Panel):
    bl_label = "01 |"
    bl_text_key = "section_import"
    bl_icon = "FILE_FOLDER"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings

        files_box = layout.box()
        files_row = files_box.row(align=True)
        files_row.enabled = not settings.batch_is_running
        file_operator = files_row.operator(
            "object.polygroups_batch_import",
            text=t(context, "import_files"),
            icon="FILE_FOLDER",
        )
        file_operator.use_file_selection = True

        files_box.separator()
        files_box.prop(settings, "batch_import_format", text=t(context, "format"))
        files_box.prop(
            settings,
            "file_import_auto_rename_objects",
            text=t(context, "auto_rename_objects"),
        )
        files_box.prop(settings, "file_import_apply_weld", text=t(context, "apply_weld"))


class VIEW3D_PT_polygroups_batch_import(bpy.types.Panel):
    bl_label = "02 |"
    bl_text_key = "section_batch_import"
    bl_icon = "FILE_REFRESH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 2
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_model_preparation_settings

        folder_row = layout.row(align=True)
        folder_row.label(text=t(context, "folder"))
        folder_row.operator("object.polygroups_select_import_folder", text="", icon="FILE_FOLDER")

        folder_path = settings.batch_import_directory or t(context, "no_folder_selected")
        layout.label(text=folder_path, icon="FILE_FOLDER")
        layout.prop(settings, "batch_import_format", text=t(context, "format"))
        layout.prop(settings, "batch_auto_rename_objects", text=t(context, "auto_rename_objects"))
        layout.prop(settings, "batch_apply_weld", text=t(context, "apply_weld"))
        layout.prop(settings, "batch_include_subfolders", text=t(context, "include_subfolders"))
        layout.prop(settings, "batch_auto_arrange_objects", text=t(context, "auto_arrange_imports"))

        arrange_box = layout.box()
        arrange_box.label(text=t(context, "arrange_objects"), icon="SNAP_EDGE")
        arrange_box.prop(settings, "batch_arrange_spacing", text=t(context, "arrange_spacing"))
        arrange_box.prop(settings, "batch_arrange_mode", text=t(context, "arrange_mode"))
        rows_row = arrange_box.row(align=True)
        rows_row.enabled = settings.batch_arrange_mode == "GRID"
        rows_row.prop(settings, "batch_arrange_rows", text=t(context, "arrange_rows"))
        arrange_row = arrange_box.row(align=True)
        arrange_row.enabled = not settings.batch_is_running
        arrange_row.operator(
            "object.polygroups_arrange_batch_objects",
            text=t(context, "arrange_selected"),
            icon="ALIGN_CENTER",
        )

        progress_column = layout.column(align=True)
        progress_column.enabled = False
        progress_column.prop(settings, "batch_import_progress", slider=True)
        progress_column.label(text=t(context, "total_files", value=settings.batch_total_count))
        progress_column.label(text=t(context, "imported_files", value=settings.batch_imported_count))
        progress_column.label(text=t(context, "imported_objects", value=settings.batch_imported_object_count))
        progress_column.label(text=t(context, "remaining_files", value=settings.batch_remaining_count))
        if settings.batch_current_file:
            progress_column.label(text=t(context, "current_file", value=settings.batch_current_file))

        scan_row = layout.row(align=True)
        scan_row.enabled = not settings.batch_is_running
        scan_row.operator(
            "object.polygroups_scan_import_folder",
            text=t(context, "scan_folder"),
            icon="VIEWZOOM",
        )

        operator_row = layout.row(align=True)
        operator_row.enabled = not settings.batch_is_running
        operator_row.operator(
            "object.polygroups_batch_import",
            text=t(context, "import_folder"),
            icon="FILE_REFRESH",
        )


class VIEW3D_PT_polygroups_remesh(bpy.types.Panel):
    bl_label = "06 |"
    bl_text_key = "section_remesh"
    bl_icon = "MOD_REMESH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 6
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        installed, enabled, available = quad_remesher_status(context)

        if not installed:
            layout.label(text=t(context, "quad_not_installed"), icon="ERROR")
            layout.label(text=t(context, "quad_install_hint"))
            return

        if not enabled or not available:
            layout.label(text=t(context, "quad_not_enabled"), icon="ERROR")
            layout.label(text=t(context, "quad_enable_hint"))
            return

        qremesher = context.scene.qremesher

        layout.label(text=t(context, "quad_available"), icon="CHECKMARK")
        layout.operator(
            "object.polygroups_checked_quad_remesh",
            text=t(context, "remesh_it"),
            icon="MOD_REMESH",
        )

        preset_row = layout.row(align=True)
        low_preset = preset_row.operator(
            "object.polygroups_set_quad_count_preset",
            text="LOW",
        )
        low_preset.quad_count = 500
        mid_preset = preset_row.operator(
            "object.polygroups_set_quad_count_preset",
            text="MID",
        )
        mid_preset.quad_count = 3000
        high_preset = preset_row.operator(
            "object.polygroups_set_quad_count_preset",
            text="HIGH",
        )
        high_preset.quad_count = 75000

        layout.prop(qremesher, "target_count", text=t(context, "quad_count"))
        layout.prop(qremesher, "use_materials", text=t(context, "use_materials"))

        symmetry_row = layout.row(align=True)
        symmetry_row.label(text=t(context, "symmetry"))
        symmetry_row.prop(qremesher, "symmetry_x")


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

        tools_box = layout.box()
        tools_column = tools_box.column(align=True)
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

        layout.separator()
        knife_content = draw_collapsible_box(
            layout,
            seam_settings,
            "show_knife_seam_settings",
            t(context, "knife_seam"),
            "MOD_BEVEL",
        )
        if knife_content is not None:
            self.draw_knife_seam(context, knife_content)

        quick_knife_content = draw_collapsible_box(
            layout,
            seam_settings,
            "show_quick_knife_seam_settings",
            t(context, "quick_knife_seam"),
            "MOD_BEVEL",
        )
        if quick_knife_content is not None:
            self.draw_quick_knife_seam(context, quick_knife_content)

        object_cutter_content = draw_collapsible_box(
            layout,
            seam_settings,
            "show_object_seam_cutter_settings",
            t(context, "object_seam_cutter"),
            "MESH_PLANE",
        )
        if object_cutter_content is not None:
            self.draw_object_seam_cutter(context, object_cutter_content)

    def draw_knife_seam(self, context, layout):
        settings = context.scene.polygroups_knife_seam_settings

        layout.prop(settings, "stable_view_cut", text=t(context, "stable_view_cut"))
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
            icon="SCULPTMODE_HLT",
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
            icon="MOD_BEVEL",
        )
        tool_operator.tool_id = "polygroups_generator.quick_knife_seam_tool"

    def draw_object_seam_cutter(self, context, layout):
        settings = context.scene.polygroups_object_seam_cutter_settings

        layout.prop(settings, "cutter_size_multiplier", text=t(context, "cutter_size"))
        layout.prop(settings, "cutter_arc_segments", text=t(context, "cylinder_segments"))
        layout.prop(settings, "cutter_local_ring_fit_mode", text=t(context, "local_ring_fit_mode"))
        layout.prop(settings, "cutter_local_ring_segments", text=t(context, "local_ring_segments"))
        layout.prop(settings, "cutter_local_ring_radius_offset", text=t(context, "local_ring_radius_offset"))
        layout.prop(settings, "cutter_apply_method", text=t(context, "cutter_apply_method"))
        layout.prop(settings, "cutter_alpha", text=t(context, "cutter_alpha"))
        layout.prop(settings, "cutter_solidify_thickness", text=t(context, "plane_thickness"))
        layout.prop(settings, "cutter_path_render_u", text=t(context, "path_render_u"))
        layout.prop(settings, "cutter_path_extrude", text=t(context, "path_extrude"))
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
        layout.separator()
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_plane"),
            icon="MESH_PLANE",
        )
        tool_operator.name = "polygroups_generator.draw_cutter_plane_tool"
        layout.operator(
            "object.polygroups_draw_cutter_plane",
            text=t(context, "draw_cutter_plane"),
            icon="MESH_PLANE",
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_arc"),
            icon="CURVE_BEZCURVE",
        )
        tool_operator.name = "polygroups_generator.draw_cutter_arc_tool"
        layout.operator(
            "object.polygroups_draw_cutter_arc",
            text=t(context, "draw_cutter_arc"),
            icon="CURVE_BEZCURVE",
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_local_ring"),
            icon="MESH_CIRCLE",
        )
        tool_operator.name = "polygroups_generator.draw_cutter_local_ring_tool"
        layout.operator(
            "object.polygroups_draw_cutter_local_ring",
            text=t(context, "draw_cutter_local_ring"),
            icon="MESH_CIRCLE",
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_path"),
            icon="CURVE_PATH",
        )
        tool_operator.name = "polygroups_generator.draw_cutter_path_tool"
        layout.operator(
            "object.polygroups_draw_cutter_path",
            text=t(context, "draw_cutter_path"),
            icon="CURVE_PATH",
        )
        layout.operator(
            "object.polygroups_join_cutter_paths",
            text=t(context, "join_cutter_paths"),
            icon="AUTOMERGE_ON",
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_draw"),
            icon="GREASEPENCIL",
        )
        tool_operator.name = "polygroups_generator.draw_cutter_draw_tool"
        layout.operator(
            "object.polygroups_draw_cutter_draw",
            text=t(context, "draw_cutter_draw"),
            icon="GREASEPENCIL",
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
        layout.operator(
            "object.polygroups_apply_cutter_seams",
            text=t(context, "apply_cutter_seams"),
            icon="MOD_BOOLEAN",
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
        column = layout.column(align=True)
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
        column.separator()
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


class VIEW3D_PT_polygroups_baking(bpy.types.Panel):
    bl_label = "10 |"
    bl_text_key = "section_baking"
    bl_icon = "RENDER_STILL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 10
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_baking_settings

        column = layout.column(align=True)
        column.label(text=t(context, "baking_save_blend_reminder"), icon="INFO")
        save_row = column.row(align=True)
        save_row.operator(
            "object.polygroups_save_blend_file",
            text=t(context, "save_blend_file"),
            icon="FILE_BLEND",
        )
        save_row.operator(
            "object.polygroups_save_blend_file_as",
            text=t(context, "save_blend_file_as"),
            icon="FILE_FOLDER",
        )
        column.separator()

        column.prop(settings, "bake_resolution", text=t(context, "bake_resolution"))
        column.prop(settings, "bake_margin", text=t(context, "bake_margin"))
        column.prop(settings, "cage_extrusion", text=t(context, "cage_extrusion"))
        column.prop(settings, "ray_distance", text=t(context, "ray_distance"))
        column.prop(settings, "image_prefix", text=t(context, "image_prefix"))
        column.prop(settings, "use_selected_to_active", text=t(context, "selected_to_active"))

        pass_row = column.row(align=True)
        pass_row.prop(settings, "bake_base_color", text=t(context, "base_color"))
        pass_row.prop(settings, "bake_normal", text=t(context, "normal"))
        column.prop(
            settings,
            "auto_save_textures_after_bake",
            text=t(context, "auto_save_textures_after_bake"),
        )

        column.separator()
        column.operator(
            "object.polygroups_check_material_textures",
            text=t(context, "check_material_textures"),
            icon="NODE_MATERIAL",
        )
        column.operator(
            "object.polygroups_prepare_highpoly_bake_materials",
            text=t(context, "prepare_highpoly_texture_only"),
            icon="MATERIAL",
        )
        column.operator(
            "object.polygroups_checked_prepare_lowpoly_bake_material",
            text=t(context, "prepare_lowpoly_bake_material"),
            icon="TEXTURE",
        )
        column.operator(
            "object.polygroups_bake_selected_to_active",
            text=t(context, "bake_selected_to_active"),
            icon="RENDER_STILL",
        )
        column.separator()
        column.operator(
            "object.polygroups_checked_prepare_and_bake",
            text=t(context, "prepare_and_bake"),
            icon="RENDER_RESULT",
        )
        column.operator(
            "object.polygroups_save_bake_textures",
            text=t(context, "save_textures"),
            icon="FILE_FOLDER",
        )
        column.operator(
            "object.polygroups_merge_bake_textures",
            text=t(context, "merge_materials_textures"),
            icon="NODE_COMPOSITING",
        )
        column.separator()
        column.operator(
            "object.polygroups_clear_bake_temp_images",
            text=t(context, "clear_all_bake_images"),
            icon="TRASH",
        )


class VIEW3D_PT_polygroups_uv_preparation(bpy.types.Panel):
    bl_label = "09 |"
    bl_text_key = "section_uv_preparation"
    bl_icon = "UV"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 9
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()

        layout.operator(
            "object.polygroups_unwrap_angle_based",
            text=t(context, "unwrap_angle_based"),
            icon="UV",
        )
        layout.separator()

        installed, enabled, available = uvpackmaster_status(context)

        if not installed:
            layout.label(text=t(context, "uvpackmaster_not_installed"), icon="ERROR")
            layout.label(text=t(context, "uvpackmaster_install_hint"))
            return

        if not enabled or not available:
            layout.label(text=t(context, "uvpackmaster_not_enabled"), icon="ERROR")
            layout.label(text=t(context, "uvpackmaster_enable_hint"))
            return

        main_props = context.scene.uvpm4_props.default_main_props
        layout.label(text=t(context, "uvpackmaster_available"), icon="CHECKMARK")

        pack_row = layout.row(align=True)
        pack_row.scale_y = 1.3
        pack_row.operator(
            "object.polygroups_uvpackmaster_pack",
            text=t(context, "uvpackmaster_pack"),
            icon="UV",
        )

        layout.separator()
        draw_optional_prop(
            layout,
            main_props,
            "rotation_enable",
            text=t(context, "uvpackmaster_rotation_enable"),
        )
        draw_optional_prop(
            layout,
            main_props,
            "margin",
            text=t(context, "uvpackmaster_margin"),
        )

        rotation_row = layout.row(align=True)
        rotation_row.enabled = bool(getattr(main_props, "rotation_enable", True))
        draw_optional_prop(
            rotation_row,
            main_props,
            "rotation_step",
            text=t(context, "uvpackmaster_rotation_step"),
        )

        draw_optional_prop(
            layout,
            main_props,
            "heuristic_enable",
            text=t(context, "uvpackmaster_heuristic_search"),
        )
        draw_optional_prop(
            layout,
            main_props,
            "heuristic_max_wait_time",
            text=t(context, "uvpackmaster_max_wait_time"),
        )


class VIEW3D_PT_airetopo_ai_generation(bpy.types.Panel):
    bl_label = "11 |"
    bl_text_key = "section_ai_generation"
    bl_icon = "IMAGE_DATA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 11
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        openai_settings = context.scene.airetopo_ai_generation_settings

        prompt_library_content = draw_collapsible_box(
            layout,
            openai_settings,
            "show_prompt_library_settings",
            t(context, "prompt_library"),
            "TEXT",
        )
        if prompt_library_content is not None:
            self.draw_prompt_library(context, prompt_library_content)

        openai_content = draw_collapsible_box(
            layout,
            openai_settings,
            "show_openai_image_settings",
            t(context, "openai_image"),
            "IMAGE_DATA",
        )
        if openai_content is not None:
            self.draw_openai_image(context, openai_content)

        google_content = draw_collapsible_box(
            layout,
            openai_settings,
            "show_google_image_settings",
            t(context, "google_image"),
            "IMAGE_DATA",
        )
        if google_content is not None:
            self.draw_google_image(context, google_content)

    def draw_prompt_library(self, context, layout):
        settings = context.scene.airetopo_ai_generation_settings
        column = layout.column(align=True)
        column.prop(settings, "prompt_library_collection", text=t(context, "prompt_collection"))
        column.prop(settings, "prompt_library_prompt", text=t(context, "prompt_file"))

        load_row = column.row(align=True)
        openai_operator = load_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "load_to_openai"),
            icon="IMPORT",
        )
        openai_operator.provider = "OPENAI"
        openai_operator.mode = "REPLACE"

        google_operator = load_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "load_to_google"),
            icon="IMPORT",
        )
        google_operator.provider = "GOOGLE"
        google_operator.mode = "REPLACE"

        both_operator = load_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "load_to_both"),
            icon="IMPORT",
        )
        both_operator.provider = "BOTH"
        both_operator.mode = "REPLACE"

        append_row = column.row(align=True)
        append_openai_operator = append_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "append_to_openai"),
            icon="ADD",
        )
        append_openai_operator.provider = "OPENAI"
        append_openai_operator.mode = "APPEND"

        append_google_operator = append_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "append_to_google"),
            icon="ADD",
        )
        append_google_operator.provider = "GOOGLE"
        append_google_operator.mode = "APPEND"

        utility_row = column.row(align=True)
        utility_row.operator(
            "object.airetopo_refresh_prompt_library",
            text=t(context, "refresh_prompt_library"),
            icon="FILE_REFRESH",
        )
        utility_row.operator(
            "object.airetopo_open_prompt_library_folder",
            text=t(context, "open_prompt_folder"),
            icon="FILE_FOLDER",
        )

        if settings.prompt_library_status:
            column.label(text=settings.prompt_library_status, icon="INFO")

    def draw_openai_image(self, context, layout):
        settings = context.scene.airetopo_ai_generation_settings
        preferences = get_preferences(context)
        has_env_key = bool(os.environ.get("OPENAI_API_KEY", ""))
        has_saved_key = bool(preferences and preferences.openai_api_key)
        uses_env_key = bool(preferences and preferences.use_env_openai_api_key)
        has_api_key = (has_env_key or has_saved_key) if uses_env_key else has_saved_key
        if not has_api_key:
            layout.label(text=t(context, "ai_key_missing"), icon="ERROR")

        column = layout.column(align=True)
        draw_ai_input_image_controls(column, context, settings, "OPENAI")
        column.separator()
        column.prop(settings, "prompt", text=t(context, "ai_prompt"))
        column.prop(settings, "model", text=t(context, "ai_model"))
        column.prop(settings, "size", text=t(context, "ai_size"))
        column.prop(settings, "quality", text=t(context, "ai_quality"))
        column.prop(settings, "output_format", text=t(context, "ai_output_format"))

        column.separator()
        generate_row = column.row(align=True)
        generate_row.enabled = not settings.is_generating
        generate_row.operator(
            "object.airetopo_generate_openai_image",
            text=t(context, "generate_openai_image"),
            icon="IMAGE_DATA",
        )

        result_row = column.row(align=True)
        result_row.enabled = bool(settings.last_image_name or settings.last_image_path)
        open_operator = result_row.operator(
            "object.airetopo_open_generated_image",
            text=t(context, "open_image_editor"),
            icon="IMAGE",
        )
        open_operator.provider = "OPENAI"
        save_operator = result_row.operator(
            "object.airetopo_save_generated_image",
            text=t(context, "save_image"),
            icon="FILE_FOLDER",
        )
        save_operator.provider = "OPENAI"

        column.separator()
        status = t(context, "ai_generating") if settings.is_generating else settings.last_status
        column.label(text=t(context, "ai_status", value=status or t(context, "ai_no_status")))
        if settings.last_image_name:
            column.label(text=t(context, "ai_last_image", value=settings.last_image_name), icon="IMAGE")

    def draw_google_image(self, context, layout):
        settings = context.scene.airetopo_google_image_settings
        preferences = get_preferences(context)
        has_env_key = bool(os.environ.get("GEMINI_API_KEY", ""))
        has_saved_key = bool(preferences and preferences.gemini_api_key)
        uses_env_key = bool(preferences and preferences.use_env_gemini_api_key)
        has_api_key = (has_env_key or has_saved_key) if uses_env_key else has_saved_key
        if not has_api_key:
            layout.label(text=t(context, "google_key_missing"), icon="ERROR")

        column = layout.column(align=True)
        draw_ai_input_image_controls(column, context, settings, "GOOGLE")
        column.separator()
        column.prop(settings, "prompt", text=t(context, "ai_prompt"))
        column.prop(settings, "model", text=t(context, "ai_model"))
        column.prop(settings, "aspect_ratio", text=t(context, "ai_aspect_ratio"))
        column.prop(settings, "image_size", text=t(context, "ai_image_size"))
        column.prop(settings, "output_format", text=t(context, "ai_output_format"))

        column.separator()
        generate_row = column.row(align=True)
        generate_row.enabled = not settings.is_generating
        generate_row.operator(
            "object.airetopo_generate_google_image",
            text=t(context, "generate_google_image"),
            icon="IMAGE_DATA",
        )

        result_row = column.row(align=True)
        result_row.enabled = bool(settings.last_image_name or settings.last_image_path)
        open_operator = result_row.operator(
            "object.airetopo_open_generated_image",
            text=t(context, "open_image_editor"),
            icon="IMAGE",
        )
        open_operator.provider = "GOOGLE"
        save_operator = result_row.operator(
            "object.airetopo_save_generated_image",
            text=t(context, "save_image"),
            icon="FILE_FOLDER",
        )
        save_operator.provider = "GOOGLE"

        column.separator()
        status = t(context, "ai_generating") if settings.is_generating else settings.last_status
        column.label(text=t(context, "ai_status", value=status or t(context, "ai_no_status")))
        if settings.last_image_name:
            column.label(text=t(context, "ai_last_image", value=settings.last_image_name), icon="IMAGE")


class VIEW3D_PT_polygroups_resculpting(bpy.types.Panel):
    bl_label = "07 |"
    bl_text_key = "section_resculpting"
    bl_icon = "MOD_MULTIRES"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 7
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_resculpting_settings

        column = layout.column(align=True)
        column.prop(settings, "multires_levels", text=t(context, "multires_levels"))
        column.prop(settings, "shrinkwrap_limit", text=t(context, "shrinkwrap_limit"))
        column.prop(settings, "shrinkwrap_offset", text=t(context, "shrinkwrap_offset"))

        column.separator()
        column.operator(
            "object.polygroups_setup_resculpting",
            text=t(context, "setup_resculpting"),
            icon="MOD_MULTIRES",
        )

        row = column.row(align=True)
        row.operator(
            "object.polygroups_add_multires",
            text=t(context, "multires"),
            icon="MOD_MULTIRES",
        )
        row.operator(
            "object.polygroups_add_shrinkwrap_to_highpoly",
            text=t(context, "shrinkwrap"),
            icon="MOD_SHRINKWRAP",
        )


class VIEW3D_PT_polygroups_seam_finalization(bpy.types.Panel):
    bl_label = "08 |"
    bl_text_key = "section_seam_finalization"
    bl_icon = "EDGE_SEAM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 8
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_generator_settings
        seam_settings = context.scene.polygroups_seam_finalization_settings
        column = layout.column(align=True)
        column.prop(seam_settings, "auto_unwrap_after_seam", text=t(context, "auto_unwrap"))
        column.prop(
            seam_settings,
            "auto_average_islands_scale_after_unwrap",
            text=t(context, "auto_average_islands_scale"),
        )
        column.prop(
            seam_settings,
            "prefer_backside_longitudinal_seam",
            text=t(context, "prefer_backside_longitudinal_seam"),
        )
        column.prop(seam_settings, "double_longitudinal_seam", text=t(context, "double_longitudinal_seam"))
        column.separator()
        column.operator(
            "mesh.polygroups_mark_selected_edges_seam",
            text=t(context, "mark_selected_edges_seam"),
            icon="EDGESEL",
        )
        column.operator(
            "mesh.polygroups_mark_selection_boundary_seam",
            text=t(context, "mark_selection_boundary_seam"),
            icon="EDGESEL",
        )
        column.operator(
            "mesh.polygroups_mark_material_boundaries_seam",
            text=t(context, "generate_seams_materials"),
            icon="EDGE_SEAM",
        )
        column.operator(
            "mesh.polygroups_mark_longitudinal_seam",
            text=t(context, "create_longitudinal_seam"),
            icon="EDGESEL",
        )
        column.operator(
            "mesh.polygroups_mark_boundary_and_longitudinal_seam",
            text=t(context, "boundary_longitudinal_seam"),
            icon="EDGE_SEAM",
        )

        column.separator()
        column.prop(settings, "checker_scale", text=t(context, "checker_scale"))
        column.operator(
            "object.polygroups_apply_checker_material",
            text=t(context, "apply_checker_material"),
            icon="TEXTURE",
        )
        column.separator()
        column.operator(
            "object.polygroups_unwrap_angle_based",
            text=t(context, "unwrap_angle_based"),
            icon="UV",
        )
        column.operator(
            "object.polygroups_smart_uv_project",
            text=t(context, "smart_uv_project"),
            icon="UV",
        )
        column.operator(
            "object.polygroups_average_islands_scale",
            text=t(context, "average_islands_scale"),
            icon="UV_SYNC_SELECT",
        )


class VIEW3D_PT_polygroups_mesh_finalization(bpy.types.Panel):
    bl_label = "12 |"
    bl_text_key = "section_mesh_finalization"
    bl_icon = "MOD_DECIM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 12
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        settings = context.scene.polygroups_mesh_finalization_settings

        decimate_content = draw_collapsible_box(
            layout,
            settings,
            "show_smart_decimate_settings",
            t(context, "decimate"),
            "MOD_DECIM",
        )
        if decimate_content is not None:
            self.draw_decimate(context, decimate_content)

        check_content = draw_collapsible_box(
            layout,
            settings,
            "show_mesh_check_settings",
            t(context, "check_mesh"),
            "VIEWZOOM",
        )
        if check_content is not None:
            self.draw_mesh_check(context, check_content)

        fab_content = draw_collapsible_box(
            layout,
            settings,
            "show_fab_rename_settings",
            t(context, "fab_rename"),
            "OUTLINER_OB_MESH",
        )
        if fab_content is not None:
            self.draw_fab_rename(context, fab_content)

        export_content = draw_collapsible_box(
            layout,
            settings,
            "show_mesh_export_settings",
            t(context, "mesh_export"),
            "EXPORT",
        )
        if export_content is not None:
            self.draw_mesh_export(context, export_content)

    def draw_decimate(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)
        column.prop(
            settings,
            "smart_decimate_duplicate_and_apply",
            text=t(context, "duplicate_and_apply_decimate"),
        )
        row = column.row(align=True)
        smart_decimate_operator = row.operator(
            "object.polygroups_smart_decimate",
            text=t(context, "smart_decimate"),
            icon="MOD_DECIM",
        )
        row.prop(
            settings,
            "smart_decimate_ratio",
            text=t(context, "ratio"),
        )
        smart_decimate_operator.ratio = settings.smart_decimate_ratio
        smart_decimate_operator.duplicate_and_apply = (
            settings.smart_decimate_duplicate_and_apply
        )

    def draw_mesh_check(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)

        action_row = column.row(align=True)
        action_row.operator(
            "object.polygroups_check_mesh",
            text=t(context, "check_mesh"),
            icon="VIEWZOOM",
        )
        action_row.operator(
            "object.polygroups_create_mesh_backup",
            text=t(context, "create_bkp"),
            icon="DUPLICATE",
        )

        has_results = settings.mesh_check_status != "Not checked"
        has_any_issue = any(
            (
                settings.mesh_check_inconsistent_normals,
                settings.mesh_check_inward_normals,
                settings.mesh_check_ngons,
                settings.mesh_check_nonmanifold_edges,
                settings.mesh_check_boundary_loops,
                settings.mesh_check_loose_vertices,
                settings.mesh_check_loose_edges,
                settings.mesh_check_zero_area_faces,
                settings.mesh_check_duplicate_vertices,
                settings.mesh_check_thin_protrusions,
            )
        )
        if not has_results:
            status_icon = "INFO"
        elif has_any_issue:
            status_icon = "ERROR"
        else:
            status_icon = "CHECKMARK"
        column.label(text=t(context, "mesh_check_status", value=settings.mesh_check_status), icon=status_icon)

        def draw_issue_row(text_key, value, operator_id=None, operator_text_key=None, icon="ERROR"):
            if not value:
                return
            row = column.row(align=True)
            row.label(text=t(context, text_key, value=value), icon=icon)
            if operator_id:
                row.operator(
                    operator_id,
                    text=t(context, operator_text_key),
                )

        def draw_protrusion_buttons(row):
            row.operator(
                "object.polygroups_select_thin_protrusions",
                text=t(context, "select_thin_protrusions"),
            )
            row.operator(
                "object.polygroups_delete_thin_protrusions",
                text=t(context, "delete_thin_protrusions"),
            )

        if has_results and has_any_issue:
            normal_total = (
                settings.mesh_check_inconsistent_normals
                + settings.mesh_check_inward_normals
            )
            draw_issue_row(
                "mesh_check_normal_issues",
                normal_total,
                "object.polygroups_fix_mesh_normals",
                "fix_normals",
            )
            draw_issue_row(
                "mesh_check_ngons",
                settings.mesh_check_ngons,
                "object.polygroups_triangulate_ngons",
                "triangulate_ngons",
            )

            if settings.mesh_check_nonmanifold_edges:
                row = column.row(align=True)
                row.label(
                    text=t(
                        context,
                        "mesh_check_nonmanifold_edges",
                        value=settings.mesh_check_nonmanifold_edges,
                    ),
                    icon="ERROR",
                )
                row.operator(
                    "object.polygroups_clean_mesh",
                    text=t(context, "clean_mesh"),
                )
                draw_protrusion_buttons(row)

            draw_issue_row(
                "mesh_check_boundary_loops",
                settings.mesh_check_boundary_loops,
                "object.polygroups_fill_nonmanifold",
                "fill_nonmanifold",
            )

            loose_total = settings.mesh_check_loose_vertices + settings.mesh_check_loose_edges
            draw_issue_row(
                "mesh_check_loose_geometry",
                loose_total,
                "object.polygroups_delete_loose_geometry",
                "delete_loose",
            )

            cleanup_total = (
                settings.mesh_check_zero_area_faces
                + settings.mesh_check_duplicate_vertices
            )
            draw_issue_row(
                "mesh_check_cleanup_issues",
                cleanup_total,
                "object.polygroups_clean_mesh",
                "clean_mesh",
            )

            if settings.mesh_check_thin_protrusions:
                row = column.row(align=True)
                row.label(
                    text=t(
                        context,
                        "mesh_check_thin_protrusions",
                        value=settings.mesh_check_thin_protrusions,
                    ),
                    icon="ERROR",
                )
                draw_protrusion_buttons(row)

        column.separator()
        column.prop(
            settings,
            "show_all_mesh_fix_operators",
            text=t(context, "show_all_fix_operators"),
            toggle=True,
            icon="HIDE_OFF" if settings.show_all_mesh_fix_operators else "HIDE_ON",
        )
        if settings.show_all_mesh_fix_operators:
            all_box = column.box()
            all_column = all_box.column(align=True)

            row = all_column.row(align=True)
            row.operator(
                "object.polygroups_fix_mesh_normals",
                text=t(context, "fix_normals"),
            )
            row.operator(
                "object.polygroups_triangulate_ngons",
                text=t(context, "triangulate_ngons"),
            )

            row = all_column.row(align=True)
            row.operator(
                "object.polygroups_fill_nonmanifold",
                text=t(context, "fill_nonmanifold"),
            )
            row.operator(
                "object.polygroups_delete_loose_geometry",
                text=t(context, "delete_loose"),
            )

            row = all_column.row(align=True)
            draw_protrusion_buttons(row)
            row.operator(
                "object.polygroups_clean_mesh",
                text=t(context, "clean_mesh"),
                icon="BRUSH_DATA",
            )

    def draw_fab_rename(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)
        column.prop(settings, "fab_asset_name", text=t(context, "fab_asset_name"))

        index_row = column.row(align=True)
        index_row.prop(settings, "fab_asset_index", text=t(context, "fab_asset_index"))
        index_row.prop(
            settings,
            "fab_auto_increment_index",
            text=t(context, "auto_increment_index"),
        )
        column.prop(settings, "fab_copy_textures", text=t(context, "copy_textures"))
        column.prop(
            settings,
            "fab_collection_color_tag",
            text=t(context, "fab_collection_color_tag"),
        )

        variant_row = column.row(align=True)
        high_operator = variant_row.operator(
            "object.polygroups_prepare_fab_variant",
            text="HIGH",
        )
        high_operator.variant = "HIGH"
        mid_operator = variant_row.operator(
            "object.polygroups_prepare_fab_variant",
            text="MID",
        )
        mid_operator.variant = "MID"
        low_operator = variant_row.operator(
            "object.polygroups_prepare_fab_variant",
            text="LOW",
        )
        low_operator.variant = "LOW"

        column.operator(
            "object.polygroups_auto_prepare_fab_selection",
            text=t(context, "auto_prepare_fab_selection"),
            icon="CHECKMARK",
        )

    def draw_mesh_export(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)
        column.prop(
            settings,
            "mesh_export_format",
            text=t(context, "mesh_export_format"),
        )
        column.operator(
            "object.polygroups_export_selected_meshes",
            text=t(context, "export_selected_meshes"),
            icon="EXPORT",
        )

        column.separator()
        blend_box = column.box()
        blend_box.label(text=t(context, "blend_asset_export"), icon="FILE_BLEND")
        blend_column = blend_box.column(align=True)
        blend_column.prop(settings, "blend_export_directory", text=t(context, "blend_export_directory"))
        picker_row = blend_column.row(align=True)
        picker_row.prop(
            settings,
            "blend_export_static_collection_picker",
            text=t(context, "blend_export_static_collection_picker"),
        )
        picker_row.operator(
            "object.polygroups_add_blend_static_collection",
            text="",
            icon="ADD",
        )
        picker_row.operator(
            "object.polygroups_clear_blend_static_collections",
            text="",
            icon="TRASH",
        )
        blend_column.prop(
            settings,
            "blend_export_static_collections",
            text=t(context, "blend_export_static_collections"),
        )
        option_column = blend_column.column(align=True)
        option_column.prop(
            settings,
            "blend_export_individual_assets",
            text=t(context, "blend_export_individual_assets"),
        )
        option_column.prop(settings, "blend_export_all_low", text=t(context, "blend_export_all_low"))
        option_column.prop(settings, "blend_export_all_mid", text=t(context, "blend_export_all_mid"))
        option_column.prop(
            settings,
            "blend_export_include_render_settings",
            text=t(context, "blend_export_include_render_settings"),
        )
        option_column.prop(
            settings,
            "blend_export_overwrite_existing",
            text=t(context, "blend_export_overwrite_existing"),
        )

        action_row = blend_column.row(align=True)
        action_row.operator(
            "object.polygroups_scan_blend_assets",
            text=t(context, "blend_export_scan"),
            icon="VIEWZOOM",
        )
        action_row.operator(
            "object.polygroups_export_blend_assets",
            text=t(context, "blend_export_start"),
            icon="FILE_BLEND",
        )

        blend_column.label(text=t(context, "blend_export_status", value=settings.blend_export_status))
        stats_row = blend_column.row(align=True)
        stats_row.label(text=t(context, "blend_export_collections", value=settings.blend_export_collection_count))
        stats_row.label(text=t(context, "blend_export_files", value=settings.blend_export_file_count))
        stats_row = blend_column.row(align=True)
        stats_row.label(text=t(context, "blend_export_low", value=settings.blend_export_low_count))
        stats_row.label(text=t(context, "blend_export_mid", value=settings.blend_export_mid_count))


class VIEW3D_PT_polygroups_render(bpy.types.Panel):
    bl_label = "13 |"
    bl_text_key = "section_render"
    bl_icon = "RENDER_STILL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 13
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_render_settings
        column = layout.column(align=True)

        row = column.row(align=True)
        row.enabled = not settings.is_running
        row.operator(
            "object.polygroups_scan_render_queue",
            text=t(context, "render_scan_queue"),
            icon="VIEWZOOM",
        )
        row.operator(
            "object.polygroups_start_render_queue",
            text=t(context, "render_start"),
            icon="RENDER_STILL",
        )

        current_row = column.row(align=True)
        current_row.enabled = not settings.is_running
        current_row.operator(
            "object.polygroups_render_current_state",
            text=t(context, "render_current_state"),
            icon="RENDER_RESULT",
        )

        row = column.row(align=True)
        row.operator(
            "object.polygroups_continue_render_queue",
            text=t(context, "render_continue"),
            icon="PLAY",
        )
        row.enabled = not settings.is_running and settings.total_count > 0
        stop_row = column.row(align=True)
        stop_row.enabled = settings.is_running
        stop_row.operator(
            "object.polygroups_stop_render_queue",
            text=t(context, "render_stop"),
            icon="CANCEL",
        )

        column.separator()
        column.prop(settings, "render_engine", text=t(context, "render_engine"))
        column.prop(settings, "max_samples", text=t(context, "render_max_samples"))
        resolution_row = column.row(align=True)
        resolution_row.prop(settings, "resolution_x", text=t(context, "render_resolution_x"))
        resolution_row.prop(settings, "resolution_y", text=t(context, "render_resolution_y"))
        column.prop(settings, "resolution_scale", text=t(context, "render_resolution_scale"))
        column.prop(settings, "output_directory", text=t(context, "render_output_directory"))

        options_row = column.row(align=True)
        options_row.prop(settings, "render_low", text=t(context, "render_low"))
        options_row.prop(settings, "render_mid", text=t(context, "render_mid"))
        column.prop(settings, "transparent_background", text=t(context, "render_transparent_background"))
        scene_row = column.row(align=True)
        scene_row.enabled = settings.transparent_background
        scene_row.prop(settings, "scene_collection_prefix", text=t(context, "render_scene_collection_prefix"))
        column.prop(settings, "skip_existing", text=t(context, "render_skip_existing"))
        column.prop(settings, "overwrite_existing", text=t(context, "render_overwrite_existing"))

        column.separator()
        column.prop(settings, "multiview_render", text=t(context, "render_multiview"))
        multiview_row = column.row(align=True)
        multiview_row.enabled = settings.multiview_render
        multiview_row.prop(settings, "multiview_offset", text=t(context, "render_multiview_offset"))
        clear_row = column.row(align=True)
        clear_row.enabled = not settings.is_running
        clear_row.operator(
            "object.polygroups_clear_multiview_render",
            text=t(context, "render_clear_multiview"),
            icon="TRASH",
        )

        column.separator()
        column.prop(settings, "freestyle_edges", text=t(context, "render_freestyle_edges"))
        freestyle_column = column.column(align=True)
        freestyle_column.enabled = settings.freestyle_edges
        freestyle_column.prop(settings, "freestyle_as_render_pass", text=t(context, "render_freestyle_as_pass"))
        freestyle_column.prop(settings, "freestyle_line_thickness", text=t(context, "render_freestyle_thickness"))
        freestyle_column.prop(settings, "freestyle_line_color", text=t(context, "render_freestyle_color"))
        freestyle_row = column.row(align=True)
        freestyle_row.enabled = not settings.is_running
        freestyle_row.operator(
            "object.polygroups_mark_freestyle_edges",
            text=t(context, "render_mark_freestyle"),
            icon="EDGESEL",
        )
        freestyle_row.operator(
            "object.polygroups_clear_freestyle_edges",
            text=t(context, "render_clear_freestyle"),
            icon="TRASH",
        )

        column.separator()
        column.label(text=t(context, "render_status", value=settings.status))
        column.label(text=t(context, "render_collections", value=settings.collection_count))
        column.label(text=t(context, "render_queued", value=settings.total_count))
        column.label(text=t(context, "render_rendered", value=settings.rendered_count))
        column.label(text=t(context, "render_remaining", value=settings.remaining_count))
        if settings.current_collection or settings.current_object:
            column.label(
                text=t(
                    context,
                    "render_current",
                    collection=settings.current_collection or "-",
                    object=settings.current_object or "-",
                ),
            )
        if settings.last_output_path:
            column.label(text=t(context, "render_last_output", value=settings.last_output_path), icon="FILE_IMAGE")


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

CLASSES = (
    VIEW3D_PT_polygroups_generator,
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


def register():
    update_panel_labels(bpy.context)
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
