import bpy

from .safety_checks import find_selected_lowpoly
from .safety_checks import is_lowpoly_name


MULTIRES_MODIFIER_NAME = "PolyGroups Multires"
SHRINKWRAP_MODIFIER_NAME = "PolyGroups Shrinkwrap"


def _mesh_polygon_count(obj):
    if not obj or obj.type != "MESH" or not obj.data:
        return 0
    return len(obj.data.polygons)


def _active_mesh(context):
    obj = context.active_object
    if not obj or obj.type != "MESH":
        return None
    return obj


def _selected_highpoly_target(context, lowpoly):
    candidates = [
        obj
        for obj in context.selected_objects
        if obj and obj.type == "MESH" and obj != lowpoly
    ]
    if not candidates:
        return None
    return max(candidates, key=_mesh_polygon_count)


def _set_object_mode(context):
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def add_multires_modifier(context, lowpoly, levels):
    _set_object_mode(context)
    context.view_layer.objects.active = lowpoly
    lowpoly.select_set(True)

    modifier = lowpoly.modifiers.get(MULTIRES_MODIFIER_NAME)
    if modifier is None:
        modifier = lowpoly.modifiers.new(MULTIRES_MODIFIER_NAME, "MULTIRES")

    levels = max(0, int(levels))
    while getattr(modifier, "total_levels", 0) < levels:
        bpy.ops.object.multires_subdivide(
            modifier=modifier.name,
            mode="CATMULL_CLARK",
        )

    available_levels = getattr(modifier, "total_levels", levels)
    display_levels = min(levels, available_levels)
    modifier.levels = display_levels
    modifier.sculpt_levels = display_levels
    modifier.render_levels = display_levels
    return modifier


def add_shrinkwrap_modifier(lowpoly, highpoly, limit, offset):
    modifier = lowpoly.modifiers.get(SHRINKWRAP_MODIFIER_NAME)
    if modifier is None:
        modifier = lowpoly.modifiers.new(SHRINKWRAP_MODIFIER_NAME, "SHRINKWRAP")

    modifier.target = highpoly
    modifier.wrap_method = "PROJECT"
    modifier.wrap_mode = "ON_SURFACE"
    modifier.project_limit = limit
    modifier.subsurf_levels = 0
    modifier.use_project_x = False
    modifier.use_project_y = False
    modifier.use_project_z = False
    modifier.use_negative_direction = True
    modifier.use_positive_direction = True
    modifier.cull_face = "FRONT"
    modifier.use_invert_cull = True
    modifier.offset = offset
    return modifier


class OBJECT_OT_polygroups_add_multires(bpy.types.Operator):
    bl_idname = "object.polygroups_add_multires"
    bl_label = "Add Multires"
    bl_description = "Add or update a Multiresolution modifier on the active lowpoly mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        settings = context.scene.polygroups_resculpting_settings
        lowpoly = _active_mesh(context)
        if lowpoly is None:
            self.report({"ERROR"}, "Active object must be a mesh lowpoly target")
            return {"CANCELLED"}

        add_multires_modifier(context, lowpoly, settings.multires_levels)
        self.report({"INFO"}, f"Added Multires levels {settings.multires_levels} to {lowpoly.name}")
        return {"FINISHED"}


class OBJECT_OT_polygroups_add_shrinkwrap_to_highpoly(bpy.types.Operator):
    bl_idname = "object.polygroups_add_shrinkwrap_to_highpoly"
    bl_label = "Add Shrinkwrap"
    bl_description = "Add or update Shrinkwrap on the active mesh using the selected highpoly as target"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        settings = context.scene.polygroups_resculpting_settings
        lowpoly = _active_mesh(context)
        highpoly = _selected_highpoly_target(context, lowpoly)
        if lowpoly is None:
            self.report({"ERROR"}, "Active object must be a mesh lowpoly target")
            return {"CANCELLED"}
        if highpoly is None:
            self.report({"ERROR"}, "Select a highpoly mesh and make the lowpoly mesh active")
            return {"CANCELLED"}

        add_shrinkwrap_modifier(
            lowpoly,
            highpoly,
            settings.shrinkwrap_limit,
            settings.shrinkwrap_offset,
        )
        self.report({"INFO"}, f"Shrinkwrap target set to {highpoly.name}")
        return {"FINISHED"}


class OBJECT_OT_polygroups_setup_resculpting(bpy.types.Operator):
    bl_idname = "object.polygroups_setup_resculpting"
    bl_label = "Setup Resculpting"
    bl_description = "Add Multiresolution and Shrinkwrap to the active lowpoly using the selected highpoly"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def invoke(self, context, event):
        lowpoly = _active_mesh(context)
        if lowpoly and is_lowpoly_name(lowpoly.name):
            return self.execute(context)

        return context.window_manager.invoke_props_dialog(
            self,
            width=460,
            confirm_text="Make Lowpoly Active + Setup",
        )

    def draw(self, context):
        layout = self.layout
        active_object = context.active_object

        layout.label(text="Danger: active object does not look like lowpoly.", icon="ERROR")
        if active_object:
            layout.label(text=f"Active: {active_object.name}")
        layout.label(text="Confirm to make lowpoly active and run setup.")

    def execute(self, context):
        settings = context.scene.polygroups_resculpting_settings
        lowpoly = _active_mesh(context)
        if lowpoly is None:
            self.report({"ERROR"}, "Active object must be a mesh lowpoly target")
            return {"CANCELLED"}
        if not is_lowpoly_name(lowpoly.name):
            lowpoly = find_selected_lowpoly(context)
            if lowpoly is None:
                self.report(
                    {"ERROR"},
                    "Select a mesh named Retopo_... or Retopology...",
                )
                return {"CANCELLED"}
            lowpoly.select_set(True)
            context.view_layer.objects.active = lowpoly

        highpoly = _selected_highpoly_target(context, lowpoly)
        if highpoly is None:
            self.report({"ERROR"}, "Select a highpoly mesh and make the lowpoly mesh active")
            return {"CANCELLED"}

        add_multires_modifier(context, lowpoly, settings.multires_levels)
        add_shrinkwrap_modifier(
            lowpoly,
            highpoly,
            settings.shrinkwrap_limit,
            settings.shrinkwrap_offset,
        )
        self.report(
            {"INFO"},
            f"Resculpting setup: {lowpoly.name} projects to {highpoly.name}",
        )
        return {"FINISHED"}
