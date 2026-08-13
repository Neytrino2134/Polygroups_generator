import bpy

from ..core.materials import clear_materials


class OBJECT_OT_clear_polygroups_materials(bpy.types.Operator):
    bl_idname = "object.clear_polygroups_materials"
    bl_label = "Clear Materials"
    bl_description = "Clear material slots from the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.active_object

        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        clear_materials(obj)
        self.report({"INFO"}, "Cleared material slots")
        return {"FINISHED"}
