import bmesh
import bpy


class MESH_OT_polygroups_mark_selected_edges_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_selected_edges_seam"
    bl_label = "Mark Selected Edges Seam"
    bl_description = "Mark currently selected edges as seams in Edit Mode"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)

        selected_edges = [edge for edge in bm.edges if edge.select]
        if not selected_edges:
            self.report({"WARNING"}, "Select one or more edges")
            return {"CANCELLED"}

        marked_count = 0
        for edge in selected_edges:
            if not edge.seam:
                edge.seam = True
                marked_count += 1

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, f"Marked {marked_count} selected edge seam(s)")
        return {"FINISHED"}
