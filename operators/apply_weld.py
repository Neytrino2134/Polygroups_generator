import bpy


class OBJECT_OT_polygroups_apply_weld(bpy.types.Operator):
    bl_idname = "object.polygroups_apply_weld"
    bl_label = "Apply Weld"
    bl_description = "Add or update a Weld modifier on selected mesh objects"
    bl_options = {"REGISTER", "UNDO"}

    modifier_name = "Retopo Weld"

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        mesh_objects = [obj for obj in context.selected_objects if obj.type == "MESH"]

        if not mesh_objects:
            self.report({"WARNING"}, "Select at least one mesh object")
            return {"CANCELLED"}

        for obj in mesh_objects:
            modifier = obj.modifiers.get(self.modifier_name)
            if modifier is None or modifier.type != "WELD":
                modifier = obj.modifiers.new(self.modifier_name, "WELD")

            modifier.merge_threshold = settings.weld_distance

        self.report(
            {"INFO"},
            f"Updated Weld modifier on {len(mesh_objects)} mesh object(s)",
        )
        return {"FINISHED"}
