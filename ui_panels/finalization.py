"""Finalization section panels."""
import json
import bpy
from ..localization import t
from .common import (
    draw_collapsible_box,
    draw_fab_variant_visibility,
    draw_overlay_polygon_limit_status,
    draw_seam_gap_controls,
    draw_section_header_icon,
    draw_topic,
    section_content_visible,
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
        display_settings = context.scene.polygroups_seam_preparation_settings
        content = draw_topic(layout, context, "seam_final_0", 'Seam Settings', "PREFERENCES")
        if content is not None:
            column = content.column(align=True)
            column.prop(
                display_settings,
                "show_seams_object_mode",
                text=t(context, "show_seams_object_mode"),
                toggle=True,
                icon="EDGE_SEAM",
            )
            if display_settings.show_seams_object_mode:
                column.prop(
                    display_settings,
                    "seam_overlay_max_polygons",
                    text=t(context, "seam_overlay_max_polygons"),
                )
                draw_overlay_polygon_limit_status(
                    column,
                    context,
                    display_settings.seam_overlay_max_polygons,
                    "seam_overlay_skipped",
                )
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

        content = draw_topic(layout, context, "seam_final_1", 'Mark Seams', "EDGE_SEAM")
        if content is not None:
            column = content.column(align=True)
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
            column.operator("mesh.polygroups_repair_uv_stretch", text=t(context, "uv_repair"), icon="UV")

        content = draw_topic(layout, context, "seam_final_2", 'Seam Gap Check', "VIEWZOOM")
        if content is not None:
            column = content.column(align=True)
            draw_seam_gap_controls(column, context, context.scene.polygroups_seam_preparation_settings)

        content = draw_topic(layout, context, "seam_final_3", 'Checker Preview', "TEXTURE")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(
                seam_settings,
                "show_checker_solid_mode",
                text=t(context, "show_checker_solid_mode"),
                toggle=True,
                icon="SHADING_SOLID",
            )
            column.prop(settings, "checker_scale", text=t(context, "checker_scale"))
            if seam_settings.show_checker_solid_mode:
                column.prop(
                    seam_settings,
                    "checker_overlay_opacity",
                    text=t(context, "checker_overlay_opacity"),
                )
                column.prop(
                    seam_settings,
                    "checker_overlay_max_polygons",
                    text=t(context, "checker_overlay_max_polygons"),
                )
                active_object = context.active_object
                polygon_limit = seam_settings.checker_overlay_max_polygons
                if (
                    polygon_limit > 0
                    and active_object is not None
                    and active_object.type == "MESH"
                    and len(active_object.data.polygons) > polygon_limit
                ):
                    column.label(
                        text=t(
                            context,
                            "checker_overlay_skipped",
                            polygons=f"{len(active_object.data.polygons):,}",
                            limit=f"{polygon_limit:,}",
                        ),
                        icon="INFO",
                    )
            column.operator(
                "object.polygroups_apply_checker_material",
                text=t(context, "apply_checker_material"),
                icon="TEXTURE",
            )

        content = draw_topic(layout, context, "seam_final_4", 'UV Unwrap', "UV")
        if content is not None:
            column = content.column(align=True)
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

        content = draw_topic(layout, context, "seam_final_5", t(context, "uv_seam_tools"), "EDGE_SEAM")
        if content is not None:
            column = content.column(align=True)
            column.prop(display_settings, "show_seams_uv_editor",
                        text=t(context, "show_seams_uv_editor"), toggle=True, icon="EDGE_SEAM")
            column.prop(display_settings, "uv_seam_path_auto_rip",
                        text=t(context, "uv_seam_path_auto_rip"), toggle=True, icon="UV")
            column.operator(
                "wm.polygroups_activate_uv_seam_path",
                text=t(context, "activate_uv_seam_path"),
                icon="UV",
            )
            column.label(text=t(context, "uv_seam_path_panel_hint"), icon="INFO")


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

        lods_content = draw_collapsible_box(
            layout, settings, "show_smart_lods_settings", "Smart LODs", "MOD_DECIM",
        )
        if lods_content is not None:
            self.draw_smart_lods(context, lods_content)

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

        unity_content = draw_collapsible_box(
            layout, settings, "show_unity_rename_settings", "Unity Rename", icon="OUTLINER_OB_MESH",
        )
        if unity_content is not None:
            navigation = unity_content.row(align=True)
            navigation.operator("object.polygroups_unity_collection_step", text="Prev Collections", icon="TRIA_LEFT").delta = -1
            navigation.operator("object.polygroups_unity_collection_step", text="Next Collections", icon="TRIA_RIGHT").delta = 1
            unity_content.label(text="Unity Prepare")
            unity_content.prop(settings, "unity_asset_name", text=t(context, "fab_asset_name"))
            unity_content.prop(settings, "unity_name_index")
            row = unity_content.row(align=True)
            row.operator("object.polygroups_unity_index_step", text="", icon="TRIA_LEFT").delta = -1
            row.prop(settings, "unity_asset_index", text="Version Index")
            row.operator("object.polygroups_unity_index_step", text="", icon="TRIA_RIGHT").delta = 1
            row.prop(settings, "unity_auto_increment_index", text="", icon="ADD")
            unity_content.operator("object.polygroups_unity_load_from_file", text="Load from File", icon="FILE_BLEND")
            unity_content.prop(settings, "unity_asset_suffix")
            unity_content.prop(settings, "unity_generate_text_labels")
            unity_content.prop(settings, "unity_label_size")
            unity_content.prop(settings, "unity_copy_textures", text=t(context, "copy_textures"))
            rename_row = unity_content.row(align=True)
            rename_row.operator("object.polygroups_rename_unity_meshes", text="Rename Meshes", icon="GREASEPENCIL")
            rename_row.operator("object.polygroups_fix_unity_textures", text="Fix Textures", icon="IMAGE_DATA")
            row = unity_content.row(align=True)
            for lod in range(6):
                row.operator("object.polygroups_prepare_unity", text=f"LOD{lod}").lod = f"LOD{lod}"
            prepare_row = unity_content.row(align=True)
            prepare_row.operator(
                "object.polygroups_prepare_unity", text="Prepare Meshes (Auto LOD)", icon="SORTSIZE",
            ).auto_lods = True
            color_icon = ('OUTLINER_COLLECTION' if settings.unity_collection_color_tag == 'NONE'
                          else 'COLLECTION_' + settings.unity_collection_color_tag)
            prepare_row.prop(settings, "unity_collection_color_tag", text="", icon=color_icon, icon_only=True)
            prepare_row.prop(settings, "unity_random_collection_color", text="", icon="FILE_REFRESH", toggle=True)
            box = draw_collapsible_box(unity_content, settings, "show_unity_asset_render_settings",
                                       "Render Unity Assets", icon="RENDER_STILL")
            if box is not None:
                box.label(text="Render Settings", icon="SETTINGS")
                box.separator()
                box.prop(settings, "unity_render_mode")
                box.prop(settings, "unity_render_separate")
                box.prop(settings, "unity_render_text")
                box.prop(settings, "unity_render_freestyle")
                render_settings = context.scene.polygroups_render_settings
                color_row = box.row(align=True)
                color_row.enabled = settings.unity_render_freestyle and not render_settings.is_running
                color_row.prop(render_settings, "freestyle_line_color", text=t(context, "render_freestyle_color"))
                color_row.operator("render.polygroups_palette_popup", text="", icon="COLOR")
                box.prop(settings, "unity_render_mesh_info")
                box.prop(settings, "unity_render_image_format")
                box.separator()
                box.operator("object.polygroups_render_unity_assets", icon="RENDER_STILL")
            animation_box = draw_collapsible_box(unity_content, settings, "show_unity_turnaround_settings",
                                                 "Turnaround", icon="RENDER_ANIMATION")
            if animation_box is not None:
                animation_box.label(text="Animation Settings", icon="SETTINGS")
                animation_box.separator()
                rs = context.scene.polygroups_render_settings
                animation_box.prop(rs, "animation_frame_count")
                animation_box.prop(rs, "animation_fps")
                animation_box.separator()
                animation_box.operator("object.polygroups_render_unity_turnaround", icon="RENDER_ANIMATION")
                if rs.is_running or rs.animation_progress > 0:
                    animation_box.progress(factor=rs.animation_progress / 100.0, type='BAR',
                                           text=f'{rs.animation_progress:.0f}%')
                    animation_box.label(text=rs.animation_status)

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
        column.prop(settings, "smart_decimate_hide_source", text=t(context, "smart_decimate_hide_low"))
        column.prop(settings, "smart_decimate_triangle_limit", text=t(context, "smart_decimate_triangle_limit"))
        ratios = column.column(align=True)
        ratios.enabled = settings.smart_decimate_triangle_limit == 0
        ratios.prop(
            settings,
            "smart_decimate_ratio",
            text=t(context, "ratio"),
            slider=True,
        )
        ratios.prop(
            settings,
            "smart_decimate_seams_ratio",
            text=t(context, "seams_decimate_ratio"),
            slider=True,
        )
        smart_decimate_operator = column.operator(
            "object.polygroups_smart_decimate",
            text=t(context, "smart_decimate"),
            icon="MOD_DECIM",
        )
        smart_decimate_operator.hide_source = settings.smart_decimate_hide_source
        smart_decimate_operator.ratio = settings.smart_decimate_ratio
        smart_decimate_operator.triangle_limit = settings.smart_decimate_triangle_limit
        smart_decimate_operator.seams_ratio = settings.smart_decimate_seams_ratio
        smart_decimate_operator.duplicate_and_apply = (
            settings.smart_decimate_duplicate_and_apply
        )

        column.operator("object.polygroups_smart_decimate_all_generated",
                        text=t(context, "smart_decimate_all_generated"), icon="MOD_DECIM")

        column.operator("object.polygroups_show_all_low", text=t(context, "smart_decimate_show_low"), icon="RESTRICT_VIEW_OFF")
        column.operator("object.polygroups_delete_all_decimated", text=t(context, "smart_decimate_delete_all"), icon="TRASH")

    def draw_smart_lods(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)
        column.prop(settings, "smart_lods_count")
        for index in range(1, settings.smart_lods_count + 1):
            column.prop(settings, f"smart_lods_target_{index}", text=f"LOD{index-1} Tris")
        column.prop(settings, "smart_lods_final_decimate")
        column.prop(settings, "smart_lods_triangulate_all")
        column.prop(settings, "smart_lods_remove_zero_area", text=t(context, "smart_lods_remove_zero_area"))
        column.prop(settings, "smart_lods_auto_arrange")
        spacing_row = column.row()
        spacing_row.enabled = settings.smart_lods_auto_arrange
        spacing_row.prop(settings, "smart_lods_spacing")
        column.prop(settings, "smart_lods_create_text")
        column.prop(settings, "smart_lods_text_size")
        column.prop(settings, "smart_lods_prepare_mode", expand=True)
        column.operator("object.polygroups_generate_smart_lods", text="Generate LODs", icon="MOD_DECIM")
        prepare_box = column.box().column(align=True)
        if settings.smart_lods_prepare_mode == 'UNITY':
            prepare_box.prop(settings, "unity_asset_name", text="Asset Name")
            prepare_box.prop(settings, "unity_name_index")
            prepare_box.prop(settings, "unity_asset_index", text="Version Index")
            prepare_box.operator("object.polygroups_unity_load_from_file", text="Load from File", icon="FILE_BLEND")
        else:
            prepare_box.prop(settings, "unreal_lod_asset_name", text="Asset Name")
            prepare_box.prop(settings, "unreal_lod_name_index", text="Name Index")
            prepare_box.prop(settings, "unreal_lod_version_index", text="Version Index")
        prepare_box.operator("object.polygroups_smart_lods_prepare", icon="MOD_DECIM")
        box = column.box().column(align=True)
        box.prop(settings, "smart_lods_render_mode")
        box.prop(settings, "smart_lods_render_text")
        box.prop(settings, "smart_lods_render_freestyle")
        box.operator("object.polygroups_render_smart_lods", icon="RENDER_STILL")

    def draw_mesh_check(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)

        action_row = column.row(align=True)
        action_row.operator(
            "object.polygroups_start_mesh_check",
            text=t(context, "mesh_check_start_step_scan"),
            icon="VIEWZOOM",
        )
        action_row.operator(
            "object.polygroups_scan_and_fix_all",
            text=t(context, "mesh_check_scan_fix_all"),
            icon="TOOL_SETTINGS",
        )
        column.operator(
            "object.polygroups_create_mesh_backup",
            text=t(context, "create_bkp"),
            icon="DUPLICATE",
        )

        column.separator()
        column.label(
            text=t(context, "mesh_check_status", value=settings.mesh_check_status),
            icon="CHECKMARK" if settings.mesh_check_stage_state == "COMPLETE" else "INFO",
        )

        normal_total = settings.mesh_check_inconsistent_normals + settings.mesh_check_inward_normals
        stages = (
            ("FIN_FACES", "mesh_check_stage_fin_faces", settings.mesh_check_thin_protrusions, "FACESEL"),
            ("DOUBLE_WALLS", "mesh_check_stage_double_walls", settings.mesh_check_double_walls, "FACESEL"),
            ("LOOSE_EDGES", "mesh_check_stage_loose_edges", settings.mesh_check_loose_edges, "EDGESEL"),
            ("ISOLATED_VERTICES", "mesh_check_stage_isolated_vertices", settings.mesh_check_loose_vertices, "VERTEXSEL"),
            ("NGONS", "mesh_check_stage_ngons", settings.mesh_check_ngons, "MOD_TRIANGULATE"),
            ("OPEN_BOUNDARIES", "mesh_check_stage_open_boundaries", settings.mesh_check_boundary_loops, "MESH_GRID"),
            ("NORMALS", "mesh_check_stage_normals", normal_total, "NORMALS_FACE"),
        )
        scanned_stages = set(filter(None, settings.mesh_check_scanned_stages.split(",")))

        for index, (stage, label_key, issue_count, stage_icon) in enumerate(stages, start=1):
            is_active = settings.mesh_check_active_stage == stage
            was_scanned = stage in scanned_stages
            box = column.box()
            header = box.row(align=True)
            header.label(
                text=f"{index}. {t(context, label_key)}",
                icon="RADIOBUT_ON" if is_active else stage_icon,
            )
            scan = header.operator(
                "object.polygroups_scan_mesh_stage",
                text=t(context, "mesh_check_scan"),
                icon="VIEWZOOM",
            )
            scan.stage = stage

            if was_scanned:
                result_row = box.row(align=True)
                result_row.label(
                    text=t(context, "mesh_check_found", value=issue_count),
                    icon="ERROR" if issue_count else "CHECKMARK",
                )
            else:
                box.label(text=t(context, "mesh_check_not_scanned"), icon="QUESTION")

            if is_active and was_scanned:
                actions = box.row(align=True)
                actions.enabled = bool(issue_count)
                fix = actions.operator(
                    "object.polygroups_fix_mesh_stage",
                    text=t(context, "mesh_check_fix"),
                    icon="TOOL_SETTINGS",
                )
                fix.stage = stage

                navigation = box.row(align=True)
                navigation.operator(
                    "object.polygroups_next_mesh_check_stage",
                    text=(
                        t(context, "mesh_check_skip_next")
                        if issue_count else t(context, "mesh_check_next")
                    ),
                    icon="FORWARD",
                )
                undo = navigation.row(align=True)
                undo.enabled = settings.mesh_check_can_undo
                undo.operator(
                    "object.polygroups_undo_mesh_check_fix",
                    text=t(context, "mesh_check_undo_fix"),
                    icon="LOOP_BACK",
                )

    def draw_fab_rename(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        variants = draw_collapsible_box(layout, settings, "show_fab_variant_rename", "HIGH / MID / LOW", "OUTLINER_COLLECTION")
        if variants is not None:
            self.draw_fab_variant_rename(context, variants)
        unreal = draw_collapsible_box(layout, settings, "show_unreal_lod_rename", "Unreal LOD Rename", "MOD_DECIM")
        if unreal is not None:
            unreal.prop(settings, "unreal_lod_asset_name")
            unreal.prop(settings, "unreal_lod_name_index")
            unreal.prop(settings, "unreal_lod_version_index")
            unreal.prop(settings, "unreal_lod_keep_high")
            high_suffix = unreal.row()
            high_suffix.enabled = settings.unreal_lod_keep_high
            high_suffix.prop(settings, "unreal_lod_high_suffix")
            unreal.prop(settings, "unreal_lod_collection_color")
            unreal.prop(settings, "unreal_lod_prepare_materials")
            row = unreal.row()
            row.enabled = settings.unreal_lod_prepare_materials
            row.prop(settings, "unreal_lod_copy_textures")
            unreal.operator("object.polygroups_unreal_lod_rename", icon="GREASEPENCIL")

    def draw_fab_variant_rename(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)
        column.enabled = not settings.fab_prepare_is_running
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

        column.operator("object.polygroups_auto_prepare_all_generated",
                        text=t(context, "auto_prepare_all_generated"), icon="CHECKMARK")

        column.operator("object.polygroups_rename_existing_fab",
                        text=t(context, "fab_rename_all_sets"), icon="GREASEPENCIL").selected_only = False
        column.operator("object.polygroups_rename_existing_fab",
                        text=t(context, "fab_rename_selected_sets"), icon="RESTRICT_SELECT_OFF").selected_only = True
        draw_fab_variant_visibility(layout)

        if settings.fab_prepare_status:
            status = layout.box().column(align=True)
            status.label(text=t(context, "fab_queue_status_" + settings.fab_prepare_status.lower()))
            status.progress(factor=settings.fab_prepare_progress, type="BAR",
                            text=t(context, "fab_queue_progress", done=settings.fab_prepare_done,
                                   total=settings.fab_prepare_total))
            status.label(text=t(context, "fab_queue_counts", prepared=settings.fab_prepare_prepared,
                                skipped=settings.fab_prepare_skipped, failed=settings.fab_prepare_failed))
            if settings.fab_prepare_current:
                status.label(text=settings.fab_prepare_current, icon="OUTLINER_COLLECTION")
            if settings.fab_prepare_is_running:
                status.operator("object.polygroups_stop_fab_prepare", text=t(context, "fab_queue_stop"), icon="CANCEL")
            status.label(text=t(context, "fab_queue_title"), icon="PRESET")
            try:
                items = json.loads(settings.fab_prepare_queue_data or "[]")
            except (ValueError, TypeError):
                items = []
            icons = {'QUEUED': 'TIME', 'PROCESSING': 'FILE_REFRESH', 'DONE': 'CHECKMARK',
                     'SKIPPED': 'INFO', 'ERROR': 'ERROR', 'STOPPED': 'CANCEL'}
            for item in items:
                row = status.row(align=True)
                row.label(text=item.get('collection', ''), icon=icons.get(item.get('status'), 'TIME'))
                row.label(text=t(context, "fab_queue_item_" + item.get('status', 'QUEUED').lower()))
                if item.get('asset'):
                    status.label(text=item['asset'])
                if item.get('status') in ('ERROR', 'SKIPPED') and item.get('message'):
                    status.label(text=item['message'])

    def draw_mesh_export(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        content = draw_topic(layout, context, "export_3", "GLTF Export", "EXPORT")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "gltf_export_info_format")
            column.prop(settings, "gltf_export_embedded")
            column.operator("object.polygroups_export_selected_gltf", icon="EXPORT")
        content = draw_topic(layout, context, "export_0", 'Fab Export', "EXPORT")
        if content is not None:
            column = content.column(align=True)
            formats = column.row(align=True)
            formats.prop(settings, "mesh_export_fbx")
            formats.prop(settings, "mesh_export_glb")
            formats.prop(settings, "mesh_export_gltf")
            column.prop(settings, "mesh_export_sort", text=t(context, "mesh_export_sort"))
            if settings.mesh_export_glb and settings.mesh_export_sort in {'LODS', 'LODS_FORMAT'}:
                column.prop(settings, "unreal_glb_mode")
            if settings.mesh_export_gltf and settings.mesh_export_sort in {'LODS', 'LODS_FORMAT'}:
                column.prop(settings, "unreal_gltf_mode")
            column.prop(settings, "mesh_export_info_format", text=t(context, "mesh_export_info_format"))
            column.operator(
                "object.polygroups_export_selected_meshes",
                text=t(context, "export_selected_meshes"),
                icon="EXPORT",
            )

        content = draw_topic(layout, context, "export_1", 'Unity Export', "EXPORT")
        if content is not None:
            column = content.column(align=True)
            navigation = column.row(align=True)
            navigation.operator("object.polygroups_unity_collection_step", text="Prev Collections", icon="TRIA_LEFT").delta = -1
            navigation.operator("object.polygroups_unity_collection_step", text="Next Collections", icon="TRIA_RIGHT").delta = 1
            presets = column.row(align=True)
            presets.operator("object.polygroups_save_unity_export_preset", text="Save Preset", icon="FILE_TICK")
            presets.operator("object.polygroups_load_unity_export_preset", text="Load Preset", icon="IMPORT")
            column.prop(settings, "unity_export_directory")
            column.prop(settings, "unity_export_overwrite")
            column.prop(settings, "unity_export_clear_asset_folder")
            column.prop(settings, "unity_export_autosave")
            formats = column.row(align=True)
            formats.prop(settings, "unity_export_fbx")
            formats.prop(settings, "unity_export_gltf")
            if settings.unity_export_gltf:
                column.prop(settings, "unity_gltf_mode")
            column.prop(settings, "unity_export_all_renders")
            rs = context.scene.polygroups_render_settings
            if settings.unity_export_all_renders:
                column.prop(settings, "unity_render_freestyle")
                color_row = column.row(align=True)
                color_row.enabled = settings.unity_render_freestyle and not rs.is_running
                color_row.prop(rs, "freestyle_line_color", text=t(context, "render_freestyle_color"))
                color_row.operator("render.polygroups_palette_popup", text="", icon="COLOR")
                column.prop(settings, "unity_render_image_format", text="LOD Image Format")
                column.prop(rs, "animation_views_image_format")
                column.prop(rs, "animation_container")
                column.prop(rs, "animation_frame_count")
                column.prop(rs, "animation_fps")
                if rs.is_running or rs.animation_progress > 0:
                    column.progress(factor=rs.animation_progress / 100, type='BAR', text=f'{rs.animation_progress:.0f}%')
                    column.label(text=rs.animation_status)
            column.prop(settings, "unity_export_info_format", text=t(context, "mesh_export_info_format"))
            column.prop(settings, "unity_use_auto_rig_pro")
            column.operator("object.polygroups_export_unity", icon="EXPORT")
            column.prop(settings, "unity_skip_lods")
            prepare = column.operator("object.polygroups_prepare_and_export_unity", icon="EXPORT")
            prepare.skip_lods = settings.unity_skip_lods
            for status_line in settings.unity_export_status.splitlines():
                column.label(text=status_line)

        content = draw_topic(layout, context, "export_2", 'Export Blend Assets', "FILE_BLEND")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            blend_box = column.box()
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
