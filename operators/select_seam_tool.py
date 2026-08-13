import bpy


class MESH_OT_polygroups_select_seam_tool(bpy.types.Operator):
    bl_idname = "mesh.polygroups_select_seam_tool"
    bl_label = "Select Seam Tool"
    bl_description = "Switch to edge select mode and select a PolyGroups seam tool"
    bl_options = {"REGISTER"}

    tool_id: bpy.props.StringProperty(
        name="Tool ID",
        default="polygroups_generator.knife_seam_tool",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
        bpy.ops.wm.tool_set_by_id(name=self.tool_id)
        return {"FINISHED"}
