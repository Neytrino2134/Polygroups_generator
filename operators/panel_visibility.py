import bpy

from ..properties import SECTION_SUBSECTION_PROPERTIES
from ..properties import SECTION_VISIBILITY_PROPERTIES
from ..properties import SUBSECTION_VISIBILITY_PROPERTIES


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


def set_all_section_visibility(settings, visible):
    """Advance the shared two-stage main-section/subsection visibility state."""
    if visible:
        if not all(getattr(settings, name) for name in SECTION_VISIBILITY_PROPERTIES):
            settings.single_section_mode = False
            for property_name in SECTION_VISIBILITY_PROPERTIES:
                setattr(settings, property_name, True)
            return "Sections expanded"

        for property_name in SUBSECTION_VISIBILITY_PROPERTIES:
            setattr(settings, property_name, True)
        return "Subsections expanded"

    if any(getattr(settings, name) for name in SUBSECTION_VISIBILITY_PROPERTIES):
        for property_name in SUBSECTION_VISIBILITY_PROPERTIES:
            setattr(settings, property_name, False)
        return "Subsections collapsed"

    for property_name in SECTION_VISIBILITY_PROPERTIES:
        setattr(settings, property_name, False)
    return "Sections collapsed"


class OBJECT_OT_airetopo_set_all_section_visibility(bpy.types.Operator):
    bl_idname = "object.airetopo_set_all_section_visibility"
    bl_label = "Set All Section Visibility"
    bl_description = "Expand or collapse all AI Retopo Toolkit sections"
    bl_options = {"REGISTER", "UNDO"}

    visible: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        settings = context.scene.airetopo_panel_visibility_settings
        self.report({"INFO"}, set_all_section_visibility(settings, self.visible))
        return {"FINISHED"}


class OBJECT_OT_airetopo_set_section_subsection_visibility(bpy.types.Operator):
    bl_idname = "object.airetopo_set_section_subsection_visibility"
    bl_label = "Set Section Subsection Visibility"
    bl_description = "Expand or collapse every subsection in this section"
    bl_options = {"REGISTER", "UNDO"}

    section_property: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    visible: bpy.props.BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        property_names = SECTION_SUBSECTION_PROPERTIES.get(self.section_property)
        if not property_names:
            self.report({"WARNING"}, "This section has no collapsible subsections")
            return {"CANCELLED"}

        settings = context.scene.airetopo_panel_visibility_settings
        for property_name in property_names:
            setattr(settings, property_name, self.visible)
        self.report({"INFO"}, "Subsections expanded" if self.visible else "Subsections collapsed")
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
