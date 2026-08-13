import bmesh
import bpy


class MESH_OT_polygroups_mark_selection_boundary_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_selection_boundary_seam"
    bl_label = "Mark Selection Boundary Seam"
    bl_description = "Mark seams along the boundary of selected faces in Edit Mode"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)

        selected_faces = {face for face in bm.faces if face.select}
        if not selected_faces:
            self.report({"WARNING"}, "Select one or more faces")
            return {"CANCELLED"}

        marked_count = 0
        for edge in bm.edges:
            linked_faces = set(edge.link_faces)
            selected_linked_faces = linked_faces & selected_faces

            if not selected_linked_faces:
                continue

            if linked_faces - selected_faces and not edge.seam:
                edge.seam = True
                marked_count += 1
                continue

            if len(linked_faces) == 1 and not edge.seam:
                edge.seam = True
                marked_count += 1

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, f"Marked {marked_count} boundary seam edge(s)")
        return {"FINISHED"}
