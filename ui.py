import bpy


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


class VIEW3D_PT_polygroups_generator(bpy.types.Panel):
    bl_label = "PolyGroups Generator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_order = 0

    def draw(self, context):
        self.layout.label(text="Retopology tools for generated meshes")


class VIEW3D_PT_polygroups_model_preparation(bpy.types.Panel):
    bl_label = "03 | Model Preparation"
    bl_icon = "AUTOMERGE_ON"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 3
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout.box()
        settings = context.scene.polygroups_model_preparation_settings

        column = layout.column(align=True)
        column.operator("object.polygroups_rename_objects", icon="OUTLINER_COLLECTION")
        column.separator()
        column.prop(settings, "weld_distance")
        column.operator("object.polygroups_apply_weld", icon="AUTOMERGE_ON")


class VIEW3D_PT_polygroups_import(bpy.types.Panel):
    bl_label = "01 | Import"
    bl_icon = "FILE_FOLDER"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
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
            text="Import Files",
            icon="FILE_FOLDER",
        )
        file_operator.use_file_selection = True

        files_box.separator()
        files_box.prop(settings, "batch_import_format")
        files_box.prop(settings, "file_import_auto_rename_objects")
        files_box.prop(settings, "file_import_apply_weld")


class VIEW3D_PT_polygroups_batch_import(bpy.types.Panel):
    bl_label = "02 | Batch Import"
    bl_icon = "FILE_REFRESH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 2
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout.box()
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


class VIEW3D_PT_polygroups_remesh(bpy.types.Panel):
    bl_label = "06 | Remesh"
    bl_icon = "MOD_REMESH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 6
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout.box()
        installed, enabled, available = quad_remesher_status(context)

        if not installed:
            layout.label(text="Quad Remesher add-on is not installed.", icon="ERROR")
            layout.label(text="Install it to use these controls.")
            return

        if not enabled or not available:
            layout.label(text="Quad Remesher add-on is installed but not enabled.", icon="ERROR")
            layout.label(text="Enable it in Blender Preferences.")
            return

        qremesher = context.scene.qremesher

        layout.label(text="Uses the installed Quad Remesher add-on.", icon="CHECKMARK")
        layout.operator("object.polygroups_checked_quad_remesh", icon="MOD_REMESH")
        layout.prop(qremesher, "target_count")
        layout.prop(qremesher, "use_materials")

        symmetry_row = layout.row(align=True)
        symmetry_row.label(text="Symmetry:")
        symmetry_row.prop(qremesher, "symmetry_x")


class VIEW3D_PT_polygroups_seam_preparation(bpy.types.Panel):
    bl_label = "04 | Seam Preparation"
    bl_icon = "EDGE_SEAM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 4
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout
        seam_settings = context.scene.polygroups_seam_preparation_settings

        tools_box = layout.box()
        tools_column = tools_box.column(align=True)
        tools_column.prop(seam_settings, "selection_smooth_iterations")

        smooth_operator = tools_column.operator(
            "mesh.polygroups_smooth_face_selection",
            icon="MOD_SMOOTH",
        )
        smooth_operator.iterations = seam_settings.selection_smooth_iterations

        tools_column.operator(
            "mesh.polygroups_mark_selected_edges_seam",
            icon="EDGESEL",
        )
        tools_column.operator(
            "mesh.polygroups_mark_selection_boundary_seam",
            icon="EDGESEL",
        )

        layout.separator()
        knife_content = draw_collapsible_box(
            layout,
            seam_settings,
            "show_knife_seam_settings",
            "Knife Seam",
            "MOD_BEVEL",
        )
        if knife_content is not None:
            self.draw_knife_seam(context, knife_content)

        quick_knife_content = draw_collapsible_box(
            layout,
            seam_settings,
            "show_quick_knife_seam_settings",
            "Quick Knife Seam",
            "MOD_BEVEL",
        )
        if quick_knife_content is not None:
            self.draw_quick_knife_seam(context, quick_knife_content)

        object_cutter_content = draw_collapsible_box(
            layout,
            seam_settings,
            "show_object_seam_cutter_settings",
            "Object Seam Cutter",
            "MESH_PLANE",
        )
        if object_cutter_content is not None:
            self.draw_object_seam_cutter(context, object_cutter_content)

    def draw_knife_seam(self, context, layout):
        settings = context.scene.polygroups_knife_seam_settings

        layout.prop(settings, "stable_view_cut")
        layout.prop(settings, "xray")
        layout.prop(settings, "use_occlude_geometry")
        layout.prop(settings, "only_selected")
        layout.prop(settings, "mark_seam")
        layout.prop(settings, "clear_selection_after_cutting")

        tool_operator = layout.operator(
            "mesh.polygroups_select_seam_tool",
            text="Select Knife Seam Tool",
            icon="SCULPTMODE_HLT",
        )
        tool_operator.tool_id = "polygroups_generator.knife_seam_tool"

    def draw_quick_knife_seam(self, context, layout):
        quick_settings = context.scene.polygroups_quick_knife_seam_settings

        layout.prop(quick_settings, "use_fill")
        layout.prop(quick_settings, "threshold")
        layout.prop(quick_settings, "mark_seam")
        layout.prop(quick_settings, "clear_selection_after_cutting")

        tool_operator = layout.operator(
            "mesh.polygroups_select_seam_tool",
            text="Select Quick Knife Seam Tool",
            icon="MOD_BEVEL",
        )
        tool_operator.tool_id = "polygroups_generator.quick_knife_seam_tool"

    def draw_object_seam_cutter(self, context, layout):
        settings = context.scene.polygroups_object_seam_cutter_settings

        layout.prop(settings, "cutter_size_multiplier")
        layout.prop(settings, "cutter_arc_segments")
        layout.prop(settings, "cutter_alpha")
        layout.prop(settings, "cutter_solidify_thickness")
        layout.prop(settings, "hide_cutters_after_apply")
        layout.prop(settings, "delete_cutters_after_apply")

        layout.separator()
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text="Select Draw Cutter Plane Tool",
            icon="MESH_PLANE",
        )
        tool_operator.name = "polygroups_generator.draw_cutter_plane_tool"
        layout.operator(
            "object.polygroups_draw_cutter_plane",
            icon="MESH_PLANE",
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text="Select Draw Cutter Arc Tool",
            icon="CURVE_BEZCURVE",
        )
        tool_operator.name = "polygroups_generator.draw_cutter_arc_tool"
        layout.operator(
            "object.polygroups_draw_cutter_arc",
            icon="CURVE_BEZCURVE",
        )
        layout.operator(
            "object.polygroups_apply_cutter_seams",
            icon="MOD_BOOLEAN",
        )

        utility_row = layout.row(align=True)
        utility_row.operator(
            "object.polygroups_select_cutter_planes",
            text="Select",
            icon="RESTRICT_SELECT_OFF",
        )
        utility_row.operator(
            "object.polygroups_clear_cutter_planes",
            text="Clear",
            icon="TRASH",
        )

        if settings.last_cutter_count or settings.last_marked_edge_count:
            layout.separator()
            layout.label(text=f"Last Cutters: {settings.last_cutter_count}")
            layout.label(text=f"Last Seam Edges: {settings.last_marked_edge_count}")


