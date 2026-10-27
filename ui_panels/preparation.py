"""Preparation section panels."""
import bpy
from ..localization import t
from ..core.remesh_defaults import get_remesh_preset_counts
from ..core.import_timing import format_duration
from .common import (
    draw_batch_processing,
    draw_collapsible_box,
    draw_import_progress,
    draw_import_remesh_options,
    draw_mesh_editing,
    draw_section_header_icon,
    draw_topic,
    quad_remesher_status,
    section_content_visible,
)


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

        content = draw_topic(layout, context, "prepare_0", t(context, "model_preparation_group_prepare"), "AUTOMERGE_ON")
        if content is not None:
            column = content.column(align=True)
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

        content = draw_topic(layout, context, "prepare_1", t(context, "model_preparation_group_mesh_edit"), "EDITMODE_HLT")
        if content is not None:
            draw_mesh_editing(content, context, "prepare_1", loose_parts=True)

        content = draw_topic(layout, context, "prepare_2", t(context, "model_preparation_group_manage"), "OUTLINER_COLLECTION")
        if content is not None:
            column = content.column(align=True)
            for prefix, label in (("Highpoly_", "Highpoly"), ("Retopo_", "Retopo")):
                row = column.row(align=True)
                for hidden, key, icon in ((True, "hide_all_named", "RESTRICT_VIEW_ON"),
                                          (False, "show_all_named", "RESTRICT_VIEW_OFF")):
                    operator = row.operator("object.polygroups_object_visibility",
                                            text=t(context, key, value=label), icon=icon)
                    operator.prefix = prefix
                    operator.hidden = hidden
            column.operator("object.polygroups_generated_collection",
                            text=t(context, "isolate_generated_collections"),
                            icon="OUTLINER_COLLECTION").action = "ISOLATE"
            row = column.row(align=True)
            row.operator("object.polygroups_generated_collection",
                         text=t(context, "previous_generated_collection"), icon="TRIA_LEFT").action = "PREVIOUS"
            row.operator("object.polygroups_generated_collection",
                         text=t(context, "next_generated_collection"), icon="TRIA_RIGHT").action = "NEXT"
            column.separator()
            column.operator(
                "object.polygroups_fix_all_generated_indices",
                text=t(context, "fix_all_generated_indices"),
                icon="FILE_REFRESH",
            )

        content = draw_topic(layout, context, "prepare_3", t(context, "model_preparation_group_seams"), "EDGE_SEAM")
        if content is not None:
            column = content.column(align=True)
            column.operator(
                "mesh.polygroups_mark_material_boundaries_seam",
                text=t(context, "generate_seams_materials"),
                icon="EDGE_SEAM",
            )
            column.prop(context.scene.polygroups_generator_settings, "checker_scale",
                        text=t(context, "checker_scale"))
            column.operator(
                "object.polygroups_apply_checker_material",
                text=t(context, "apply_checker_material"),
                icon="TEXTURE",
            )
            column.operator(
                "object.polygroups_unwrap_angle_based",
                text=t(context, "unwrap_angle_based"),
                icon="UV",
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

        content = draw_topic(layout, context, "import_0", t(context, "import_group_source"), "FILE_FOLDER")
        if content is not None:
            files_box = content.column(align=True)
            files_box.prop(settings, "batch_import_format", text=t(context, "format"))
            files_row = files_box.row(align=True)
            files_row.enabled = not settings.batch_is_running
            file_operator = files_row.operator(
                "object.polygroups_batch_import",
                text=t(context, "import_files"),
                icon="FILE_FOLDER",
            )
            file_operator.use_file_selection = True
            files_box.label(text=t(context, "import_automatic_processing" if
                                   settings.file_import_automatic_processing else "import_simple_processing"),
                            icon="MODIFIER")

        content = draw_topic(layout, context, "import_1", t(context, "import_simple_processing"), "MODIFIER")
        if content is not None:
            files_box = content.column(align=True)
            files_box.enabled = (not settings.file_import_automatic_processing
                                 and (not settings.batch_is_running or settings.batch_stage == "PAUSED"))
            files_box.prop(
                settings,
                "file_import_auto_rename_objects",
                text=t(context, "auto_rename_objects"),
            )
            files_box.prop(settings, "file_import_apply_weld", text=t(context, "apply_weld"))
            files_box.prop(settings, "file_import_disable_view_assist",
                           text=t(context, "disable_view_assist"))
            draw_import_remesh_options(files_box, context, settings, "file_import")

        content = draw_topic(layout, context, "import_3", t(context, "import_automatic_processing"), "MODIFIER")
        if content is not None:
            mode_row = content.row(align=True)
            mode_row.enabled = not settings.batch_is_running
            mode_row.prop(settings, "file_import_automatic_processing",
                          text=t(context, "import_use_automatic_processing"), toggle=True)
            automatic = content.column(align=True)
            automatic.enabled = (settings.file_import_automatic_processing
                                 and (not settings.batch_is_running or settings.batch_stage == "PAUSED"))
            draw_batch_processing(automatic, context, settings)
            automatic.separator(type="LINE")
            automatic.prop(settings, "batch_auto_arrange_objects", text=t(context, "auto_arrange_imports"))
            arrange = automatic.column(align=True)
            arrange.enabled = settings.batch_auto_arrange_objects
            arrange.prop(settings, "batch_arrange_spacing", text=t(context, "arrange_spacing_x"))
            arrange.prop(settings, "batch_arrange_secondary_spacing", text=t(context, "arrange_spacing_y" if settings.batch_arrange_plane == "XY" else "arrange_spacing_z"))
            arrange.prop(settings, "batch_arrange_mode", text=t(context, "arrange_mode"))
            arrange.prop(settings, "batch_arrange_plane", text=t(context, "arrange_plane"))
            arrange.prop(settings, "batch_arrange_alignment", text=t(context, "arrange_alignment"))
            arrange.prop(settings, "batch_arrange_rows", text=t(context, "arrange_rows"))
            automatic.prop(settings, "batch_import_mode", text=t(context, "batch_import_mode"), expand=True)
            save_row = automatic.row(align=True)
            save_row.enabled = not settings.batch_is_running
            save_row.operator("object.polygroups_save_blend_file",
                              text=t(context, "save_file"), icon="FILE_TICK")
            hint = automatic.row()
            hint.alert = not bool(bpy.data.filepath)
            hint.label(text=t(context, "batch_save_before_start"),
                       icon="INFO" if bpy.data.filepath else "ERROR")

        content = draw_topic(layout, context, "import_2", t(context, "import_group_progress"), "INFO")
        if content is not None:
            draw_import_progress(content, context, settings)


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

        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings

        content = draw_topic(layout, context, "batch_0", t(context, "import_group_source"), "FILE_FOLDER")
        if content is not None:
            folder_row = content.row(align=True)
            folder_row.label(text=t(context, "folder"))
            folder_row.operator("object.polygroups_select_import_folder", text="", icon="FILE_FOLDER")

            folder_path = settings.batch_import_directory or t(context, "no_folder_selected")
            content.label(text=folder_path, icon="FILE_FOLDER")
            content.prop(settings, "batch_import_format", text=t(context, "format"))
            subfolders_row = content.row()
            subfolders_row.enabled = not settings.batch_is_running
            subfolders_row.prop(settings, "batch_include_subfolders", text=t(context, "include_subfolders"))
            content.separator(type="LINE")
            heading = content.row(align=True)
            heading.alignment = "CENTER"
            heading.label(text="--  " + t(context, "batch_heading_scan") + "  --")
            scan_row = content.row(align=True)
            scan_row.enabled = not settings.batch_is_running
            scan_row.operator(
                "object.polygroups_scan_import_folder",
                text=t(context, "scan_folder"),
                icon="VIEWZOOM",
            )
            content.separator(type="LINE")
            heading = content.row(align=True)
            heading.alignment = "CENTER"
            heading.label(text="--  " + t(context, "batch_heading_status") + "  --")
            content.progress(
                factor=1.0 if settings.batch_stage == "QUEUED" else 0.0,
                type="BAR",
                text=t(context, "scanned_files_found", value=settings.batch_total_count),
            )
            if settings.batch_import_format == "BLEND":
                append_options = content.column(align=True)
                append_options.enabled = not settings.batch_is_running
                append_options.prop(
                    settings,
                    "batch_append_include_highpoly",
                    text=t(context, "batch_append_include_highpoly"),
                )
                append_options.operator(
                    "object.polygroups_append_generated_blends",
                    text=t(context, "batch_append_generated_blends"),
                    icon="APPEND_BLEND",
                )

        content = draw_topic(layout, context, "batch_1", t(context, "import_group_processing"), "MODIFIER")
        if content is not None:
            if settings.batch_import_format == "BLEND":
                content.label(text=t(context, "batch_blend_processing_disabled"), icon="INFO")
            else:
                draw_batch_processing(content, context, settings)

        content = draw_topic(layout, context, "batch_2", t(context, "arrange_objects"), "SNAP_EDGE")
        if content is not None:
            arrange_box = content.column(align=True)
            arrange_box.prop(settings, "batch_auto_arrange_objects", text=t(context, "auto_arrange_imports"))
            arrange_box.prop(settings, "batch_arrange_spacing", text=t(context, "arrange_spacing_x"))
            arrange_box.prop(settings, "batch_arrange_secondary_spacing", text=t(context, "arrange_spacing_y" if settings.batch_arrange_plane == "XY" else "arrange_spacing_z"))
            arrange_box.prop(settings, "batch_arrange_mode", text=t(context, "arrange_mode"))
            arrange_box.prop(settings, "batch_arrange_plane", text=t(context, "arrange_plane"))
            arrange_box.prop(settings, "batch_arrange_alignment", text=t(context, "arrange_alignment"))
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

        content = draw_topic(layout, context, "batch_3", t(context, "import_group_run"), "PLAY")
        if content is not None:
            group = draw_collapsible_box(content, settings, "show_batch_start_file", t(context, "batch_start_save_reset_group"), "FILE_BLEND")
            if group is not None:
                group.separator(type="LINE")
                heading = group.row(align=True)
                heading.alignment = "CENTER"
                heading.label(text="--  " + t(context, "batch_heading_save") + "  --")
                save_row = group.row(align=True)
                save_row.enabled = not settings.batch_is_running
                save_row.operator(
                    "object.polygroups_save_blend_file",
                    text=t(context, "save_file"),
                    icon="FILE_TICK",
                )
                if not bpy.data.filepath:
                    save_hint = group.column(align=True)
                    save_hint.alert = True
                    save_hint.label(
                        text=t(context, "batch_save_before_start_line1"),
                        icon="ERROR",
                    )
                    save_hint.label(text=t(context, "batch_save_before_start_line2"), icon="BLANK1")
                group.separator(type="LINE")
                heading = group.row(align=True)
                heading.alignment = "CENTER"
                heading.label(text="--  " + t(context, "batch_heading_reset") + "  --")
                group.operator(
                    "object.polygroups_reset_import_state",
                    text=t(context, "batch_reset_state"),
                    icon="FILE_REFRESH",
                )
                group.separator(type="LINE")

            group = draw_collapsible_box(content, settings, "show_batch_start_autosave", t(context, "batch_start_autosave_group"), "RECOVER_LAST")
            if group is not None:
                auto_save_row = group.row(align=True)
                auto_save_row.enabled = (
                    not settings.batch_is_running
                    and not (
                        settings.batch_save_generated_separately
                        and settings.batch_separate_collections
                    )
                )
                auto_save_row.prop(
                    settings,
                    "batch_auto_save",
                    text=t(context, "batch_auto_save"),
                    toggle=True,
                )
                interval = auto_save_row.row(align=True)
                interval.enabled = settings.batch_auto_save
                interval.prop(
                    settings,
                    "batch_auto_save_interval",
                    text=t(context, "batch_auto_save_every"),
                )

                separate_save = group.column(align=True)
                separate_save.enabled = not settings.batch_is_running
                separate_save.prop(
                    settings,
                    "batch_save_generated_separately",
                    text=t(context, "batch_save_generated_separately"),
                    toggle=True,
                )
                separate_hint = separate_save.column(align=True)
                separate_hint.alert = bool(
                    settings.batch_save_generated_separately
                    and (not settings.batch_separate_collections or not bpy.data.filepath)
                )
                separate_hint.label(
                    text=t(context, "batch_separate_hint_line1"),
                    icon="ERROR" if separate_hint.alert else "FILE_BLEND",
                )
                separate_hint.label(text=t(context, "batch_separate_hint_line2"), icon="BLANK1")
                auto_restore_row = separate_save.row(align=True)
                auto_restore_row.enabled = bool(
                    settings.batch_save_generated_separately
                    and settings.batch_separate_collections
                )
                auto_restore_row.prop(
                    settings,
                    "batch_auto_restore_separate_retopo",
                    text=t(context, "batch_auto_restore_separate_retopo"),
                )
                if settings.batch_auto_restore_separate_retopo:
                    separate_save.prop(
                        settings,
                        "batch_restore_include_highpoly",
                        text=t(context, "batch_restore_include_highpoly"),
                    )
                group.separator(type="LINE")
                restore_row = group.row(align=True)
                restore_row.enabled = bool(bpy.data.filepath) and not settings.batch_is_running
                restore_row.operator(
                    "object.polygroups_restore_separate_retopo",
                    text=t(context, "batch_restore_separate_retopo"),
                    icon="IMPORT",
                )
                group.separator(type="LINE")

            group = draw_collapsible_box(content, settings, "show_batch_start_mode", t(context, "batch_start_mode_group"), "PLAY")
            if group is not None:
                group.separator(type="LINE")
                heading = group.row(align=True)
                heading.alignment = "CENTER"
                heading.label(text="--  " + t(context, "batch_heading_process") + "  --")
                operator_row = group.row(align=True)
                operator_row.enabled = not settings.batch_is_running and settings.batch_import_format != "BLEND"
                operator_row.operator_context = "EXEC_DEFAULT"
                start_import = operator_row.operator(
                    "object.polygroups_batch_import",
                    text=t(context, "import_folder"),
                    icon="PLAY",
                )
                start_import.use_file_selection = False
                group.separator(type="LINE")
                heading = group.row(align=True)
                heading.alignment = "CENTER"
                heading.label(text="--  " + t(context, "batch_heading_settings") + "  --")
                import_mode_row = group.row(align=True)
                import_mode_row.enabled = not settings.batch_is_running
                import_mode_row.prop(
                    settings,
                    "batch_import_mode",
                    text=t(context, "batch_import_mode"),
                    expand=True,
                )

                from ..operators.import_queue import active_highpoly_collection

                selected_row = group.row(align=True)
                selected_row.enabled = (
                    not settings.batch_is_running
                    and active_highpoly_collection(context) is not None
                )
                selected_row.operator_context = "EXEC_DEFAULT"
                do_selected = selected_row.operator(
                    "object.polygroups_batch_import",
                    text=t(context, "batch_do_selected"),
                    icon="PLAY",
                )
                do_selected.use_file_selection = False
                do_selected.do_selected = True
                selected_hint = group.column(align=True)
                selected_hint.label(text=t(context, "batch_selected_hint_line1"), icon="OUTLINER_OB_MESH")
                selected_hint.label(text=t(context, "batch_selected_hint_line2"), icon="BLANK1")


        content = draw_topic(layout, context, "batch_5", t(context, "phase2_title"), "RECOVER_LAST")
        if content is not None:
            start = draw_collapsible_box(content, settings, "phase2_show_start", "Start Phase 2", "PLAY")
            if start is not None:
                from ..core.phase2_progress import draw_start
                draw_start(start, context, settings)
            group = draw_collapsible_box(content, settings, "phase2_show_restore",
                t(context, "phase2_restore_processing"), "IMPORT")
            if group is not None:
                controls = group.column(align=True)
                controls.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                controls.separator(type="LINE")
                controls.operator("object.polygroups_phase2_restore", text=t(context, "phase2_restore"), icon="IMPORT")
                controls.operator("object.polygroups_phase2_scan", text=t(context, "phase2_scan"), icon="VIEWZOOM")
                controls.prop(settings, "phase2_scan_subfolders", text=t(context, "phase2_recursive"))
                group.label(text=t(context, "phase2_scanned_files", value=settings.phase2_scanned_files), icon="INFO")
                group.label(text=t(context, "phase2_scanned_collections", value=settings.phase2_scanned_collections))
                controls = group.column(align=True)
                controls.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                controls.separator(type="LINE")
                presets = group.column(align=True)
                presets.enabled = not (settings.phase2_pipeline_running or settings.phase2_is_running or settings.phase2_final_is_running or settings.phase2_auto_render_running or settings.batch_is_running)
                modes = presets.row(align=True)
                modes.operator('object.polygroups_phase2_processing_preset', text=t(context, 'phase2_preset_import'),
                    icon='IMPORT', depress=not any((settings.phase2_auto_bake, settings.phase2_mesh_auto_repair, settings.phase2_mid_remesh, settings.phase2_repack_after_repair))).preset = 'IMPORT'
                modes.operator('object.polygroups_phase2_processing_preset', text=t(context, 'phase2_preset_rebake'),
                    icon='RENDER_STILL', depress=settings.phase2_auto_bake).preset = 'REBAKE'
                presets.operator('object.polygroups_phase2_processing_preset', text=t(context, 'phase2_preset_resculpt'),
                    icon='MOD_MULTIRES', depress=settings.phase2_resculpt_retopo01).preset = 'RESCULPT'
                controls = group.column(align=True)
                controls.enabled = presets.enabled
                controls.separator(type="LINE")
                controls.prop(settings, "phase2_clear_generated", text=t(context, "phase2_clear"))
                if settings.phase2_clear_generated:
                    warning = controls.column(align=True)
                    warning.alert = True
                    warning.label(text=t(context, "phase2_clear_hint1"), icon="ERROR")
                    warning.label(text=t(context, "phase2_clear_hint2"), icon="BLANK1")
                controls.prop(settings, 'phase2_skip_retopo_backups')
                controls.prop(settings, "phase2_mesh_auto_repair", text=t(context, "phase2_mesh_auto_repair"))
                controls.prop(settings, 'phase2_mid_remesh')
                if settings.phase2_mid_remesh:
                    controls.label(text='Clear seams + pins | Smart Seams 22 degrees | MID', icon='INFO')
                repack = controls.row()
                repack.prop(settings, "phase2_repack_after_repair", text=t(context, "phase2_repack_after_repair"))
                controls.prop(settings, "phase2_auto_bake", text=t(context, "phase2_autobake"))
                if settings.phase2_auto_bake:
                    controls.prop(settings, "phase2_repair_artifacts", text=t(context, "phase2_repair"))
                    controls.prop(settings, 'phase2_resculpt_retopo01')
                    if settings.phase2_resculpt_retopo01:
                        controls.prop(settings, 'phase2_high_remesh_before_resculpting')
                        if settings.phase2_high_remesh_before_resculpting:
                            controls.label(text='Clear seams + pins | Smart Seams 22 degrees | HIGH', icon='INFO')
                        controls.prop(settings, 'phase2_repair_after_resculpt')
                    controls.prop(settings, 'phase2_autobake_retopo01')
                    controls.prop(settings, "phase2_delete_high_after_bake")
                    controls.prop(settings, "phase2_delete_lower_retopo")
                    keep = controls.row()
                    keep.enabled = settings.phase2_delete_lower_retopo
                    keep.prop(settings, 'phase2_keep_retopo01')
                    controls.label(text=t(context, "phase2_bake_hint1"), icon="INFO")
                    controls.label(text=t(context, "phase2_bake_hint2"), icon="BLANK1")
                controls.prop(settings, 'phase2_autosave')
                autosave = controls.row()
                autosave.enabled = settings.phase2_autosave
                autosave.prop(settings, 'phase2_autosave_every')
                if settings.phase2_autosave_status:
                    group.label(text=settings.phase2_autosave_status, icon='INFO')
                manual = draw_collapsible_box(group, settings, 'phase2_show_manual_cleanup', 'Manual Cleanup', 'TRASH')
                if manual is not None:
                    buttons = manual.column(align=True)
                    buttons.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                    buttons.prop(settings, 'phase2_keep_retopo01')
                    buttons.operator('object.polygroups_phase2_rename_retopo01', icon='SORTALPHA')
                    for family, label in (('RETOPO', 'Retopo_'), ('RESCULPTING', 'Resculpting_')):
                        row = buttons.row(align=True)
                        row.label(text=label)
                        for show, text, icon in ((True, 'Show All', 'RESTRICT_VIEW_OFF'), (False, 'Hide All', 'RESTRICT_VIEW_ON')):
                            op = row.operator('object.polygroups_phase2_mesh_visibility', text=text, icon=icon)
                            op.family, op.show = family, show
                    row = buttons.row(align=True)
                    row.label(text='Multires (Resculpting)')
                    for enable, text in ((True, 'Enable'), (False, 'Disable')):
                        row.operator('object.polygroups_phase2_multires_visibility', text=text, icon='MOD_MULTIRES').enable = enable
                    buttons.operator("object.polygroups_phase2_clear_lower_retopo", icon="TRASH")
                    buttons.operator("object.polygroups_phase2_clear_highpoly", icon="TRASH")
                    buttons.operator("object.polygroups_phase2_clear_backups", icon="TRASH")
                    buttons.operator('object.polygroups_phase2_clear_resculpting', icon='TRASH')
                    buttons.operator('object.polygroups_phase2_clear_generated', icon='TRASH')
                    from ..save_cleanup import draw_missing_files
                    draw_missing_files(buttons, context)
            final = draw_collapsible_box(content, settings, "phase2_show_finalization", "Batch Finalization", "MOD_DECIM")
            if final is not None:
                preparation = draw_collapsible_box(final, settings, 'phase2_show_lods_rename', 'Prepare LODs / Rename', 'MOD_DECIM')
                if preparation is not None:
                    config = preparation.column(align=True)
                    config.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                    config.prop(settings, "phase2_final_lods")
                    engine = config.row()
                    engine.enabled = settings.phase2_final_lods
                    engine.prop(settings, "phase2_final_lod_engine", expand=True)
                    config.prop(settings, "phase2_final_rename")
                    engine = config.row()
                    engine.enabled = settings.phase2_final_rename
                    engine.prop(settings, "phase2_final_rename_engine", expand=True)
                    cleanup = config.row()
                    cleanup.enabled = settings.phase2_final_rename
                    cleanup.prop(settings, 'phase2_final_cleanup_generated')
                    config.operator("object.polygroups_batch_finalization", text="Execute Batch Finalization", icon="PLAY")
                    if settings.phase2_final_is_running:
                        preparation.operator("object.polygroups_stop_lod_job", icon="CANCEL")
                export = draw_collapsible_box(final, settings, 'phase2_show_export', 'Export Prepared Models', 'EXPORT')
                if export is not None:
                    controls = export.column(align=True)
                    controls.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                    controls.prop(settings, 'phase2_export_engine', expand=True)
                    row = controls.row(align=True)
                    for name in ('phase2_export_glb', 'phase2_export_gltf', 'phase2_export_fbx'):
                        row.prop(settings, name)
                    controls.prop(settings, 'phase2_export_sort')
                    controls.prop(settings, 'phase2_export_json')
                    final_settings = context.scene.polygroups_mesh_finalization_settings
                    if settings.phase2_export_engine == 'UNITY':
                        controls.prop(final_settings, 'unity_export_directory')
                        controls.prop(final_settings, 'unity_gltf_mode')
                        controls.prop(final_settings, 'unity_glb_mode')
                    else:
                        if settings.phase2_export_glb:
                            controls.prop(final_settings, 'unreal_glb_mode')
                        if settings.phase2_export_gltf:
                            controls.prop(final_settings, 'unreal_gltf_mode')
                    controls.operator('object.polygroups_phase2_export', text='Export', icon='EXPORT')
                    controls.operator('object.polygroups_phase2_export', text='Export Selected',
                                      icon='RESTRICT_SELECT_OFF').selected_only = True
                    controls.label(text=settings.phase2_export_status)
                blend_export = draw_collapsible_box(final, settings, 'phase2_show_export_blend', 'Export Blend Files', 'FILE_BLEND')
                if blend_export is not None:
                    controls = blend_export.column(align=True)
                    controls.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                    controls.prop(settings, 'phase2_blend_export_pack')
                    controls.prop(settings, 'phase2_blend_export_reset_y')
                    controls.prop(settings, 'phase2_blend_export_generated')
                    controls.label(text='One clean blend per *_Collection in !Blend', icon='INFO')
                    row = controls.row(align=True)
                    row.operator('object.polygroups_phase2_export_blend', text='Export Blend Files', icon='EXPORT')
                    row.operator('object.polygroups_phase2_open_blend_folder', text='', icon='FILE_FOLDER')
                    controls.operator('object.polygroups_phase2_export_blend', text='Export Selected Blend',
                                      icon='RESTRICT_SELECT_OFF').selected_only = True
                    controls.label(text=settings.phase2_blend_export_status)
                zbrush_export = draw_collapsible_box(final, settings, 'phase2_show_export_zbrush', 'Export ZBrush', 'MOD_MULTIRES')
                if zbrush_export is not None:
                    controls = zbrush_export.column(align=True)
                    controls.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                    controls.prop(settings, 'phase2_zbrush_directory')
                    if not settings.phase2_zbrush_directory:
                        controls.label(text='Default: !ZBrush beside the blend file', icon='INFO')
                    controls.prop(settings, 'phase2_zbrush_build', expand=True)
                    controls.prop(settings, 'phase2_zbrush_launch')
                    controls.prop(settings, 'phase2_zbrush_cleanup_on_success')
                    controls.label(text='Multires levels -> ZBrush subdiv levels | polygroups | one ZTL per mesh', icon='INFO')
                    controls.separator(type='LINE')
                    heading = controls.row()
                    heading.alignment = 'CENTER'
                    heading.label(text='--  Export  --')
                    row = controls.row(align=True)
                    row.operator('object.polygroups_phase2_export_zbrush', text='Export Active Mesh', icon='EXPORT').scope = 'ACTIVE'
                    row.operator('object.polygroups_phase2_export_zbrush', text='Export All Generated.N', icon='EXPORT').scope = 'ALL'
                    controls.separator(type='LINE')
                    heading = controls.row()
                    heading.alignment = 'CENTER'
                    heading.label(text='--  Delete  --')
                    controls.operator('object.polygroups_zbrush_delete_generated', text='Delete All Generated.N Collections + Meshes', icon='TRASH')
                    controls.operator('object.polygroups_zbrush_clear_obj', text='Delete Temporary OBJ Files', icon='TRASH')
                    controls.label(text=settings.phase2_zbrush_status)
                    extra = draw_collapsible_box(zbrush_export, settings, 'phase2_show_zbrush_folder_launch',
                        'Folder Export / Launch', 'FILE_FOLDER')
                    if extra is not None:
                        tools = extra.column(align=True)
                        tools.enabled = controls.enabled
                        tools.prop(settings, 'phase2_zbrush_blend_folder')
                        tools.operator('object.polygroups_phase2_export_zbrush_folder', text='Export Folder of Generated.N.blend', icon='FILE_FOLDER')
                        tools.separator(type='LINE')
                        row = tools.row(align=True)
                        row.operator('object.polygroups_phase2_launch_zbrush', text='Launch ZBrush', icon='PLAY')
                        row.operator('object.polygroups_phase2_open_zbrush_folder', text='', icon='FILE_FOLDER')
            auto = draw_collapsible_box(content, settings, "phase2_show_auto_render", "Auto Render", "RENDER_STILL")
            if auto is not None:
                config = auto.column(align=True)
                config.enabled = not (settings.phase2_pipeline_running or settings.phase2_is_running or settings.phase2_final_is_running or settings.phase2_auto_render_running or settings.batch_is_running)
                config.label(text="Quality and Output: 16:9 | 2K", icon="INFO")
                config.label(text="2048 x 1152 | Eevee")
                config.prop(context.scene.polygroups_render_settings, "output_directory")
                transparent = config.box()
                transparent.prop(settings, "phase2_auto_transparent")
                prefix = transparent.row()
                prefix.enabled = settings.phase2_auto_transparent
                prefix.prop(settings, "phase2_auto_scene_prefix")
                scene = config.box()
                scene.prop(settings, "phase2_auto_scene")
                sub = scene.column(align=True)
                sub.enabled = settings.phase2_auto_scene
                sub.prop(settings, "phase2_auto_camera")
                sub.label(text="Replace foreign studio / reset managed studio")
                selection = config.box()
                selection.prop(settings, "phase2_auto_selection")
                selection.label(text="MID + LOD0 (LOW previews)")
                freestyle = config.box()
                freestyle.prop(settings, "phase2_auto_freestyle")
                sub = freestyle.column(align=True)
                sub.enabled = settings.phase2_auto_freestyle
                sub.prop(settings, "phase2_auto_freestyle_pass")
                sub.prop(settings, "phase2_auto_freestyle_color")
                multiview = config.box()
                multiview.prop(settings, "phase2_auto_multiview")
                sub = multiview.column(align=True)
                sub.enabled = settings.phase2_auto_multiview
                sub.prop(settings, "phase2_auto_mv_offset")
                sub.prop(settings, "phase2_auto_mv_angle", expand=True)
                sub.prop(settings, "phase2_auto_mv_hero")
                textures = config.box()
                textures.prop(settings, "phase2_auto_textures")
                sub = textures.column(align=True)
                sub.enabled = settings.phase2_auto_textures
                sub.prop(settings, "phase2_auto_texture_prepare", expand=True)
                sub.label(text="Base Color + Normal | Texture Render Mode: Together")
                config.operator("object.polygroups_phase2_auto_render", text="Start Render", icon="RENDER_STILL")
                if settings.phase2_auto_render_running:
                    auto.operator("object.polygroups_stop_lod_job", text="Stop Render", icon="CANCEL")
            group = draw_collapsible_box(content, settings, "phase2_show_status",
                t(context, "phase2_processing_status"), "INFO")
            if group is not None:
                if settings.phase2_status:
                    group.separator(type="LINE")
                    group.label(text=settings.phase2_status, icon="INFO")
                if settings.phase2_final_is_running or settings.phase2_auto_render_running or settings.phase2_final_progress:
                    group.progress(factor=settings.phase2_final_progress / 100, type='BAR', text=f'{settings.phase2_final_progress:.0f}%')
                if settings.phase2_total_count:
                    group.progress(
                        factor=(settings.phase2_done_count + settings.phase2_failed_count) / settings.phase2_total_count,
                        type="BAR", text=t(context, "phase2_progress", done=settings.phase2_done_count,
                                           failed=settings.phase2_failed_count, total=settings.phase2_total_count),
                    )
                if settings.phase2_is_running:
                    group.operator("object.polygroups_phase2_stop", text=t(context, "phase2_stop"), icon="PAUSE")
                if settings.phase2_final_is_running or settings.phase2_auto_render_running:
                    group.operator("object.polygroups_stop_lod_job", icon="CANCEL")

            manager = draw_collapsible_box(content, settings, "phase2_show_files",
                t(context, "phase2_file_manager"), "FILE_BLEND")
            if manager is not None:
                buttons = manager.column(align=True)
                buttons.enabled = not settings.phase2_pipeline_running and not settings.phase2_is_running and not settings.phase2_final_is_running and not settings.phase2_auto_render_running and not settings.batch_is_running
                buttons.operator("object.polygroups_phase2_files_scan", icon="VIEWZOOM")
                buttons.prop(settings, "phase2_files_cleanup")
                move = buttons.row()
                move.enabled = settings.phase2_files_found > 0
                move.operator("object.polygroups_phase2_files_move", icon="FILE_FOLDER")
                manager.label(text=settings.phase2_files_status, icon="INFO")
                if settings.phase2_files_cleanup_status:
                    manager.label(text=settings.phase2_files_cleanup_status)

        content = draw_topic(layout, context, "batch_4", t(context, "import_group_progress"), "INFO")
        if content is not None:
            draw_import_progress(content, context, settings)


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
        content = draw_topic(layout, context, "remesh_0", 'Remesh Controls', "MOD_REMESH")
        if content is not None:
            self.draw_remesh_controls(context, content)
        content = draw_topic(layout, context, "remesh_1", 'Remesh Progress', "INFO")
        if content is not None:
            self.draw_remesh_progress(context, content)

    def draw_remesh_controls(self, context, layout):
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

        status = context.scene.polygroups_remesh_status
        content = layout
        if content is not None:
            content = content.column()
            content.enabled = not status.is_running and not context.scene.polygroups_model_preparation_settings.batch_is_running
            content.operator(
                "object.polygroups_checked_quad_remesh",
                text=t(context, "remesh_it"),
                icon="MOD_REMESH",
            )

            preset_row = content.row(align=True)
            remesh_row = content.row(align=True)
            for label, quad_count in get_remesh_preset_counts(context):
                preset = preset_row.operator(
                    "object.polygroups_set_quad_count_preset", text=label,
                )
                preset.quad_count = quad_count
                remesh = remesh_row.operator(
                    "object.polygroups_checked_quad_remesh", text=f"Remesh {label}",
                )
                remesh.quad_count = quad_count

            content.prop(qremesher, "target_count", text=t(context, "quad_count"))
            content.prop(qremesher, "use_materials", text=t(context, "use_materials"))
            content.prop(context.scene.polygroups_model_preparation_settings,
                         "remesh_pregenerate_polygroups", text="Pregenerate Poly Groups")
            content.prop(context.scene.polygroups_model_preparation_settings,
                         "remesh_auto_generate_seams", text="Auto Generate Seams")
            content.prop(context.scene.polygroups_model_preparation_settings,
                         "remesh_auto_unwrap_checker", text="Auto Unwrap and Apply Checker")

            symmetry_row = content.row(align=True)
            symmetry_row.label(text=t(context, "symmetry"))
            symmetry_row.prop(qremesher, "symmetry_x")

            if status.is_running:
                content.operator("object.polygroups_cancel_remesh", text=t(context, "import_cancel"), icon="CANCEL")

    def draw_remesh_progress(self, context, content):
        status = context.scene.polygroups_remesh_status
        if content is not None:
            progress_box = content.column(align=True)
            if status.stage:
                progress_box.label(text=t(context, "remesh_stage_" + status.stage))
                progress_box.label(text=t(context, "remesh_source", value=status.source_name))
                progress_box.progress(factor=status.progress / 100, type="BAR", text=f"{status.progress:.1f}%")
                progress_box.label(text=t(context, "remesh_elapsed", value=format_duration(status.elapsed_seconds)))
                if status.stage == "DONE":
                    progress_box.label(text=t(context, "remesh_completed_polygons", value=f"{status.polygon_count:,}"), icon="CHECKMARK")
                    progress_box.label(text=status.result_name)
                elif status.message:
                    progress_box.label(text=status.message, icon="ERROR" if status.stage == "FAILED" else "INFO")
            else:
                progress_box.label(text=t(context, "import_group_progress"), icon="INFO")
