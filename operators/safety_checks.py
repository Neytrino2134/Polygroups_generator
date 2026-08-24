import re

import bpy

from ..core.remesh_defaults import apply_quad_remesher_defaults_once
from .apply_weld import apply_weld_to_objects
from .rename_objects import rename_and_move_objects


HIGHPOLY_NAME_PATTERN = re.compile(r"^Highpoly_Generated\.\d{3,}$")
FAB_HIGHPOLY_NAME_PATTERN = re.compile(r"^SM_.+_HIGH(?:\.\d+)?$")
FAB_LOWPOLY_NAME_PATTERN = re.compile(r"^SM_.+_LOW(?:\.\d+)?$")
FAB_MIDPOLY_NAME_PATTERN = re.compile(r"^SM_.+_MID(?:\.\d+)?$")
LOWPOLY_PREFIXES = ("Retopo_", "Retopology")


def is_generated_highpoly_name(name):
    return bool(
        HIGHPOLY_NAME_PATTERN.match(name)
        or FAB_HIGHPOLY_NAME_PATTERN.match(name)
    )


def is_lowpoly_name(name):
    return bool(
        name.startswith(LOWPOLY_PREFIXES)
        or FAB_LOWPOLY_NAME_PATTERN.match(name)
        or FAB_MIDPOLY_NAME_PATTERN.match(name)
    )


def lowpoly_name_priority(name):
    if FAB_LOWPOLY_NAME_PATTERN.match(name):
        return 0
    if FAB_MIDPOLY_NAME_PATTERN.match(name):
        return 1
    return 2


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

    lowpoly_objects.sort(key=lambda obj: lowpoly_name_priority(obj.name))
    return lowpoly_objects[0]


def make_selected_lowpoly_active(context):
    lowpoly = find_selected_lowpoly(context)
    if lowpoly is None:
        return None

    if context.active_object and context.active_object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    lowpoly.select_set(True)
    context.view_layer.objects.active = lowpoly
    return lowpoly


def run_bake_action(operator, context, action):
    if action == "PREPARE_LOWPOLY":
        try:
            return bpy.ops.object.polygroups_prepare_lowpoly_bake_material()
        except Exception as error:
            operator.report({"ERROR"}, f"Prepare lowpoly bake material failed: {error}")
            return {"CANCELLED"}

    if action == "PREPARE_AND_BAKE":
        try:
            return bpy.ops.object.polygroups_prepare_and_bake()
        except Exception as error:
            operator.report({"ERROR"}, f"Prepare and bake failed: {error}")
            return {"CANCELLED"}

    operator.report({"ERROR"}, "Unknown bake action")
    return {"CANCELLED"}


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
    bl_options = {"UNDO"}

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
        apply_quad_remesher_defaults_once(context.scene)
        try:
            return bpy.ops.qremesher.remesh()
        except Exception as error:
            self.report({"ERROR"}, f"Quad Remesher failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_skip_quad_remesh(bpy.types.Operator):
    bl_idname = "object.polygroups_skip_quad_remesh"
    bl_label = "Skip - Just Remesh"
    bl_description = "Skip preparation checks and run Quad Remesher on the active mesh"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        apply_quad_remesher_defaults_once(context.scene)
        try:
            return bpy.ops.qremesher.remesh()
        except Exception as error:
            self.report({"ERROR"}, f"Quad Remesher failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_skip_prepare_and_bake(bpy.types.Operator):
    bl_idname = "object.polygroups_skip_prepare_and_bake"
    bl_label = "Skip - Just Bake"
    bl_description = "Skip lowpoly naming checks and run selected-to-active bake"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        try:
            return bpy.ops.object.polygroups_bake_selected_to_active()
        except Exception as error:
            self.report({"ERROR"}, f"Bake failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_checked_generate_polygroups(bpy.types.Operator):
    bl_idname = "object.polygroups_checked_generate_polygroups"
    bl_label = "Generate PolyGroups"
    bl_description = "Check highpoly preparation before generating PolyGroups"
    bl_options = {"UNDO"}

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
        layout.separator()
        layout.operator(
            "object.polygroups_skip_generate_polygroups",
            text="Skip - Just Generate",
            icon="FACESEL",
        )

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


class OBJECT_OT_polygroups_skip_generate_polygroups(bpy.types.Operator):
    bl_idname = "object.polygroups_skip_generate_polygroups"
    bl_label = "Skip - Just Generate"
    bl_description = "Skip preparation checks and generate PolyGroups on the active mesh"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        try:
            return bpy.ops.object.generate_polygroups()
        except Exception as error:
            self.report({"ERROR"}, f"Generate PolyGroups failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_make_lowpoly_active(bpy.types.Operator):
    bl_idname = "object.polygroups_make_lowpoly_active"
    bl_label = "Make Lowpoly Active"
    bl_description = "Make the selected Retopo or Retopology mesh active"
    bl_options = {"UNDO"}

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


class PolygroupsBakeLowpolyCheckMixin:
    bake_action = ""
    confirm_label = "Make Lowpoly Active + Continue"
    skip_operator_id = ""

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        active_object = context.active_object
        if (
            active_object
            and active_object.type == "MESH"
            and is_lowpoly_name(active_object.name)
        ):
            return self.execute(context)

        return context.window_manager.invoke_props_dialog(
            self,
            width=470,
            confirm_text=self.confirm_label,
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Active object does not look like a lowpoly target.", icon="ERROR")
        layout.label(text="Make sure the active mesh is named Retopo_..., Retopology..., SM_*_LOW, or SM_*_MID.")
        layout.label(text="Confirm to make the selected lowpoly active and continue.")
        if self.skip_operator_id:
            layout.separator()
            layout.operator(
                self.skip_operator_id,
                text="Skip - Just Bake",
                icon="RENDER_STILL",
            )

    def execute(self, context):
        active_object = context.active_object
        if (
            active_object
            and active_object.type == "MESH"
            and is_lowpoly_name(active_object.name)
        ):
            return run_bake_action(self, context, self.bake_action)

        lowpoly = make_selected_lowpoly_active(context)
        if lowpoly is None:
            self.report(
                {"ERROR"},
                "Select a mesh named Retopo_..., Retopology..., SM_*_LOW, or SM_*_MID with the highpoly source",
            )
            return {"CANCELLED"}

        self.report({"INFO"}, f"Active lowpoly: {lowpoly.name}")
        return run_bake_action(self, context, self.bake_action)


class OBJECT_OT_polygroups_checked_prepare_lowpoly_bake_material(
    PolygroupsBakeLowpolyCheckMixin,
    bpy.types.Operator,
):
    bl_idname = "object.polygroups_checked_prepare_lowpoly_bake_material"
    bl_label = "Prepare Lowpoly Bake Material"
    bl_description = "Check that a Retopo or Retopology mesh is active before preparing bake material"
    bl_options = {"UNDO"}

    bake_action = "PREPARE_LOWPOLY"
    confirm_label = "Make Lowpoly Active + Prepare"


class OBJECT_OT_polygroups_checked_prepare_and_bake(
    PolygroupsBakeLowpolyCheckMixin,
    bpy.types.Operator,
):
    bl_idname = "object.polygroups_checked_prepare_and_bake"
    bl_label = "Prepare And Bake"
    bl_description = "Check that a Retopo or Retopology mesh is active before preparing and baking"
    bl_options = {"UNDO"}

    bake_action = "PREPARE_AND_BAKE"
    confirm_label = "Make Lowpoly Active + Bake"
    skip_operator_id = "object.polygroups_skip_prepare_and_bake"
