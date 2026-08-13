import bmesh
import bpy


class MESH_OT_polygroups_mark_material_boundaries_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_material_boundaries_seam"
    bl_label = "Generate Seams From Materials"
    bl_description = "Mark seams on edges where adjacent faces use different materials"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        marked_count = 0

        if context.mode == "EDIT_MESH":
            bm = bmesh.from_edit_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            for edge in bm.edges:
                material_indices = {face.material_index for face in edge.link_faces}
                if len(material_indices) > 1:
                    if not edge.seam:
                        marked_count += 1
                    edge.seam = True

            bmesh.update_edit_mesh(obj.data)
        else:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            for edge in bm.edges:
                material_indices = {face.material_index for face in edge.link_faces}
                if len(material_indices) > 1:
                    if not edge.seam:
                        marked_count += 1
                    edge.seam = True

            bm.to_mesh(obj.data)
            bm.free()
            obj.data.update()

        self.report({"INFO"}, f"Marked {marked_count} material boundary seam edge(s)")
        return {"FINISHED"}
