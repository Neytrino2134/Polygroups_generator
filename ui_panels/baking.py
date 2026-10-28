"""Baking section panels."""
import bpy
from ..localization import t
from .common import (
    draw_optional_prop,
    draw_section_header_icon,
    draw_topic,
    section_content_visible,
    uvpackmaster_status,
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

        content = draw_topic(layout, context, "bake_0", 'Save Project', "FILE_BLEND")
        if content is not None:
            column = content.column(align=True)
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

        content = draw_topic(layout, context, "bake_1", 'Cage Settings', "MOD_SHRINKWRAP")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "cage_extrusion", text=t(context, "cage_extrusion"))
            auto_cage_box = column.box()
            auto_cage_box.prop(settings, "use_auto_cage", text="Auto Cage")
            if settings.use_auto_cage:
                auto_cage_column = auto_cage_box.column(align=True)
                auto_cage_column.prop(settings, "auto_cage_coverage", text=t(context, "auto_cage_coverage"), slider=True)
                auto_cage_column.prop(settings, "auto_cage_margin", text=t(context, "auto_cage_margin"))
                auto_cage_column.prop(settings, "auto_cage_margin_percent", text=t(context, "auto_cage_margin_percent"), slider=True)
                auto_cage_column.prop(settings, "auto_cage_safe_zone", text=t(context, "auto_cage_safe_zone"), slider=True)
                auto_cage_column.prop(settings, "auto_cage_max", text=t(context, "auto_cage_max"))
                auto_cage_column.prop(settings, "auto_cage_sample_limit", text=t(context, "auto_cage_samples"))
                auto_cage_column.operator("object.polygroups_calculate_auto_cage",
                                          text=t(context, "calculate_auto_cage"), icon="MOD_SHRINKWRAP")
                auto_cage_column.label(text=t(context, "auto_cage_status", value=settings.auto_cage_status), icon="INFO")
            smart = column.box()
            smart.prop(settings, "autogenerate_smart_cage", text="Smart Cage Object")
            if settings.autogenerate_smart_cage:
                smart_body = smart.column(align=True)
                smart_body.prop(settings, "smart_cage_object")
                smart_body.prop(settings, "smart_cage_margin")
                smart_body.prop(settings, "smart_cage_started_clearance")
                smart_body.prop(settings, "smart_cage_max")
                smart_body.prop(settings, "smart_cage_smoothing", slider=True)
                smart_body.prop(settings, "smart_cage_iterations")
                smart_body.prop(settings, "smart_cage_samples")
                smart_body.prop(settings, "smart_cage_avoid_self")
                smart_body.operator("object.polygroups_generate_smart_cage", icon="MOD_DISPLACE")
                cage = settings.smart_cage_object
                if cage is not None:
                    modifier = cage.modifiers.get("Smart Cage Displace")
                    if modifier is not None:
                        smart_body.prop(settings, "smart_cage_live_thickness")
                    trim = cage.modifiers.get("Smart Cage Extra Clearance")
                    if trim is not None:
                        smart_body.prop(settings, "smart_cage_live_clearance")
                    reducer = cage.modifiers.get("Smart Cage Reduce Self Intersections")
                    if reducer is not None:
                        smart_body.prop(settings, "smart_cage_reduce_self")
                    smart_body.label(text="Weight Paint: Smart Cage Weights")
                    smart_body.label(text="Diagnostics: Highpoly / Self Intersections")
                    smart_body.operator("object.polygroups_validate_smart_cage", icon="CHECKMARK")
                smart_body.label(text="Last validation (refresh after edits):", icon="INFO")
                for status_part in settings.smart_cage_status.split(" | "):
                    smart_body.label(text=status_part)
                smart_body.label(text="Solver settings apply on Generate; validate after edits")
            column.prop(settings, "ray_distance", text=t(context, "ray_distance"))

        content = draw_topic(layout, context, "bake_2", 'Bake Settings', "RENDER_STILL")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "bake_resolution", text=t(context, "bake_resolution"))
            column.prop(settings, "bake_margin", text=t(context, "bake_margin"))
            column.prop(settings, "bake_background_mode", text=t(context, "bake_background"))
            column.label(text=t(context, "bake_alpha_hint"), icon="IMAGE_ALPHA")
            column.prop(settings, "image_prefix", text=t(context, "image_prefix"))
            column.prop(settings, "use_selected_to_active", text=t(context, "selected_to_active"))

            pass_row = column.row(align=True)
            pass_row.prop(settings, "bake_base_color", text=t(context, "base_color"))
            pass_row.prop(settings, "bake_normal", text=t(context, "normal"))
            column.prop(settings, "bake_artifact_mask", text=t(context, "bake_artifact_mask"))
            if settings.bake_artifact_mask:
                column.prop(settings, "bake_artifact_mode")
                column.prop(settings, "bake_artifact_match_normal")
                if not settings.bake_artifact_match_normal:
                    column.prop(settings, "bake_artifact_resolution", text=t(context, "bake_artifact_resolution"))
                column.prop(settings, "bake_artifact_geometry")
                column.prop(settings, "bake_artifact_self_intersections", text=t(context, "bake_artifact_self_intersections"))
                column.prop(settings, "bake_artifact_inherit_margin", text=t(context, "bake_artifact_inherit_margin"))
                column.prop(settings, "bake_artifact_radius", text=t(context, "bake_artifact_radius"))
                inherited_margin = settings.bake_margin if settings.bake_artifact_inherit_margin else 0
                column.label(text=t(context, "bake_artifact_total_expansion").format(
                    margin=inherited_margin, extra=settings.bake_artifact_radius,
                    total=inherited_margin + settings.bake_artifact_radius,
                ))
                column.prop(settings, "bake_artifact_autofill", text=t(context, "bake_artifact_autofill"))
                if settings.bake_artifact_autofill:
                    column.prop(settings, "bake_artifact_autofill_blur", text=t(context, "bake_artifact_autofill_blur"))
                column.label(text=t(context, "bake_artifact_mask_hint"), icon="INFO")
            column.prop(
                settings,
                "auto_save_textures_after_bake",
                text=t(context, "auto_save_textures_after_bake"),
            )
            column.prop(
                settings,
                "disable_highpoly_after_bake",
                text=t(context, "disable_highpoly_after_bake"),
            )
            column.prop(
                settings,
                "auto_fix_generated_index",
                text=t(context, "auto_fix_generated_index"),
            )
            pack_box = column.box()
            pack_header = pack_box.row(align=True)
            pack_header.prop(
                settings,
                "show_auto_pack_uv_settings",
                text="",
                icon=(
                    "TRIA_DOWN"
                    if settings.show_auto_pack_uv_settings
                    else "TRIA_RIGHT"
                ),
                emboss=False,
            )
            pack_header.prop(
                settings,
                "auto_pack_uv_before_bake",
                text=t(context, "auto_pack_uv_before_bake"),
            )
            if settings.show_auto_pack_uv_settings:
                pack_settings = pack_box.column(align=True)
                installed, enabled, available = uvpackmaster_status(context)
                if not installed:
                    pack_settings.label(text=t(context, "uvpackmaster_not_installed"), icon="ERROR")
                elif not enabled or not available:
                    pack_settings.label(text=t(context, "uvpackmaster_not_enabled"), icon="ERROR")
                else:
                    main_props = context.scene.uvpm4_props.default_main_props
                    draw_optional_prop(
                        pack_settings, main_props, "rotation_enable",
                        text=t(context, "uvpackmaster_rotation_enable"),
                    )
                    draw_optional_prop(
                        pack_settings, main_props, "margin",
                        text=t(context, "uvpackmaster_margin"),
                    )
                    rotation_row = pack_settings.row(align=True)
                    rotation_row.enabled = bool(getattr(main_props, "rotation_enable", True))
                    draw_optional_prop(
                        rotation_row, main_props, "rotation_step",
                        text=t(context, "uvpackmaster_rotation_step"),
                    )
                    draw_optional_prop(
                        pack_settings, main_props, "heuristic_enable",
                        text=t(context, "uvpackmaster_heuristic_search"),
                    )
                    draw_optional_prop(
                        pack_settings, main_props, "heuristic_max_wait_time",
                        text=t(context, "uvpackmaster_max_wait_time"),
                    )
            column.separator()
            auto_bake_row = column.row(align=True)
            auto_bake_row.scale_y = 1.3
            auto_bake_row.enabled = not settings.bake_task_is_running
            auto_bake_row.operator(
                "object.polygroups_checked_prepare_and_bake",
                text=t(context, "prepare_and_bake"),
                icon="RENDER_RESULT",
            )
            auto_bake_row.operator(
                "object.polygroups_rebake_final_mesh",
                text=t(context, "rebake_final_mesh"),
                icon="FILE_REFRESH",
            )

        content = draw_topic(layout, context, "bake_3", 'Bake Operations', "RENDER_STILL")
        if content is not None:
            column = content.column(align=True)
            if settings.bake_task_stage:
                status_box = column.box()
                status_box.label(text=t(context, "bake_task_status"), icon="TIME")
                status_box.label(text=settings.bake_task_message)
                if settings.bake_task_stage != "CANCELLED":
                    status_box.progress(
                        factor=settings.bake_task_progress / 100.0,
                        type="BAR",
                        text=f"{settings.bake_task_progress:.0f}%",
                    )
            material_box = column.box()
            material_box.enabled = not settings.bake_task_is_running
            material_box.label(text=t(context, "material_setup"), icon="MATERIAL")
            material_box.operator(
                "object.polygroups_check_material_textures",
                text=t(context, "check_material_textures"),
                icon="NODE_MATERIAL",
            )
            material_box.operator(
                "object.polygroups_prepare_highpoly_bake_materials",
                text=t(context, "prepare_highpoly_texture_only"),
                icon="MATERIAL",
            )
            material_box.operator(
                "object.polygroups_checked_prepare_lowpoly_bake_material",
                text=t(context, "prepare_lowpoly_bake_material"),
                icon="TEXTURE",
            )

            bake_box = column.box()
            bake_box.enabled = not settings.bake_task_is_running
            bake_box.label(text=t(context, "bake_action"), icon="RENDER_STILL")
            bake_box.operator(
                "object.polygroups_checked_bake_selected_to_active",
                text=t(context, "bake_selected_to_active"),
                icon="RENDER_STILL",
            )
            bake_box.operator(
                "object.polygroups_checked_prepare_and_bake",
                text=t(context, "prepare_and_bake"),
                icon="RENDER_RESULT",
            )

            save_box = column.box()
            save_box.enabled = not settings.bake_task_is_running
            save_box.label(text=t(context, "save_textures_group"), icon="FILE_FOLDER")
            save_box.operator(
                "object.polygroups_save_bake_textures",
                text=t(context, "save_textures"),
                icon="FILE_FOLDER",
            )
            save_box.operator(
                "object.polygroups_restore_textures",
                text=t(context, "restore_textures"),
                icon="FILE_REFRESH",
            )
            save_box.operator(
                "object.polygroups_merge_bake_textures",
                text=t(context, "merge_materials_textures"),
                icon="NODE_COMPOSITING",
            )

        content = draw_topic(layout, context, "bake_4", 'Cleanup', "TRASH")
        if content is not None:
            column = content.column(align=True)
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

        content = draw_topic(layout, context, "uv_0", 'UV Unwrap', "UV")
        if content is not None:
            smart_column = content.column(align=True)
            smart_column.operator(
                "object.polygroups_smart_uv_unwrap",
                text=t(context, "smart_uv_unwrap"),
                icon="UV",
            )
            smart_column.prop(
                context.scene.polygroups_seam_preparation_settings,
                "smart_seam_angle_limit",
                text=t(context, "smart_seam_angle_limit"),
            )
            smart_column.prop(
                context.scene.polygroups_seam_finalization_settings,
                "smart_uv_unwrap_auto_pack",
                text=t(context, "auto_pack"),
            )
            content.separator()
            content.operator(
                "object.polygroups_unwrap_angle_based",
                text=t(context, "unwrap_angle_based"),
                icon="UV",
            )
            content.separator()

        content = draw_topic(layout, context, "uv_4", "topology_guard", "MOD_UVPROJECT")
        if content is not None:
            guard = context.scene.polygroups_seam_finalization_settings
            column = content.column(align=True)
            column.label(text=t(context, "topology_guard_detect"), icon="VIEWZOOM")
            for name in ("fix_handles", "fix_annuli", "fix_closed", "fix_necks", "selected_only"):
                column.prop(guard, "topology_guard_" + name, text=t(context, "topology_guard_" + name))
            column.separator()
            column.label(text=t(context, "topology_guard_shape"), icon="MESH_CYLINDER")
            for name in ("hole_ratio", "lip_angle", "max_flare", "neck_angle", "neck_elongation",
                         "neck_max_share", "tube_tolerance", "cup_min_height"):
                column.prop(guard, "topology_guard_" + name, text=t(context, "topology_guard_" + name))
            column.separator()
            column.label(text=t(context, "topology_guard_seams"), icon="EDGE_SEAM")
            for name in ("sharp_preference", "create_edges", "smooth_rings", "pin_generated",
                         "smart_relax", "unwrap", "pack"):
                column.prop(guard, "topology_guard_" + name, text=t(context, "topology_guard_" + name))
            column.separator()
            column.label(text=t(context, "topology_guard_auto"), icon="AUTO")
            for name in ("after_smart_seams", "before_repair"):
                column.prop(guard, "topology_guard_" + name, text=t(context, "topology_guard_" + name))
            column.separator()
            column.operator_context = 'EXEC_DEFAULT'
            row = column.row(align=True)
            row.operator_context = 'EXEC_DEFAULT'
            for action, label, icon in (
                ('SELECT', 'topology_guard_select', 'RESTRICT_SELECT_OFF'),
                ('APPLY', 'topology_guard_apply', 'EDGE_SEAM'),
            ):
                button = row.operator(
                    'mesh.polygroups_topology_guard', text=t(context, label), icon=icon,
                )
                button.action = action

        content = draw_topic(layout, context, "uv_3", "uv_repair", "UV")
        if content is not None:
            repair = context.scene.polygroups_seam_finalization_settings
            column = content.column(align=True)
            for name in (
                "threshold", "grow_threshold", "min_faces", "smooth_steps",
                "surface_angle", "selected_only", "sharp_preference",
                "create_edges", "merge_small_islands", "small_island_threshold",
                "pin_generated", "smart_relax", "average_island_scale", "native_pack",
            ):
                column.prop(repair, "uv_repair_" + name, text=t(context, "uv_repair_" + name))
            column.separator()
            column.operator_context = 'EXEC_DEFAULT'
            for action, label, icon in (
                ('SELECT', 'uv_repair_select', 'RESTRICT_SELECT_OFF'),
                ('REPAIR', 'uv_repair_apply', 'UV'),
            ):
                button = column.operator(
                    'mesh.polygroups_repair_uv_stretch', text=t(context, label), icon=icon,
                )
                button.action = action
                button.threshold = repair.uv_repair_threshold
                button.grow_threshold = repair.uv_repair_grow_threshold
                button.min_faces = repair.uv_repair_min_faces
                button.smooth_steps = repair.uv_repair_smooth_steps
                button.surface_angle = repair.uv_repair_surface_angle
                button.selected_only = repair.uv_repair_selected_only
                button.sharp_preference = repair.uv_repair_sharp_preference
                button.create_edges = repair.uv_repair_create_edges
                button.merge_small_islands = repair.uv_repair_merge_small_islands
                button.small_island_threshold = repair.uv_repair_small_island_threshold
                button.pin_generated = repair.uv_repair_pin_generated
                button.smart_relax = repair.uv_repair_smart_relax
                button.average_island_scale = repair.uv_repair_average_island_scale
                button.native_pack = repair.uv_repair_native_pack
                button.cleanup_artifacts = repair.uv_repair_cleanup_artifacts
                button.artifact_method = repair.uv_repair_artifact_method
                button.artifact_max_faces = repair.uv_repair_artifact_max_faces
                button.artifact_stretch = repair.uv_repair_artifact_stretch
                button.artifact_compactness = repair.uv_repair_artifact_compactness
            column.separator()
            column.label(text=t(context, "uv_artifact_cleanup"), icon="MESH_DATA")
            for name in (
                "cleanup_artifacts", "artifact_method", "artifact_max_faces",
                "artifact_stretch", "artifact_compactness",
            ):
                column.prop(repair, "uv_repair_" + name, text=t(context, "uv_repair_" + name))
            for action, label, icon in (
                ('SELECT', 'uv_artifact_select', 'RESTRICT_SELECT_OFF'),
                ('APPLY', 'uv_artifact_apply', 'MESH_DATA'),
            ):
                button = column.operator(
                    'mesh.polygroups_uv_artifact_cleanup', text=t(context, label), icon=icon,
                )
                button.action = action
                button.method = repair.uv_repair_artifact_method
                button.max_faces = repair.uv_repair_artifact_max_faces
                button.stretch_threshold = repair.uv_repair_artifact_stretch
                button.compactness_threshold = repair.uv_repair_artifact_compactness
                button.selected_only = repair.uv_repair_selected_only

        content = draw_topic(layout, context, "uv_2", "narrow_island_splitter", "UV_EDGESEL")
        if content is not None:
            narrow = context.scene.polygroups_seam_finalization_settings
            column = content.column(align=True)
            column.prop(narrow, "narrow_island_source", text=t(context, "narrow_island_source"))
            column.prop(narrow, "narrow_island_width", text=t(context, "narrow_island_width"))
            column.prop(narrow, "narrow_island_max_width_percent", text=t(context, "narrow_island_max_width_percent"))
            column.prop(narrow, "narrow_island_min_area_percent", text=t(context, "narrow_island_min_area_percent"))
            column.prop(narrow, "narrow_island_min_faces", text=t(context, "narrow_island_min_faces"))
            column.prop(narrow, "narrow_island_min_length", text=t(context, "narrow_island_min_length"))
            column.prop(narrow, "narrow_island_selected_only", text=t(context, "narrow_island_selected_only"))
            column.prop(narrow, "narrow_island_create_edges", text=t(context, "narrow_island_create_edges"))
            column.prop(narrow, "narrow_island_smart_relax", text=t(context, "narrow_island_smart_relax"))
            column.separator()
            column.operator_context = 'EXEC_DEFAULT'
            for action, label, icon in (
                ('PREVIEW', 'narrow_island_preview', 'VIEWZOOM'),
                ('SEAMS', 'narrow_island_mark_seams', 'EDGE_SEAM'),
                ('SPLIT', 'narrow_island_split_uv', 'UV'),
            ):
                row = column.row(align=True)
                row.operator_context = 'EXEC_DEFAULT'
                row.enabled = action != 'SPLIT' or narrow.narrow_island_source == 'UV'
                button = row.operator(
                    'mesh.polygroups_split_narrow_islands', text=t(context, label), icon=icon,
                )
                button.source = narrow.narrow_island_source
                button.action = action
                button.width = narrow.narrow_island_width
                button.max_width_percent = narrow.narrow_island_max_width_percent
                button.min_island_area_percent = narrow.narrow_island_min_area_percent
                button.min_faces = narrow.narrow_island_min_faces
                button.min_length = narrow.narrow_island_min_length
                button.selected_only = narrow.narrow_island_selected_only
                button.create_edges = narrow.narrow_island_create_edges
                button.smart_relax = narrow.narrow_island_smart_relax
            if narrow.narrow_island_create_edges:
                column.label(text=t(context, 'narrow_island_diagonal_hint'), icon='INFO')
            column.label(text=t(context, 'narrow_island_pack_hint'), icon='INFO')

        content = draw_topic(layout, context, "uv_1", 'UVPackmaster Packing', "UV_SYNC_SELECT")
        if content is not None:
            installed, enabled, available = uvpackmaster_status(context)

            if not installed:
                content.label(text=t(context, "uvpackmaster_not_installed"), icon="ERROR")
                content.label(text=t(context, "uvpackmaster_install_hint"))
                return

            if not enabled or not available:
                content.label(text=t(context, "uvpackmaster_not_enabled"), icon="ERROR")
                content.label(text=t(context, "uvpackmaster_enable_hint"))
                return

            main_props = context.scene.uvpm4_props.default_main_props
            content.label(text=t(context, "uvpackmaster_available"), icon="CHECKMARK")

            pack_row = content.row(align=True)
            pack_row.scale_y = 1.3
            pack_row.operator(
                "object.polygroups_uvpackmaster_pack",
                text=t(context, "uvpackmaster_pack"),
                icon="UV",
            )

            content.separator()
            draw_optional_prop(
                content,
                main_props,
                "rotation_enable",
                text=t(context, "uvpackmaster_rotation_enable"),
            )
            draw_optional_prop(
                content,
                main_props,
                "margin",
                text=t(context, "uvpackmaster_margin"),
            )

            rotation_row = content.row(align=True)
            rotation_row.enabled = bool(getattr(main_props, "rotation_enable", True))
            draw_optional_prop(
                rotation_row,
                main_props,
                "rotation_step",
                text=t(context, "uvpackmaster_rotation_step"),
            )

            draw_optional_prop(
                content,
                main_props,
                "heuristic_enable",
                text=t(context, "uvpackmaster_heuristic_search"),
            )
            draw_optional_prop(
                content,
                main_props,
                "heuristic_max_wait_time",
                text=t(context, "uvpackmaster_max_wait_time"),
            )
