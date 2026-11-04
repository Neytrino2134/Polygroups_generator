"""Smart LODs presets: add the current LOD count / budgets as a preset, overwrite the active one, remove it."""
import bpy
from bpy.app.handlers import persistent

from ..core import smart_lod_presets as presets


@persistent
def seed_presets(*_args):
    """Give every scene the default Unreal / Unity presets once."""
    for scene in bpy.data.scenes:
        settings = getattr(scene, "polygroups_mesh_finalization_settings", None)
        if settings is not None and presets.seed(settings):
            engine = scene.polygroups_model_preparation_settings.phase2_run_engine
            name = presets.preset_name_for_engine(engine)
            if presets.find(settings, name) is not None:
                # Select it without applying: values already in the blend stay as they are.
                settings["smart_lods_preset_active"] = name
    return None


class OBJECT_OT_polygroups_smart_lods_preset(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_lods_preset"
    bl_label = "Smart LODs Preset"
    bl_description = "Add, save to the active, or remove a Smart LODs preset"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(items=(
        ("ADD", "Add", "Add the current LOD count and budgets as a new preset"),
        ("SAVE", "Save", "Overwrite the active preset with the current LOD count and budgets"),
        ("REMOVE", "Remove", "Remove the active preset"),
    ))
    name: bpy.props.StringProperty(name="Name", default="New Preset")

    @classmethod
    def poll(cls, context):
        return not context.scene.polygroups_mesh_finalization_settings.smart_lods_is_running

    def invoke(self, context, event):
        if self.action == "ADD":
            return context.window_manager.invoke_props_dialog(self, width=300, confirm_text="Add Preset")
        return self.execute(context)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        presets.seed(settings)
        count, targets = presets.read_current(settings)
        if self.action == "ADD":
            name = self.name.strip()
            if not name:
                self.report({"ERROR"}, "Enter a preset name")
                return {"CANCELLED"}
            if presets.find(settings, name) is not None:
                self.report({"ERROR"}, f"Preset '{name}' already exists; select it and use Save")
                return {"CANCELLED"}
            presets.write(settings.smart_lods_presets.add(), name, count, targets)
            settings.smart_lods_preset_active = name
            return {"FINISHED"}
        active = presets.find(settings, settings.smart_lods_preset_active)
        if active is None:
            self.report({"ERROR"}, "Select a Smart LODs preset first")
            return {"CANCELLED"}
        if self.action == "SAVE":
            presets.write(active, active.name, count, targets)
            self.report({"INFO"}, f"Saved '{active.name}': {count} LOD(s)")
            return {"FINISHED"}
        index = list(settings.smart_lods_presets).index(active)
        settings.smart_lods_presets.remove(index)
        settings.smart_lods_preset_active = ""
        return {"FINISHED"}


CLASSES = (OBJECT_OT_polygroups_smart_lods_preset,)
