import bpy

from ..core.material_seams import mark_material_boundary_seams


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
        marked_count = mark_material_boundary_seams(context.active_object)

        self.report({"INFO"}, f"Marked {marked_count} material boundary seam edge(s)")
        return {"FINISHED"}
