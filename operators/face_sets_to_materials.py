import bmesh
import bpy

from ..core.facesets import split_faces_by_face_set
from ..core.materials import assign_materials


class OBJECT_OT_face_sets_to_materials(bpy.types.Operator):
    bl_idname = "object.face_sets_to_materials"
    bl_label = "Face Sets to Materials"
    bl_description = "Create and assign materials from existing sculpt Face Sets"
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

        groups = split_faces_by_face_set(bm)
        if groups is None:
            self.report({"WARNING"}, "No sculpt Face Set attribute found on the mesh")
            return {"CANCELLED"}

        if not groups:
            self.report({"WARNING"}, "No Face Sets were found to convert")
            return {"CANCELLED"}

        assign_materials(obj, groups, prefix="PolyGroup")
        bmesh.update_edit_mesh(obj.data)

        self.report({"INFO"}, f"Assigned materials to {len(groups)} Face Set groups")
        return {"FINISHED"}
