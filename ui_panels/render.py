"""Render section panels."""
import bpy
from ..localization import t
from .common import (
    draw_fab_variant_visibility,
    draw_section_header_icon,
    draw_studio_position,
    draw_topic,
    section_content_visible,
)


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
        content = draw_topic(layout, context, "render_1", 'Quality and Output', "PREFERENCES")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(settings, "render_engine", text=t(context, "render_engine"))
            column.prop(settings, "max_samples", text=t(context, "render_max_samples"))
            column.prop(settings, "resolution_aspect_preset", text=t(context, "render_aspect_preset"), expand=True)
            column.prop(settings, "resolution_size_preset", text=t(context, "render_size_preset"), expand=True)
            resolution_row = column.row(align=True)
            resolution_row.prop(settings, "resolution_x", text=t(context, "render_resolution_x"))
            resolution_row.prop(settings, "resolution_y", text=t(context, "render_resolution_y"))
            column.prop(settings, "resolution_scale", text=t(context, "render_resolution_scale"))
            column.operator(
                "render.polygroups_apply_resolution",
                text=t(context, "render_apply_format"),
                icon="CHECKMARK",
            )
            column.prop(settings, "output_directory", text=t(context, "render_output_directory"))
            column.prop(settings, "image_format")

            column.prop(settings, "transparent_background", text=t(context, "render_transparent_background"))
            scene_row = column.row(align=True)
            scene_row.enabled = settings.transparent_background
            scene_row.prop(settings, "scene_collection_prefix", text=t(context, "render_scene_collection_prefix"))
            column.prop(settings, "skip_existing", text=t(context, "render_skip_existing"))
            column.prop(settings, "overwrite_existing", text=t(context, "render_overwrite_existing"))

        content = draw_topic(layout, context, "render_6", "Scene Setup", "SCENE_DATA")
        if content is not None:
            column = content.column(align=True)
            column.enabled = not settings.is_running
            column.operator("render.polygroups_prepare_studio", text=t(context, "studio_prepare"), icon="SCENE_DATA")
            column.operator("render.polygroups_reset_studio", text=t(context, "studio_reset_all"), icon="LOOP_BACK").scope = 'ALL'

            column.operator("render.polygroups_delete_studio_scenes", text=t(context, "studio_delete_all"), icon="TRASH")

            column.prop(settings, "studio_collection_color_tag", text=t(context, "studio_collection_color_tag"))
            column.prop(settings, "studio_move_step", text=t(context, "studio_move_step"))

            column.separator()
            column.label(text=t(context, "studio_camera"), icon="CAMERA_DATA")
            if settings.studio_camera_position is not None:
                column.prop(settings.studio_camera_position, "location", text="Camera Position")
            column.operator("render.polygroups_reset_studio", text=t(context, "studio_reset_camera"), icon="LOOP_BACK").scope = "CAMERA"
            camera = settings.studio_camera
            if camera is not None and camera.type == "CAMERA":
                draw_studio_position(column, context, "camera", camera, "YZ", t(context, "studio_position"))
                if settings.studio_camera_aim is not None:
                    draw_studio_position(column, context, "camera_aim", settings.studio_camera_aim, "YZ", t(context, "studio_aim"))
                column.prop(camera.data, "type", text=t(context, "studio_camera_type"))
                if camera.data.type == "ORTHO":
                    column.prop(camera.data, "ortho_scale", text=t(context, "studio_ortho_scale"))
                else:
                    column.prop(camera.data, "lens", text=t(context, "studio_lens"))
                column.operator("view3d.view_camera", text=t(context, "studio_camera_view"), icon="VIEW_CAMERA")

            column.separator()
            column.label(text=t(context, "studio_lights"), icon="LIGHT")
            if settings.studio_light_position is not None:
                column.prop(settings.studio_light_position, "location", text="Light Position")
            column.operator("render.polygroups_reset_studio", text=t(context, "studio_reset_lights"), icon="LOOP_BACK").scope = "LIGHTS"
            column.label(text=t(context, "studio_color_presets"), icon="COLOR")
            for pair in (("NEUTRAL", "WARM_COOL"), ("COOL_WARM", "SUNSET"), ("CYAN_MAGENTA", "GOLD_VIOLET")):
                row = column.row(align=True)
                for preset in pair:
                    row.operator("render.polygroups_studio_light_colors",
                                 text=t(context, "studio_palette_" + preset.lower())).preset = preset
            for role in ("key", "fill", "rim"):
                light = getattr(settings, "studio_" + role)
                if light is None or light.type != "LIGHT":
                    continue
                box = column.box().column(align=True)
                box.label(text=t(context, "studio_" + role), icon="LIGHT_AREA")
                box.operator("render.polygroups_reset_studio", text=t(context, "studio_reset_light"), icon="LOOP_BACK").scope = role.upper()
                draw_studio_position(box, context, role, light, "XYZ", t(context, "studio_position"))
                target = getattr(settings, "studio_" + role + "_aim")
                if target is not None:
                    draw_studio_position(box, context, role + "_aim", target, "XYZ", t(context, "studio_aim"))
                box.prop(light, "hide_render", text=t(context, "studio_light_off"))
                box.prop(light.data, "color", text=t(context, "studio_light_color"))
                box.prop(light.data, "energy", text=t(context, "studio_power"))
                if light.data.type == "AREA":
                    box.prop(light.data, "size", text=t(context, "studio_light_size"))

            column.separator()
            column.label(text=t(context, "studio_scene"), icon="MESH_PLANE")
            if settings.studio_scene_position is not None:
                column.prop(settings.studio_scene_position, "location", text="Scene Position")
            column.operator("render.polygroups_reset_studio", text=t(context, "studio_reset_scene"), icon="LOOP_BACK").scope = "SCENE"
            for prop in ("color", "width", "depth", "height", "distance", "radius"):
                column.prop(settings, "studio_" + prop, text=t(context, "studio_" + prop))
            if settings.studio_backdrop is not None:
                column.prop(settings.studio_backdrop, "location", text=t(context, "studio_position"))

        content = draw_topic(layout, context, "render_11", t(context, "render_mesh_selection"), "MESH_DATA")
        if content is not None:
            column = content.column(align=True)
            column.enabled = not settings.is_running
            column.label(text="Selection")
            options_row = column.row(align=True)
            options_row.prop(settings, "render_low", text="LOW")
            options_row.prop(settings, "render_mid", text="MID")
            options_row.prop(settings, "render_high", text="HIGH")
            column.prop(settings, "render_lod_enabled", text="LOD")
            if settings.render_lod_enabled:
                column.prop(settings, "render_lod_level", text="LOD Level")
            column.separator()
            column.label(text="Rename")
            column.prop(settings, "render_rename_suffix", text="Suffix")
            column.operator("object.polygroups_render_rename_suffix", text="Rename Suffix")

        content = draw_topic(layout, context, "render_12", "FreeStyle", "EDGE_SEAM")
        if content is not None:
            freestyle_box = content.column(align=True)
            freestyle_box.prop(settings, "freestyle_edges", text=t(context, "render_freestyle_edges"))
            freestyle_column = freestyle_box.column(align=True)
            freestyle_column.enabled = settings.freestyle_edges
            freestyle_column.prop(settings, "freestyle_as_render_pass", text=t(context, "render_freestyle_as_pass"))
            freestyle_column.prop(settings, "freestyle_line_thickness", text=t(context, "render_freestyle_thickness"))
            color_row = freestyle_column.row(align=True)
            color_row.prop(settings, "freestyle_line_color", text=t(context, "render_freestyle_color"))
            palette_button = color_row.row(align=True)
            palette_button.enabled = not settings.is_running
            palette_button.operator("render.polygroups_palette_popup", text="", icon="COLOR")
            freestyle_row = freestyle_box.row(align=True)
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

        content = draw_topic(layout, context, "render_10", t(context, "render_material_settings"), "MATERIAL")
        if content is not None:
            column = content.column(align=True)
            obj = context.active_object
            if obj is None or obj.type != 'MESH' or not obj.select_get():
                column.label(text=t(context, "render_select_material_mesh"), icon="INFO")
            elif obj.active_material is None:
                column.label(text=t(context, "render_no_active_material"), icon="INFO")
            else:
                column.label(text=obj.name, icon="MESH_DATA")
                if len(obj.material_slots) > 1:
                    column.prop(obj, "active_material_index", text=t(context, "render_material_slot"))
                material = obj.active_material
                column.label(text=material.name, icon="MATERIAL")
                controls = column.column(align=True)
                controls.enabled = not settings.is_running and (material.library is None or material.override_library is not None)
                controls.prop(material, "use_backface_culling", text=t(context, "render_hide_backfaces"))

        content = draw_topic(layout, context, "render_7", t(context, "arrange_objects"), "SNAP_EDGE")
        if content is not None:
            arrange_box = content.column(align=True)
            arrange_box.prop(settings, "render_arrange_spacing", text=t(context, "arrange_spacing_x"))
            arrange_box.prop(settings, "render_arrange_secondary_spacing", text=t(context, "arrange_spacing_y" if settings.render_arrange_plane == "XY" else "arrange_spacing_z"))
            arrange_box.prop(settings, "render_arrange_mode", text=t(context, "arrange_mode"))
            arrange_box.prop(settings, "render_arrange_plane", text=t(context, "arrange_plane"))
            arrange_box.prop(settings, "render_arrange_alignment", text=t(context, "arrange_alignment"))
            rows_row = arrange_box.row(align=True)
            rows_row.enabled = settings.render_arrange_mode == "GRID"
            rows_row.prop(settings, "render_arrange_rows", text=t(context, "arrange_rows"))
            arrange_box.operator(
                "object.polygroups_arrange_batch_objects",
                text=t(context, "arrange_selected"),
                icon="ALIGN_CENTER",
            ).use_render_settings = True

        content = draw_topic(layout, context, "render_2", 'Multiple Views', "CAMERA_DATA")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(settings, "multiview_render", text=t(context, "render_multiview"))
            column.prop(settings, "multiview_render_hero")
            multiview_row = column.row(align=True)
            multiview_row.prop(settings, "multiview_offset", text=t(context, "render_multiview_offset"))
            column.prop(settings, "multiview_angle", text=t(context, "render_multiview_angle"))
            prepare_row = column.row(align=True)
            prepare_row.enabled = not settings.is_running
            prepare_row.operator(
                "object.polygroups_prepare_selected_multiview",
                text=t(context, "render_prepare_multiview"),
                icon="DUPLICATE",
            )
            clear_row = column.row(align=True)
            clear_row.enabled = not settings.is_running
            clear_row.operator(
                "object.polygroups_clear_multiview_render",
                text=t(context, "render_clear_multiview"),
                icon="TRASH",
            )

        content = draw_topic(layout, context, "render_9", "Render Textures", "TEXTURE")
        if content is not None:
            column = content.column(align=True)
            column.enabled = not settings.is_running
            column.operator("object.polygroups_prepare_render_textures", icon="MESH_PLANE")
            column.prop(settings, "texture_render_mode")
            for kind, title in (("BaseColor", "Base Color Planes"), ("Normal", "Normal Planes")):
                column.label(text=title)
                row = column.row(align=True)
                for show, label, icon in ((True, "Show All", "HIDE_OFF"), (False, "Hide All", "HIDE_ON")):
                    op = row.operator("object.polygroups_texture_plane_visibility", text=label, icon=icon)
                    op.kind = kind
                    op.show = show
            column.operator("object.polygroups_clear_render_textures", icon="TRASH")

        content = draw_topic(layout, context, "render_0", 'Render Queue', "RENDER_STILL")
        if content is not None:
            column = content.column(align=True)

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

            if settings.queue_scanned:
                column.progress(
                    factor=1.0,
                    type="BAR",
                    text=t(
                        context, "render_scan_summary",
                        collections=settings.collection_count,
                        jobs=settings.total_count,
                    ),
                )

            column.operator("object.polygroups_render_selected_auto", icon="CAMERA_DATA")
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

            column.operator("object.polygroups_reset_render_state",
                            text=t(context, "render_reset_state"), icon="FILE_REFRESH")
            column.separator()
            visibility = column.column(align=True)
            visibility.enabled = not settings.is_running
            draw_fab_variant_visibility(visibility)

        content = draw_topic(layout, context, "render_4", 'Progress', "INFO")
        if content is not None:
            column = content.column(align=True)
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

        content = draw_topic(layout, context, "render_8", "Color Palettes", "COLOR")
        if content is not None:
            from ..core.render_palettes import draw_library
            column = content.column(align=True)
            column.enabled = not settings.is_running
            draw_library(column, settings)

        content = draw_topic(layout, context, "render_5", 'Animation', "RENDER_ANIMATION")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(settings, "animation_frame_count", text=t(context, "animation_length"))
            column.prop(settings, "animation_fps", text=t(context, "animation_fps"))
            column.prop(settings, "animation_media_type", text=t(context, "animation_media_type"))
            if settings.animation_media_type == "VIDEO":
                column.prop(settings, "animation_container", text=t(context, "animation_container"))
                column.prop(settings, "animation_quality", text=t(context, "animation_quality"))
                if settings.freestyle_edges and settings.freestyle_as_render_pass:
                    column.prop(settings, "animation_freestyle_dual_video")
            column.prop(
                settings,
                "animation_keep_scene_collections",
                text=t(context, "animation_keep_scene_collections"),
            )
            column.prop(settings, "animation_delete_collection_after_render")
            row = column.row(align=True)
            row.enabled = not settings.is_running and context.active_object is not None
            row.operator("object.polygroups_prepare_turnaround_animation",
                         text=t(context, "animation_prepare"), icon="ORIENTATION_GIMBAL")
            render_row = column.row(align=True)
            render_row.enabled = not settings.is_running and bool(settings.animation_collection_name)
            render_row.operator("object.polygroups_render_turnaround_animation",
                                text=t(context, "animation_render"), icon="RENDER_ANIMATION")
            column.prop(settings, "animation_views_image_format")
            if settings.freestyle_edges and settings.freestyle_as_render_pass:
                column.prop(settings, "animation_views_freestyle_dual")
            views_row = column.row(align=True)
            views_row.enabled = not settings.is_running and bool(settings.animation_collection_name)
            views_row.operator("object.polygroups_render_turnaround_views",
                               text=t(context, "animation_render_views"), icon="RENDER_STILL")
            if settings.is_running or settings.animation_progress > 0:
                column.progress(
                    factor=settings.animation_progress / 100.0,
                    type="BAR",
                    text=f"{settings.animation_progress:.0f}%",
                )
            column.label(text=t(context, "animation_status", value=settings.animation_status))
            column.operator("object.polygroups_reset_render_state",
                            text=t(context, "render_reset_state"), icon="FILE_REFRESH")
            if settings.animation_last_output:
                column.label(text=t(context, "animation_output", value=settings.animation_last_output), icon="FILE_MOVIE")
