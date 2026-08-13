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
        column.prop(settings, "weld_distance")
        column.operator("object.polygroups_apply_weld", icon="AUTOMERGE_ON")


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
    VIEW3D_PT_polygroups_tools,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
