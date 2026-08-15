import re

import bpy

from .apply_weld import apply_weld_to_objects
from .rename_objects import rename_and_move_objects


HIGHPOLY_NAME_PATTERN = re.compile(r"^Highpoly_Generated\.\d{3,}$")
LOWPOLY_PREFIXES = ("Retopo_", "Retopology")


def is_generated_highpoly_name(name):
    return bool(HIGHPOLY_NAME_PATTERN.match(name))


def is_lowpoly_name(name):
    return name.startswith(LOWPOLY_PREFIXES)


def is_quad_remesh_ready_name(name):
    return is_generated_highpoly_name(name) or is_lowpoly_name(name)


def selected_mesh_objects(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def find_selected_lowpoly(context):
    lowpoly_objects = [
        obj
        for obj in selected_mesh_objects(context)
        if is_lowpoly_name(obj.name)
    ]
    if not lowpoly_objects:
        return None
    return lowpoly_objects[0]


class OBJECT_OT_polygroups_rename_and_apply_weld(bpy.types.Operator):
    bl_idname = "object.polygroups_rename_and_apply_weld"
    bl_label = "Rename And Apply Weld"
    bl_description = "Rename selected objects, move them to Generated, then apply Weld"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(selected_mesh_objects(context))

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        mesh_objects = selected_mesh_objects(context)
        if not mesh_objects:
            self.report({"ERROR"}, "Select at least one mesh object")
            return {"CANCELLED"}

        renamed_count = rename_and_move_objects(context, mesh_objects)
        welded_count = apply_weld_to_objects(
            context,
            mesh_objects,
            settings.weld_distance,
            self.report,
        )
        self.report(
            {"INFO"},
            f"Renamed {renamed_count} object(s), applied Weld on {welded_count}",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_checked_quad_remesh(bpy.types.Operator):
    bl_idname = "object.polygroups_checked_quad_remesh"
    bl_label = "Remesh It"
    bl_description = "Check the selected highpoly name before running Quad Remesher"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        active_object = context.active_object
        if (
            active_object
            and active_object.type == "MESH"
            and is_quad_remesh_ready_name(active_object.name)
        ):
            return self.execute(context)

        return context.window_manager.invoke_props_dialog(
            self,
            width=440,
            confirm_text="Rename + Weld + Remesh",
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Selected object does not look prepared.", icon="ERROR")
        layout.label(text="Make sure Rename Objects and Apply Weld were done.")
        layout.label(text="Confirm to prepare it and start Quad Remesher.")
        layout.separator()
        layout.operator(
            "object.polygroups_skip_quad_remesh",
            text="Skip - Just Remesh",
            icon="MOD_REMESH",
        )

    def execute(self, context):
        active_object = context.active_object
        if (
            active_object
            and active_object.type == "MESH"
            and is_quad_remesh_ready_name(active_object.name)
        ):
            return self.run_quad_remesher(context)

        if not active_object or active_object.type != "MESH":
            self.report({"ERROR"}, "Active object must be a mesh")
            return {"CANCELLED"}

        mesh_objects = selected_mesh_objects(context)
        if active_object not in mesh_objects:
            self.report({"ERROR"}, "Active mesh must be selected")
            return {"CANCELLED"}

        settings = context.scene.polygroups_model_preparation_settings
        renamed_count = rename_and_move_objects(context, mesh_objects)
        welded_count = apply_weld_to_objects(
            context,
            mesh_objects,
            settings.weld_distance,
            self.report,
        )
        self.report(
            {"INFO"},
            f"Prepared {renamed_count} object(s), applied Weld on {welded_count}",
        )

        if not is_generated_highpoly_name(active_object.name):
            self.report({"ERROR"}, "Prepared object name is not Highpoly_Generated.###")
            return {"CANCELLED"}

        return self.run_quad_remesher(context)

    def run_quad_remesher(self, context):
        try:
            return bpy.ops.qremesher.remesh()
        except Exception as error:
            self.report({"ERROR"}, f"Quad Remesher failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_skip_quad_remesh(bpy.types.Operator):
    bl_idname = "object.polygroups_skip_quad_remesh"
    bl_label = "Skip - Just Remesh"
    bl_description = "Skip preparation checks and run Quad Remesher on the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        try:
            return bpy.ops.qremesher.remesh()
        except Exception as error:
            self.report({"ERROR"}, f"Quad Remesher failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_checked_generate_polygroups(bpy.types.Operator):
    bl_idname = "object.polygroups_checked_generate_polygroups"
    bl_label = "Generate PolyGroups"
    bl_description = "Check highpoly preparation before generating PolyGroups"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        active_object = context.active_object
        if (
            active_object
            and active_object.type == "MESH"
            and is_generated_highpoly_name(active_object.name)
        ):
            return self.execute(context)

        return context.window_manager.invoke_props_dialog(
            self,
            width=460,
            confirm_text="Rename + Weld + Generate PolyGroups",
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Selected object does not look prepared.", icon="ERROR")
        layout.label(text="Make sure Rename Objects and Apply Weld were done.")
        layout.label(text="Confirm to prepare it and generate PolyGroups.")

    def execute(self, context):
        active_object = context.active_object
        if (
            active_object
            and active_object.type == "MESH"
            and is_generated_highpoly_name(active_object.name)
        ):
            return self.run_generate_polygroups(context)

        if not active_object or active_object.type != "MESH":
            self.report({"ERROR"}, "Active object must be a mesh")
            return {"CANCELLED"}

        mesh_objects = selected_mesh_objects(context)
        if active_object not in mesh_objects:
            self.report({"ERROR"}, "Active mesh must be selected")
            return {"CANCELLED"}

        settings = context.scene.polygroups_model_preparation_settings
        renamed_count = rename_and_move_objects(context, mesh_objects)
        welded_count = apply_weld_to_objects(
            context,
            mesh_objects,
            settings.weld_distance,
            self.report,
        )
        self.report(
            {"INFO"},
            f"Prepared {renamed_count} object(s), applied Weld on {welded_count}",
        )

        if not is_generated_highpoly_name(active_object.name):
            self.report({"ERROR"}, "Prepared object name is not Highpoly_Generated.###")
            return {"CANCELLED"}

        return self.run_generate_polygroups(context)

    def run_generate_polygroups(self, context):
        try:
            return bpy.ops.object.generate_polygroups()
        except Exception as error:
            self.report({"ERROR"}, f"Generate PolyGroups failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_make_lowpoly_active(bpy.types.Operator):
    bl_idname = "object.polygroups_make_lowpoly_active"
    bl_label = "Make Lowpoly Active"
    bl_description = "Make the selected Retopo or Retopology mesh active"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return find_selected_lowpoly(context) is not None

    def execute(self, context):
        lowpoly = find_selected_lowpoly(context)
        if lowpoly is None:
            self.report(
                {"ERROR"},
                "Select a mesh named Retopo_... or Retopology...",
            )
            return {"CANCELLED"}

        lowpoly.select_set(True)
        context.view_layer.objects.active = lowpoly
        self.report({"INFO"}, f"Active lowpoly: {lowpoly.name}")
        return {"FINISHED"}
