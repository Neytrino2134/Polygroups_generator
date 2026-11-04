"""Remove material slots that no face uses from every selected mesh."""
import bpy


def unused_slot_count(obj):
    used = {polygon.material_index for polygon in obj.data.polygons}
    return sum(1 for index in range(len(obj.material_slots)) if index not in used)


class OBJECT_OT_polygroups_remove_unused_slots(bpy.types.Operator):
    bl_idname = "object.polygroups_remove_unused_slots"
    bl_label = "Remove Unused Slots"
    bl_description = "Remove material slots that no face uses from all selected meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        removed = skipped = meshes = 0
        done = set()
        for obj in [o for o in context.selected_objects if o.type == "MESH"]:
            if obj.data in done:
                continue            # linked duplicates share one mesh: its slots are already cleaned
            done.add(obj.data)
            if obj.library or obj.data.library:
                skipped += 1
                continue
            before = len(obj.material_slots)
            if not before or not unused_slot_count(obj):
                continue
            with context.temp_override(object=obj, active_object=obj, selected_editable_objects=[obj],
                                       selected_objects=[obj]):
                bpy.ops.object.material_slot_remove_unused()
            removed += before - len(obj.material_slots)
            meshes += 1
        if skipped:
            self.report({"WARNING"}, f"Skipped {skipped} linked mesh(es)")
        self.report({"INFO"}, f"Removed {removed} unused material slot(s) from {meshes} mesh(es)")
        return {"FINISHED"}
