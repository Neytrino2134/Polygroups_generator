import re

import bpy

from ..core.remesh_defaults import apply_quad_remesher_defaults_once
from ..core.generated_index import generated_collection_info
from ..localization import t
from .apply_weld import apply_weld_to_objects
from .rename_objects import rename_and_move_objects
from .remesh_progress import remesh_available


HIGHPOLY_NAME_PATTERN = re.compile(r"^Highpoly_Generated\.\d+$", re.IGNORECASE)
FAB_HIGHPOLY_NAME_PATTERN = re.compile(r"^SM_.+_HIGH(?:\.\d+)?$")
FAB_LOWPOLY_NAME_PATTERN = re.compile(r"^SM_.+_LOW(?:\.\d+)?$")
FAB_MIDPOLY_NAME_PATTERN = re.compile(r"^SM_.+_MID(?:\.\d+)?$")
LOWPOLY_PREFIXES = ("Retopo_", "Retopology")
LOWPOLY_TOKEN_PATTERN = re.compile(
    r"^(?:low|retopo(?:logy)?)(?:[_. -]|$)|(?:^|[_. -])(?:low|retopo(?:logy)?)(?:\.\d+)?$",
    re.IGNORECASE,
)
RETOPO_SOURCE_PATTERN = re.compile(r"^Retopo_(?:\d+_)?(.+)$", re.IGNORECASE)


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
        or LOWPOLY_TOKEN_PATTERN.search(name)
    )


def lowpoly_name_priority(name):
    if FAB_LOWPOLY_NAME_PATTERN.match(name):
        return 0
    if FAB_MIDPOLY_NAME_PATTERN.match(name):
        return 1
    return 2


def is_quad_remesh_ready_name(name):
    return is_generated_highpoly_name(name) or is_lowpoly_name(name)


def is_polygroups_ready_name(name):
    return is_generated_highpoly_name(name) or name.startswith("Retopo_")


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


def expected_highpoly_name(lowpoly_name):
    """Return the original highpoly name encoded in a Retopo[_NN]_ name."""
    match = RETOPO_SOURCE_PATTERN.match(lowpoly_name)
    if match is None:
        return ""
    candidate = match.group(1)
    return candidate if is_generated_highpoly_name(candidate) else ""


def find_matching_highpoly(lowpoly):
    """Find the exact source mesh in the lowpoly's numbered Generated collection."""
    expected_name = expected_highpoly_name(lowpoly.name)
    collection, _index = generated_collection_info(lowpoly)
    if not expected_name or collection is None:
        return None, expected_name, collection
    source = next(
        (
            obj
            for obj in collection.objects
            if obj != lowpoly
            and obj.type == "MESH"
            and obj.name.casefold() == expected_name.casefold()
        ),
        None,
    )
    return source, expected_name, collection


def auto_select_matching_highpoly(context, lowpoly):
    source, expected_name, collection = find_matching_highpoly(lowpoly)
    if source is None:
        return None, expected_name, collection
    if lowpoly.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    source.hide_viewport = False
    source.hide_render = False
    source.hide_set(False)
    source.select_set(True)
    lowpoly.select_set(True)
    context.view_layer.objects.active = lowpoly
    return source, expected_name, collection


def report_missing_matching_highpoly(operator, context, lowpoly, expected_name, collection):
    collection_name = collection.name if collection is not None else "Generated.N"
    if expected_name:
        message = t(
            context,
            "bake_matching_highpoly_not_found",
            object=expected_name,
            collection=collection_name,
        )
    else:
        message = t(context, "bake_matching_highpoly_name_invalid", object=lowpoly.name)
    operator.report({"WARNING"}, message)
    if not bpy.app.background:
        def draw_warning(menu, _context):
            menu.layout.label(text=message)
            menu.layout.label(text=t(context, "bake_matching_highpoly_hint"))

        context.window_manager.popup_menu(
            draw_warning,
            title=t(context, "bake_selection_required"),
            icon="ERROR",
        )


