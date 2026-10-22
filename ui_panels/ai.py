"""Ai section panels."""
import os
import bpy
from ..localization import get_preferences
from ..localization import t
from .common import (
    draw_ai_input_image_controls,
    draw_section_header_icon,
    draw_topic,
    section_content_visible,
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

        prompt_library_content = draw_topic(layout, context, "ai_0", "prompt_library", "TEXT")
        if prompt_library_content is not None:
            self.draw_prompt_library(context, prompt_library_content)

        openai_content = draw_topic(layout, context, "ai_1", "openai_image", "IMAGE_DATA")
        if openai_content is not None:
            self.draw_openai_image(context, openai_content)

        google_content = draw_topic(layout, context, "ai_2", "google_image", "IMAGE_DATA")
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

        content = draw_topic(layout, context, "sculpt_0", 'Multires and Shrinkwrap Settings', "MOD_MULTIRES")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "multires_levels", text=t(context, "multires_levels"))
            column.prop(settings, "shrinkwrap_limit", text=t(context, "shrinkwrap_limit"))
            column.prop(settings, "shrinkwrap_offset", text=t(context, "shrinkwrap_offset"))

        content = draw_topic(layout, context, "sculpt_1", 'Prepare Sculpting', "SCULPTMODE_HLT")
        if content is not None:
            column = content.column(align=True)
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
