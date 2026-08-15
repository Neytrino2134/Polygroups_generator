import os
import sys

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


def draw_collapsible_box(layout, settings, property_name, label, icon):
    box = layout.box()
    header = box.row(align=True)
    is_open = getattr(settings, property_name)
    header.prop(
        settings,
        property_name,
        text=label,
        icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
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
    for cls in CLASSES:
        text_key = getattr(cls, "bl_text_key", None)
        if text_key is None:
            continue

        cls.bl_label = f"{cls.bl_order:02d} | {t(context, text_key)}"


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
        header.alignment = "RIGHT"
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
        layout.prop(settings, "cutter_alpha", text=t(context, "cutter_alpha"))
        layout.prop(settings, "cutter_solidify_thickness", text=t(context, "plane_thickness"))
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
        layout.operator(
            "object.polygroups_apply_cutter_seams",
            text=t(context, "apply_cutter_seams"),
            icon="MOD_BOOLEAN",
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
    bl_label = "09 |"
    bl_text_key = "section_baking"
    bl_icon = "RENDER_STILL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 9
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout.box()
        settings = context.scene.polygroups_baking_settings

        column = layout.column(align=True)
        column.prop(settings, "bake_resolution", text=t(context, "bake_resolution"))
        column.prop(settings, "bake_margin", text=t(context, "bake_margin"))
        column.prop(settings, "cage_extrusion", text=t(context, "cage_extrusion"))
        column.prop(settings, "ray_distance", text=t(context, "ray_distance"))
        column.prop(settings, "image_prefix", text=t(context, "image_prefix"))
        column.prop(settings, "use_selected_to_active", text=t(context, "selected_to_active"))

        pass_row = column.row(align=True)
        pass_row.prop(settings, "bake_base_color", text=t(context, "base_color"))
        pass_row.prop(settings, "bake_normal", text=t(context, "normal"))

        column.separator()
        column.operator(
            "object.polygroups_prepare_highpoly_bake_materials",
            text=t(context, "prepare_highpoly_texture_only"),
            icon="MATERIAL",
        )
        column.operator(
            "object.polygroups_prepare_lowpoly_bake_material",
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
            "object.polygroups_prepare_and_bake",
            text=t(context, "prepare_and_bake"),
            icon="RENDER_RESULT",
        )
        column.operator(
            "object.polygroups_save_bake_textures",
            text=t(context, "save_textures"),
            icon="FILE_FOLDER",
        )


class VIEW3D_PT_airetopo_ai_generation(bpy.types.Panel):
    bl_label = "10 |"
    bl_text_key = "section_ai_generation"
    bl_icon = "IMAGE_DATA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 10
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout
        openai_settings = context.scene.airetopo_ai_generation_settings

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
        layout = self.layout.box()
        settings = context.scene.polygroups_generator_settings
        seam_settings = context.scene.polygroups_seam_finalization_settings
        column = layout.column(align=True)
        column.prop(seam_settings, "auto_unwrap_after_seam", text=t(context, "auto_unwrap"))
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


CLASSES = (
    VIEW3D_PT_polygroups_generator,
    VIEW3D_PT_polygroups_import,
    VIEW3D_PT_polygroups_batch_import,
    VIEW3D_PT_polygroups_model_preparation,
    VIEW3D_PT_polygroups_seam_preparation,
    VIEW3D_PT_polygroups_tools,
    VIEW3D_PT_polygroups_remesh,
    VIEW3D_PT_polygroups_resculpting,
    VIEW3D_PT_polygroups_seam_finalization,
    VIEW3D_PT_polygroups_baking,
    VIEW3D_PT_airetopo_ai_generation,
)


def register():
    update_panel_labels(bpy.context)
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