def run_bake_action(operator, context, action, check_uv=True):
    mesh_objects = selected_mesh_objects(context)
    if action == "PREPARE_AND_BAKE" and len(mesh_objects) == 1:
        lowpoly = context.active_object
        source, expected_name, collection = auto_select_matching_highpoly(context, lowpoly)
        if source is None:
            report_missing_matching_highpoly(
                operator,
                context,
                lowpoly,
                expected_name,
                collection,
            )
            return {"CANCELLED"}
        operator.report(
            {"INFO"},
            t(context, "bake_matching_highpoly_selected", object=source.name),
        )

    if action in {"PREPARE_AND_BAKE", "BAKE"} and len(selected_mesh_objects(context)) < 2:
        message = t(context, "bake_requires_two_objects")
        operator.report({"WARNING"}, message)
        if not bpy.app.background:
            def draw_warning(menu, _context):
                menu.layout.label(text=message)
                menu.layout.label(text=t(context, "bake_select_highpoly_lowpoly_hint"))

            context.window_manager.popup_menu(
                draw_warning,
                title=t(context, "bake_selection_required"),
                icon="ERROR",
            )
        return {"CANCELLED"}

    target = context.active_object
    if (
        check_uv
        and action in {"PREPARE_AND_BAKE", "BAKE"}
        and target is not None
        and target.type == "MESH"
        and not target.data.uv_layers
    ):
        return bpy.ops.object.polygroups_missing_uv_bake_dialog(
            "INVOKE_DEFAULT",
            bake_action=action,
        )

    if action == "PREPARE_LOWPOLY":
        try:
            return bpy.ops.object.polygroups_prepare_lowpoly_bake_material()
        except Exception as error:
            operator.report({"ERROR"}, f"Prepare lowpoly bake material failed: {error}")
            return {"CANCELLED"}

    if action == "PREPARE_AND_BAKE":
        try:
            return bpy.ops.object.polygroups_bake_task("INVOKE_DEFAULT", prepare_materials=True)
        except Exception as error:
            operator.report({"ERROR"}, f"Prepare and bake failed: {error}")
            return {"CANCELLED"}

    if action == "BAKE":
        try:
            return bpy.ops.object.polygroups_bake_task("INVOKE_DEFAULT", prepare_materials=False)
        except Exception as error:
            operator.report({"ERROR"}, f"Bake failed: {error}")
            return {"CANCELLED"}

    operator.report({"ERROR"}, "Unknown bake action")
    return {"CANCELLED"}


class OBJECT_OT_polygroups_missing_uv_bake_dialog(bpy.types.Operator):
    bl_idname = "object.polygroups_missing_uv_bake_dialog"
    bl_label = "Lowpoly Has No UV Map"
    bl_description = "Unwrap and pack the active lowpoly before baking"
    bl_options = {"UNDO", "INTERNAL"}

    bake_action: bpy.props.StringProperty(default="BAKE", options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=500,
            confirm_text="Unwrap + UVPackmaster + Bake",
        )

    def draw(self, context):
        layout = self.layout
        target = context.active_object
        name = target.name if target is not None else "Active object"
        layout.label(text=f'"{name}" has no UV map.', icon="ERROR")
        layout.label(text="The lowpoly object is not unwrapped and the bake may be invalid.")
        layout.label(text="Confirm to unwrap it with Angle Based and pack it with UVPackmaster.")

    def execute(self, context):
        target = context.active_object
        if target is None or target.type != "MESH":
            self.report({"ERROR"}, "Active bake target must be a mesh")
            return {"CANCELLED"}
        if (
            not hasattr(context.scene, "uvpm4_props")
            or getattr(getattr(bpy.ops, "uvpackmaster4", None), "pack", None) is None
        ):
            self.report({"ERROR"}, "UVPackmaster 4 must be installed and enabled")
            return {"CANCELLED"}
        try:
            unwrap_result = bpy.ops.object.polygroups_unwrap_angle_based("EXEC_DEFAULT")
        except Exception as error:
            self.report({"ERROR"}, f"UV unwrap failed: {error}")
            return {"CANCELLED"}
        if "FINISHED" not in unwrap_result:
            self.report({"ERROR"}, "UV unwrap was not completed")
            return {"CANCELLED"}

        from .baking import _auto_pack_target_uvs
        settings = context.scene.polygroups_baking_settings
        if not _auto_pack_target_uvs(context, target, settings, self.report, force=True):
            return {"CANCELLED"}
        return run_bake_action(self, context, self.bake_action, check_uv=False)


