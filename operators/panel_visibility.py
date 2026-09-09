import bpy

from ..properties import SECTION_VISIBILITY_PROPERTIES


PANEL_SETTINGS_GROUPS = (
    "polygroups_model_preparation_settings",
    "polygroups_knife_seam_settings",
    "polygroups_seam_preparation_settings",
    "polygroups_quick_knife_seam_settings",
    "polygroups_object_seam_cutter_settings",
    "polygroups_generator_settings",
    "polygroups_seam_finalization_settings",
    "polygroups_mesh_finalization_settings",
    "polygroups_render_settings",
    "polygroups_baking_settings",
    "polygroups_resculpting_settings",
    "airetopo_ai_generation_settings",
    "airetopo_google_image_settings",
)


def restore_panel_defaults(scene):
    """Unset saved values so Blender restores every add-on RNA default."""
    reset_count = 0
    for group_name in PANEL_SETTINGS_GROUPS:
        settings = getattr(scene, group_name, None)
        if settings is None:
            continue
        for prop in settings.bl_rna.properties:
            if prop.identifier == "rna_type" or prop.is_readonly:
                continue
            if prop.identifier in settings:
                settings.property_unset(prop.identifier)
                reset_count += 1
    return reset_count


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


class OBJECT_OT_airetopo_restore_panel_defaults(bpy.types.Operator):
    bl_idname = "object.airetopo_restore_panel_defaults"
    bl_label = "Restore Defaults"
    bl_description = "Restore all AI Retopo parameter defaults across sections 1 through 13"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        reset_count = restore_panel_defaults(context.scene)
        self.report({"INFO"}, f"Restored {reset_count} saved setting values to defaults")
        return {"FINISHED"}
