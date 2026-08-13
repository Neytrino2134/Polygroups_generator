import bpy


def apply_weld_to_objects(context, objects, weld_distance, report=None):
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]

    if not mesh_objects:
        return 0

    previous_active = context.view_layer.objects.active
    previous_selection = list(context.selected_objects)

    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    applied_count = 0
    for obj in mesh_objects:
        modifier = obj.modifiers.get(OBJECT_OT_polygroups_apply_weld.modifier_name)
        if modifier is None or modifier.type != "WELD":
            modifier = obj.modifiers.new(
                OBJECT_OT_polygroups_apply_weld.modifier_name,
                "WELD",
            )

        modifier.merge_threshold = weld_distance

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj

        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except RuntimeError as error:
            if report:
                report({"WARNING"}, f"{obj.name}: {error}")
            continue

        applied_count += 1

    bpy.ops.object.select_all(action="DESELECT")
    for obj in previous_selection:
        try:
            obj.select_set(True)
        except RuntimeError:
            pass
    if previous_active:
        try:
            context.view_layer.objects.active = previous_active
        except (RuntimeError, TypeError):
            pass

    return applied_count


class OBJECT_OT_polygroups_apply_weld(bpy.types.Operator):
    bl_idname = "object.polygroups_apply_weld"
    bl_label = "Apply Weld"
    bl_description = "Add and apply a Weld modifier on selected mesh objects"
    bl_options = {"REGISTER", "UNDO"}

    modifier_name = "Retopo Weld"

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        mesh_objects = [obj for obj in context.selected_objects if obj.type == "MESH"]

        if not mesh_objects:
            self.report({"WARNING"}, "Select at least one mesh object")
            return {"CANCELLED"}

        applied_count = apply_weld_to_objects(
            context,
            mesh_objects,
            settings.weld_distance,
            self.report,
        )

        self.report(
            {"INFO"},
            f"Applied Weld on {applied_count} mesh object(s)",
        )
        return {"FINISHED"}
