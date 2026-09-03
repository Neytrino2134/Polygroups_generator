import bmesh
import bpy

from ..localization import t


def editable_meshes(context):
    return [
        (obj.data, bmesh.from_edit_mesh(obj.data))
        for obj in context.objects_in_mode_unique_data
        if obj.type == "MESH" and obj.mode == "EDIT"
    ]


class MESH_OT_polygroups_clear_selected_edges_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_clear_selected_edges_seam"
    bl_label = "Clear Selected Edges Seam"
    bl_description = "Remove seams from selected edges, preserving selection and all other seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        selected_count = cleared_count = 0
        for mesh, bm in editable_meshes(context):
            selected_edges = [edge for edge in bm.edges if edge.select and not edge.hide]
            selected_count += len(selected_edges)
            for edge in selected_edges:
                cleared_count += int(edge.seam)
                edge.seam = False
            if selected_edges:
                bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        if not selected_count:
            self.report({"WARNING"}, t(context, "seam_select_edges"))
            return {"CANCELLED"}
        self.report({"INFO"}, t(context, "seam_cleared_edges", count=cleared_count))
        return {"FINISHED"}


class MESH_OT_polygroups_clear_inside_edges_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_clear_inside_edges_seam"
    bl_label = "Clear Inside Edges Seam"
    bl_description = "Clear seams inside selected faces and mark their boundary; preserve selection and outside seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        selected_count = cleared_count = boundary_count = 0
        for mesh, bm in editable_meshes(context):
            selected_faces = {face for face in bm.faces if face.select and not face.hide}
            selected_count += len(selected_faces)
            if not selected_faces:
                continue
            region_edges = {edge for face in selected_faces for edge in face.edges}
            for edge in region_edges:
                is_boundary = len(edge.link_faces) == 1 or any(
                    face not in selected_faces for face in edge.link_faces
                )
                if is_boundary:
                    boundary_count += int(not edge.seam)
                    edge.seam = True
                else:
                    cleared_count += int(edge.seam)
                    edge.seam = False
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        if not selected_count:
            self.report({"WARNING"}, t(context, "seam_select_faces"))
            return {"CANCELLED"}
        self.report({"INFO"}, t(
            context, "seam_cleared_inside", cleared=cleared_count, marked=boundary_count,
        ))
        return {"FINISHED"}
