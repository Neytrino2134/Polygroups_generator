import math

import bmesh
import bpy


def face_neighbors(face):
    neighbors = set()
    for edge in face.edges:
        for linked_face in edge.link_faces:
            if linked_face != face:
                neighbors.add(linked_face)
    return neighbors


class MESH_OT_polygroups_smooth_face_selection(bpy.types.Operator):
    bl_idname = "mesh.polygroups_smooth_face_selection"
    bl_label = "Smooth Face Selection"
    bl_description = "Smooth the selected face region by relaxing its boundary in Edit Mode"
    bl_options = {"REGISTER", "UNDO"}

    iterations: bpy.props.IntProperty(
        name="Iterations",
        default=2,
        min=1,
        max=25,
    )

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

        for _iteration in range(self.iterations):
            next_selected_faces = set(selected_faces)

            for face in bm.faces:
                neighbors = face_neighbors(face)
                if not neighbors:
                    continue

                selected_neighbor_count = len(neighbors & selected_faces)
                fill_threshold = math.ceil(len(neighbors) * 0.75)
                keep_threshold = math.ceil(len(neighbors) * 0.25)

                if face in selected_faces:
                    if selected_neighbor_count < keep_threshold:
                        next_selected_faces.discard(face)
                elif selected_neighbor_count >= fill_threshold:
                    next_selected_faces.add(face)

            if next_selected_faces == selected_faces:
                break

            selected_faces = next_selected_faces

        for face in bm.faces:
            face.select_set(face in selected_faces)

        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, f"Smoothed selection to {len(selected_faces)} face(s)")
        return {"FINISHED"}