class OBJECT_OT_polygroups_rename_and_apply_weld(bpy.types.Operator):
    bl_idname = "object.polygroups_rename_and_apply_weld"
    bl_label = "Rename And Apply Weld"
    bl_description = "Rename selected objects, keep existing Generated.N collections, then apply Weld"
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

    quad_count: bpy.props.IntProperty(
        name="Quad Count", description="Target quad count; zero keeps the current value",
        default=0, min=0, options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return remesh_available(context)

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
        ).quad_count = self.quad_count

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
            if self.quad_count:
                context.scene.qremesher.target_count = self.quad_count
            result = bpy.ops.object.polygroups_run_remesh()
            return {"FINISHED"} if "RUNNING_MODAL" in result else result
        except Exception as error:
            self.report({"ERROR"}, f"Quad Remesher failed: {error}")
            return {"CANCELLED"}


class OBJECT_OT_polygroups_skip_quad_remesh(bpy.types.Operator):
    bl_idname = "object.polygroups_skip_quad_remesh"
    bl_label = "Skip - Just Remesh"
    bl_description = "Skip preparation checks and run Quad Remesher on the active mesh"
    bl_options = {"UNDO"}

    quad_count: bpy.props.IntProperty(
        name="Quad Count", description="Target quad count; zero keeps the current value",
        default=0, min=0, options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return remesh_available(context)

    def execute(self, context):
        apply_quad_remesher_defaults_once(context.scene)
        try:
            if self.quad_count:
                context.scene.qremesher.target_count = self.quad_count
            result = bpy.ops.object.polygroups_run_remesh()
            return {"FINISHED"} if "RUNNING_MODAL" in result else result
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
        return run_bake_action(self, context, "BAKE")


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
            and is_polygroups_ready_name(active_object.name)
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
            and is_polygroups_ready_name(active_object.name)
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


class OBJECT_OT_polygroups_checked_bake_selected_to_active(bpy.types.Operator):
    bl_idname = "object.polygroups_checked_bake_selected_to_active"
    bl_label = "Bake Selected To Active"
    bl_description = "Verify or automatically select the lowpoly target before baking"
    bl_options = {"UNDO"}

    target_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return len(selected_mesh_objects(context)) >= 2

    def invoke(self, context, event):
        self.target_name = ""
        active = context.active_object
        if active is not None and is_lowpoly_name(active.name):
            return self.execute(context)

        lowpoly = find_selected_lowpoly(context)
        if lowpoly is not None:
            self.target_name = lowpoly.name
            return self.execute(context)

        meshes = selected_mesh_objects(context)
        candidate = None
        if active is not None and is_generated_highpoly_name(active.name) and len(meshes) == 2:
            candidate = next((obj for obj in meshes if obj != active), None)
        self.target_name = candidate.name if candidate is not None else ""
        confirm_text = (
            f'Make "{candidate.name}" Active and Bake'
            if candidate is not None
            else "Bake With Current Active"
        )
        return context.window_manager.invoke_props_dialog(
            self,
            width=500,
            confirm_text=confirm_text,
        )

    def draw(self, context):
        layout = self.layout
        active = context.active_object
        layout.label(text="Could not identify a lowpoly target by name.", icon="ERROR")
        layout.label(text="Make sure the intended lowpoly object is active before baking.")
        if self.target_name:
            layout.separator()
            layout.label(text=f'Highpoly "{active.name}" is currently active.')
            layout.label(text=f'Confirm to make "{self.target_name}" active and bake.')
        layout.separator()
        layout.operator(
            "object.polygroups_skip_prepare_and_bake",
            text="Skip Check - Bake With Current Active",
            icon="RENDER_STILL",
        )

    def execute(self, context):
        if self.target_name:
            target = next(
                (obj for obj in selected_mesh_objects(context) if obj.name == self.target_name),
                None,
            )
            if target is None:
                self.report({"ERROR"}, f'Bake target "{self.target_name}" is no longer selected')
                return {"CANCELLED"}
            if context.active_object and context.active_object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            target.select_set(True)
            context.view_layer.objects.active = target
            self.report({"INFO"}, f"Active lowpoly: {target.name}")
        return run_bake_action(self, context, "BAKE")
