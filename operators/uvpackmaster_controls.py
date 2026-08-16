import bpy


class OBJECT_OT_polygroups_uvpackmaster_pack(bpy.types.Operator):
    bl_idname = "object.polygroups_uvpackmaster_pack"
    bl_label = "PACK"
    bl_description = "Run UVPackmaster Pack with a safe heuristic max wait time"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not hasattr(context.scene, "uvpm4_props"):
            self.report({"ERROR"}, "UVPackmaster 4 properties were not found.")
            return {"CANCELLED"}

        main_props = context.scene.uvpm4_props.default_main_props
        if hasattr(main_props, "heuristic_max_wait_time") and main_props.heuristic_max_wait_time <= 0:
            main_props.heuristic_max_wait_time = 3

        return bpy.ops.uvpackmaster4.pack(
            "INVOKE_DEFAULT",
            mode_id="__active__",
            pack_op_type="0",
        )
