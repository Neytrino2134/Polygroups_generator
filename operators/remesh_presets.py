import bpy


class OBJECT_OT_polygroups_set_quad_count_preset(bpy.types.Operator):
    bl_idname = "object.polygroups_set_quad_count_preset"
    bl_label = "Set Quad Count"
    bl_description = "Set Quad Remesher target quad count"
    bl_options = {"REGISTER", "UNDO"}

    quad_count: bpy.props.IntProperty(
        name="Quad Count",
        default=3000,
        min=1,
    )

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "qremesher")

    def execute(self, context):
        context.scene.qremesher.target_count = self.quad_count
        self.report({"INFO"}, f"Quad Count set to {self.quad_count}")
        return {"FINISHED"}
