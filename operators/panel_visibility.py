import bpy

from ..properties import SECTION_VISIBILITY_PROPERTIES


class OBJECT_OT_airetopo_set_all_section_visibility(bpy.types.Operator):
    bl_idname = "object.airetopo_set_all_section_visibility"
    bl_label = "Set All Section Visibility"
    bl_description = "Expand or collapse all AI Retopo Toolkit sections"
    bl_options = {"REGISTER", "UNDO"}

    visible: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        settings = context.scene.airetopo_panel_visibility_settings
        if self.visible:
            settings.single_section_mode = False

        for property_name in SECTION_VISIBILITY_PROPERTIES:
            setattr(settings, property_name, self.visible)

        self.report({"INFO"}, "Sections expanded" if self.visible else "Sections collapsed")
        return {"FINISHED"}