class VIEW3D_PT_polygroups_tools(bpy.types.Panel):
    bl_label = "05 | PolyGroups"
    bl_icon = "MATERIAL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_order = 5
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout.box()
        settings = context.scene.polygroups_generator_settings
        column = layout.column(align=True)
        column.prop(settings, "material_mode", expand=True)
        column.separator()
        column.operator("object.generate_polygroups", icon="MATERIAL")
        column.operator(
            "mesh.polygroups_mark_material_boundaries_seam",
            icon="EDGE_SEAM",
        )
        column.operator(
            "object.polygroups_unwrap_angle_based",
            icon="UV",
        )
        column.separator()
        column.operator("object.face_sets_to_materials", icon="SHADING_TEXTURE")
        column.operator("object.clear_polygroups_materials", icon="TRASH")


class VIEW3D_PT_polygroups_baking(bpy.types.Panel):
    bl_label = "08 | Baking"
    bl_icon = "RENDER_STILL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 8
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout.box()
        settings = context.scene.polygroups_baking_settings

        column = layout.column(align=True)
        column.prop(settings, "bake_resolution")
        column.prop(settings, "bake_margin")
        column.prop(settings, "ray_distance")
        column.prop(settings, "cage_extrusion")
        column.prop(settings, "image_prefix")
        column.prop(settings, "use_selected_to_active")

        pass_row = column.row(align=True)
        pass_row.prop(settings, "bake_base_color")
        pass_row.prop(settings, "bake_normal")

        column.separator()
        column.operator(
            "object.polygroups_prepare_highpoly_bake_materials",
            icon="MATERIAL",
        )
        column.operator(
            "object.polygroups_prepare_lowpoly_bake_material",
            icon="TEXTURE",
        )
        column.operator(
            "object.polygroups_bake_selected_to_active",
            icon="RENDER_STILL",
        )
        column.separator()
        column.operator(
            "object.polygroups_prepare_and_bake",
            icon="RENDER_RESULT",
        )


class VIEW3D_PT_polygroups_resculpting(bpy.types.Panel):
    bl_label = "07 | Resculpting"
    bl_icon = "MOD_MULTIRES"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PolyGroups"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 7
    draw_header = draw_section_header_icon

    def draw(self, context):
        layout = self.layout.box()
        settings = context.scene.polygroups_resculpting_settings

        column = layout.column(align=True)
        column.prop(settings, "multires_levels")
        column.prop(settings, "shrinkwrap_limit")
        column.prop(settings, "shrinkwrap_offset")

        column.separator()
        column.operator(
            "object.polygroups_setup_resculpting",
            icon="MOD_MULTIRES",
        )

        row = column.row(align=True)
        row.operator(
            "object.polygroups_add_multires",
            text="Multires",
            icon="MOD_MULTIRES",
        )
        row.operator(
            "object.polygroups_add_shrinkwrap_to_highpoly",
            text="Shrinkwrap",
            icon="MOD_SHRINKWRAP",
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
    VIEW3D_PT_polygroups_baking,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
