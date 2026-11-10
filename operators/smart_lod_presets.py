"""Smart LODs presets: add the current LOD count / budgets as a preset, overwrite the active one, remove it."""
import bpy
from bpy.app.handlers import persistent

from ..core import smart_lod_presets as presets


@persistent
def seed_presets(*_args):
    """Load the global library into every scene after opening a blend."""
    document = None
    for scene in bpy.data.scenes:
        settings = getattr(scene, "polygroups_mesh_finalization_settings", None)
        if settings is None:
            continue
        try:
            document = presets.synchronize(settings)
        except (OSError, ValueError) as error:
            print(f'Smart LODs preset library: {error}')
            presets.seed(settings)
        if not presets.find(settings, settings.smart_lods_preset_active):
            engine = scene.polygroups_model_preparation_settings.phase2_run_engine
            name = presets.preset_name_for_engine(engine)
            if presets.find(settings, name) is not None:
                # Select it without applying: values already in the blend stay as they are.
                settings["smart_lods_preset_active"] = name
    if document is not None:
        # A later scene may contribute legacy presets missing from earlier scenes.
        presets.refresh_scenes(document['presets'])
    return None


class OBJECT_OT_polygroups_smart_lods_preset(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_lods_preset"
    bl_label = "Smart LODs Preset"
    bl_description = "Add, save or remove a global Smart LODs preset shared by all blend files"
    bl_options = {"REGISTER"}

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
        try:
            return self.save_preset(context)
        except (OSError, ValueError) as error:
            self.report({"ERROR"}, f'Cannot save global Smart LODs presets: {error}')
            return {"CANCELLED"}

    def save_preset(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        presets.synchronize(settings)
        count, targets = presets.read_current(settings)
        if self.action == "ADD":
            name = self.name.strip()
            if not name:
                self.report({"ERROR"}, "Enter a preset name")
                return {"CANCELLED"}
            if presets.find(settings, name) is not None:
                self.report({"ERROR"}, f"Preset '{name}' already exists; select it and use Save")
                return {"CANCELLED"}
            presets.save_global(settings, name, count, targets)
            settings.smart_lods_preset_active = name
            return {"FINISHED"}
        active = presets.find(settings, settings.smart_lods_preset_active)
        if active is None:
            self.report({"ERROR"}, "Select a Smart LODs preset first")
            return {"CANCELLED"}
        if self.action == "SAVE":
            name = active.name
            presets.save_global(settings, name, count, targets)
            self.report({"INFO"}, f"Saved globally '{name}': {count} LOD(s)")
            return {"FINISHED"}
        presets.save_global(settings, active.name, remove=True)
        settings.smart_lods_preset_active = ""
        return {"FINISHED"}


CLASSES = (OBJECT_OT_polygroups_smart_lods_preset,)
