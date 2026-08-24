import bpy


class OBJECT_OT_polygroups_uvpackmaster_pack(bpy.types.Operator):
    bl_idname = "object.polygroups_uvpackmaster_pack"
    bl_label = "PACK"
    bl_description = "Run UVPackmaster Pack with a safe heuristic max wait time"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        if not hasattr(context.scene, "uvpm4_props"):
            self.report({"ERROR"}, "UVPackmaster 4 properties were not found.")
            return {"CANCELLED"}

        obj = context.active_object
        context.view_layer.objects.active = obj
        if obj.mode != "EDIT":
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action="SELECT")

        main_props = context.scene.uvpm4_props.default_main_props
        if hasattr(main_props, "heuristic_max_wait_time") and main_props.heuristic_max_wait_time <= 0:
            main_props.heuristic_max_wait_time = 3

        return bpy.ops.uvpackmaster4.pack(
            "INVOKE_DEFAULT",
            mode_id="__active__",
            pack_op_type="0",
        )
