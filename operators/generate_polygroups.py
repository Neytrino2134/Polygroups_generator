import bmesh
import bpy

from ..core.facesets import assign_face_sets_from_materials
from ..core.materials import assign_materials
from ..core.mesh_segmentation import get_seam_edges, split_into_groups


class OBJECT_OT_generate_polygroups(bpy.types.Operator):
    bl_idname = "object.generate_polygroups"
    bl_label = "Generate PolyGroups"
    bl_description = "Split the active mesh by seam edges, assign materials, and create Face Sets"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        view_layer = context.view_layer
        view_layer.objects.active = obj

        if context.mode not in {"OBJECT", "EDIT_MESH", "SCULPT"}:
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        seam_edges = get_seam_edges(bm)
        groups = split_into_groups(bm, seam_edges=seam_edges)

        if not groups:
            self.report({"WARNING"}, "No face groups were generated")
            return {"CANCELLED"}

        assign_materials(obj, groups)
        bmesh.update_edit_mesh(obj.data)

        bpy.ops.object.mode_set(mode="OBJECT")
        assign_face_sets_from_materials(context, obj)

        self.report(
            {"INFO"},
            f"Generated {len(groups)} PolyGroups from {len(seam_edges)} seam edges",
        )
        return {"FINISHED"}
