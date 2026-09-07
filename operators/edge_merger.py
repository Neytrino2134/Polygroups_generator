"""Single-click edge merge tool for Edit Mode."""
import bmesh
import bpy


TOOL_ID = "polygroups_generator.edge_merger_tool"


class MESH_OT_polygroups_edge_merger_click(bpy.types.Operator):
    bl_idname = "mesh.polygroups_edge_merger_click"
    bl_label = "Merge Edge at Center"
    bl_description = "Pick one edge and immediately merge its vertices at the center"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def invoke(self, context, event):
        obj = context.active_object
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.view3d.select(
            location=(event.mouse_region_x, event.mouse_region_y),
            deselect_all=True,
        )
        bm = bmesh.from_edit_mesh(obj.data)
        selected = [edge for edge in bm.edges if edge.select and not edge.hide]
        if len(selected) != 1:
            return {"CANCELLED"}
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
        bm = bmesh.from_edit_mesh(obj.data)
        selected = [edge for edge in bm.edges if edge.select and not edge.hide]
        if len(selected) != 1:
            self.report({"WARNING"}, "Select exactly one edge")
            return {"CANCELLED"}
        edge = selected[0]
        for vert in bm.verts:
            vert.select_set(vert in edge.verts)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        result = bpy.ops.mesh.merge(type="CENTER", uvs=True)
        if "FINISHED" not in result:
            return result
        return {"FINISHED"}
