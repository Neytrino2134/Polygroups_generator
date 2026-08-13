import bpy


class VIEW3D_PT_polygroups_generator(bpy.types.Panel):
    bl_label = "PolyGroups Generator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"

    def draw(self, context):
        self.layout.label(text="Retopology tools for generated meshes")


class VIEW3D_PT_polygroups_model_preparation(bpy.types.Panel):
    bl_label = "Model Preparation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings

        column = layout.column(align=True)
        column.operator("object.polygroups_rename_objects", icon="OUTLINER_COLLECTION")
        column.separator()
        column.prop(settings, "weld_distance")
        column.operator("object.polygroups_apply_weld", icon="AUTOMERGE_ON")


class VIEW3D_PT_polygroups_import(bpy.types.Panel):
    bl_label = "Import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings

        files_box = layout.box()
        files_box.label(text="Import Files", icon="FILE_FOLDER")
        files_box.prop(settings, "batch_import_format")
        files_box.prop(settings, "file_import_auto_rename_objects")
        files_box.prop(settings, "file_import_apply_weld")

        files_row = files_box.row(align=True)
        files_row.enabled = not settings.batch_is_running
        file_operator = files_row.operator(
            "object.polygroups_batch_import",
            text="Import Files",
            icon="FILE_FOLDER",
        )
        file_operator.use_file_selection = True


class VIEW3D_PT_polygroups_batch_import(bpy.types.Panel):
    bl_label = "Batch Import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings

        folder_row = layout.row(align=True)
        folder_row.label(text="Folder:")
        folder_row.operator("object.polygroups_select_import_folder", text="", icon="FILE_FOLDER")

        folder_path = settings.batch_import_directory or "No folder selected"
        layout.label(text=folder_path, icon="FILE_FOLDER")
        layout.prop(settings, "batch_import_format")
        layout.prop(settings, "batch_auto_rename_objects")
        layout.prop(settings, "batch_apply_weld")

        progress_column = layout.column(align=True)
        progress_column.enabled = False
        progress_column.prop(settings, "batch_import_progress", slider=True)
        progress_column.label(text=f"Total Files: {settings.batch_total_count}")
        progress_column.label(text=f"Imported Files: {settings.batch_imported_count}")
        progress_column.label(text=f"Imported Objects: {settings.batch_imported_object_count}")
        progress_column.label(text=f"Remaining Files: {settings.batch_remaining_count}")
        if settings.batch_current_file:
            progress_column.label(text=f"Current: {settings.batch_current_file}")

        scan_row = layout.row(align=True)
        scan_row.enabled = not settings.batch_is_running
        scan_row.operator("object.polygroups_scan_import_folder", icon="VIEWZOOM")

        operator_row = layout.row(align=True)
        operator_row.enabled = not settings.batch_is_running
        operator_row.operator(
            "object.polygroups_batch_import",
            text="Import Folder",
            icon="FILE_REFRESH",
        )


class VIEW3D_PT_polygroups_tools(bpy.types.Panel):
    bl_label = "PolyGroups"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)
        column.operator("object.generate_polygroups", icon="MATERIAL")
        column.operator("object.face_sets_to_materials", icon="SHADING_TEXTURE")
        column.operator("object.clear_polygroups_materials", icon="TRASH")

        layout.separator()

        settings = context.scene.polygroups_knife_seam_settings
        box = layout.box()
        box.label(text="Knife Seam", icon="MOD_BEVEL")
        box.prop(settings, "xray")
        box.prop(settings, "use_occlude_geometry")
        box.prop(settings, "only_selected")
        box.prop(settings, "mark_seam")
        box.prop(settings, "clear_selection_after_cutting")

        operator = box.operator("mesh.polygroups_knife_seam", icon="SCULPTMODE_HLT")
        operator.xray = settings.xray
        operator.use_occlude_geometry = settings.use_occlude_geometry
        operator.only_selected = settings.only_selected
        operator.mark_seam = settings.mark_seam
        operator.clear_selection_after_cutting = settings.clear_selection_after_cutting

        quick_settings = context.scene.polygroups_quick_knife_seam_settings
        quick_box = layout.box()
        quick_box.label(text="Quick Knife Seam", icon="MOD_BEVEL")
        quick_box.prop(quick_settings, "use_fill")
        quick_box.prop(quick_settings, "threshold")
        quick_box.prop(quick_settings, "mark_seam")
        quick_box.prop(quick_settings, "clear_selection_after_cutting")

        quick_operator = quick_box.operator(
            "mesh.polygroups_quick_knife_seam",
            icon="MOD_BEVEL",
        )
        quick_operator.use_fill = quick_settings.use_fill
        quick_operator.threshold = quick_settings.threshold
        quick_operator.mark_seam = quick_settings.mark_seam
        quick_operator.clear_selection_after_cutting = quick_settings.clear_selection_after_cutting


CLASSES = (
    VIEW3D_PT_polygroups_generator,
    VIEW3D_PT_polygroups_model_preparation,
    VIEW3D_PT_polygroups_import,
    VIEW3D_PT_polygroups_batch_import,
    VIEW3D_PT_polygroups_tools,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
