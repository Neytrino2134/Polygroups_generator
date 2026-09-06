"""Operators for persistent pinned seam edges."""
import bpy
import bmesh

from ..pin_edges import pin_layer, is_pinned, set_pinned


class _PinBase:
    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and any(obj.type == "MESH" for obj in context.objects_in_mode_unique_data)

    def meshes(self, context):
        for obj in context.objects_in_mode_unique_data:
            if obj.type == "MESH":
                yield obj, bmesh.from_edit_mesh(obj.data)


class MESH_OT_polygroups_pin_selected_seams(_PinBase, bpy.types.Operator):
    bl_idname = "mesh.polygroups_pin_selected_seams"
    bl_label = "Pin Selected Seams"
    bl_description = "Pin selected edges that are marked as seams"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        for obj, bm in self.meshes(context):
            layer = pin_layer(bm, True)
            edges = [edge for edge in bm.edges if edge.select and edge.seam and not edge.hide]
            count += sum(not is_pinned(edge, layer) for edge in edges)
            set_pinned(edges, layer)
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        self.report({"INFO"}, f"Pinned {count} selected seam edges")
        return {"FINISHED"}


class MESH_OT_polygroups_unpin_selected_edges(_PinBase, bpy.types.Operator):
    bl_idname = "mesh.polygroups_unpin_selected_edges"
    bl_label = "Unpin Selected"
    bl_description = "Clear pin marks from selected edges without clearing seams"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        for obj, bm in self.meshes(context):
            layer = pin_layer(bm)
            if layer is not None:
                edges = [edge for edge in bm.edges if edge.select and is_pinned(edge, layer)]
                count += len(edges)
                set_pinned(edges, layer, False)
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        self.report({"INFO"}, f"Unpinned {count} selected edges")
        return {"FINISHED"}


class MESH_OT_polygroups_clear_all_pins(_PinBase, bpy.types.Operator):
    bl_idname = "mesh.polygroups_clear_all_pins"
    bl_label = "Clear All Pins"
    bl_description = "Clear every pinned-edge mark without clearing seams"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        for obj, bm in self.meshes(context):
            layer = pin_layer(bm)
            if layer is not None:
                edges = [edge for edge in bm.edges if is_pinned(edge, layer)]
                count += len(edges)
                set_pinned(edges, layer, False)
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        self.report({"INFO"}, f"Cleared {count} pinned edges")
        return {"FINISHED"}
