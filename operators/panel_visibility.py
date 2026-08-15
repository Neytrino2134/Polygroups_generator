import bpy


SECTION_VISIBILITY_PROPERTIES = (
    "show_import_section",
    "show_batch_import_section",
    "show_model_preparation_section",
    "show_seam_preparation_section",
    "show_polygroups_section",
    "show_remesh_section",
    "show_resculpting_section",
    "show_seam_finalization_section",
    "show_uv_preparation_section",
    "show_baking_section",
    "show_ai_generation_section",
)


class OBJECT_OT_airetopo_set_all_section_visibility(bpy.types.Operator):
    bl_idname = "object.airetopo_set_all_section_visibility"
    bl_label = "Set All Section Visibility"
    bl_description = "Expand or collapse all AI Retopo Toolkit sections"
    bl_options = {"REGISTER", "UNDO"}

    visible: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        settings = context.scene.airetopo_panel_visibility_settings
        for property_name in SECTION_VISIBILITY_PROPERTIES:
            setattr(settings, property_name, self.visible)

        self.report({"INFO"}, "Sections expanded" if self.visible else "Sections collapsed")
        return {"FINISHED"}
