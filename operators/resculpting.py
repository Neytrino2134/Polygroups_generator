import re
import bpy

from .safety_checks import find_selected_lowpoly
from .safety_checks import is_lowpoly_name
from .safety_checks import expected_highpoly_name, find_matching_highpoly
from .safety_checks import auto_select_matching_highpoly, report_missing_matching_highpoly
from .safety_checks import is_generated_highpoly_name
from ..core.mesh_ngons import ngon_count, triangulated_ngon_copy


MULTIRES_MODIFIER_NAME = "PolyGroups Multires"
SHRINKWRAP_MODIFIER_NAME = "PolyGroups Shrinkwrap"


def resculpted_name(name):
    renamed, count = re.subn(r'Retopo(?=_|$)', 'Resculpting', name, count=1, flags=re.I)
    if count:
        return renamed
    if re.search(r'Resculpting(?:_|$)', name, re.I) or re.search(r'_Resculpting(?:\.\d+)?$', name, re.I):
        return name
    return name + '_Resculpting'


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


class SetupResculptingMixin:
    """Setup Resculpting logic shared by the registered operators (a registered operator is not subclassed)."""

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def invoke(self, context, event):
        lowpoly = _active_mesh(context)
        if lowpoly and (is_lowpoly_name(lowpoly.name) or not is_generated_highpoly_name(lowpoly.name)):
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
        if not is_lowpoly_name(lowpoly.name) and is_generated_highpoly_name(lowpoly.name):
            selected_lowpoly = find_selected_lowpoly(context)
            if selected_lowpoly is not None:
                lowpoly = selected_lowpoly
            else:
                self.report(
                    {"ERROR"},
                    "Select a mesh named Retopo_... or Retopology...",
                )
                return {"CANCELLED"}
            lowpoly.select_set(True)
            context.view_layer.objects.active = lowpoly

        # Use the same exact source/collection resolution as Autobake, rather
        # than picking an unrelated selected mesh by its polygon count.
        automatic = bool(expected_highpoly_name(lowpoly.name))
        if automatic:
            highpoly, expected, collection = find_matching_highpoly(lowpoly)
            if highpoly is None:
                report_missing_matching_highpoly(self, context, lowpoly, expected, collection)
                return {'CANCELLED'}
        else:
            highpoly = _selected_highpoly_target(context, lowpoly)
        if highpoly is None:
            self.report({'ERROR'}, 'Select a highpoly mesh and make the lowpoly mesh active')
            return {'CANCELLED'}

        target_name = resculpted_name(lowpoly.name) if self.rename_lowpoly else lowpoly.name
        existing = bpy.data.objects.get(target_name)
        if existing is not None and existing != lowpoly:
            self.report({'ERROR'}, 'Resculpting object already exists: ' + target_name)
            return {'CANCELLED'}
        refusal = self.before_setup(lowpoly)
        if refusal:
            self.report({'ERROR'}, refusal)
            return {'CANCELLED'}

        if ngon_count(lowpoly.data):
            if lowpoly.library or lowpoly.data.library:
                self.report({'ERROR'}, 'Make the lowpoly mesh local before triangulating n-gons for Resculpting')
                return {'CANCELLED'}
            if lowpoly.data.shape_keys or any(
                    mod.type == 'MULTIRES' and mod.total_levels for mod in lowpoly.modifiers):
                self.report({'ERROR'}, 'N-gons must be triangulated before creating Multires or shape keys')
                return {'CANCELLED'}

        locked = highpoly.hide_select
        try:
            _set_object_mode(context)
            highpoly.hide_select = False
            if automatic:
                auto_select_matching_highpoly(context, lowpoly)
            else:
                highpoly.hide_viewport = highpoly.hide_render = False
                highpoly.hide_set(False)
            context.view_layer.objects.active = lowpoly
            lowpoly.select_set(True)
            context.view_layer.update()
            original_mesh = lowpoly.data
            prepared_mesh = triangulated_ngon_copy(original_mesh)
            if prepared_mesh is not None:
                lowpoly.data = prepared_mesh
                if original_mesh.users == 0 and not original_mesh.library:
                    bpy.data.meshes.remove(original_mesh)
            add_multires_modifier(context, lowpoly, settings.multires_levels)
            shrinkwrap = add_shrinkwrap_modifier(lowpoly, highpoly, settings.shrinkwrap_limit, settings.shrinkwrap_offset)
            if settings.apply_shrinkwrap:
                result = bpy.ops.object.modifier_apply(modifier=shrinkwrap.name)
                if 'FINISHED' not in result:
                    raise RuntimeError('Could not apply Shrinkwrap')
        finally:
            highpoly.select_set(False)
            highpoly.hide_viewport = highpoly.hide_render = True
            highpoly.hide_set(True)
            highpoly.hide_select = locked
            context.view_layer.objects.active = lowpoly
            lowpoly.select_set(True)
            context.view_layer.update()
        if self.rename_lowpoly:
            lowpoly.name = target_name
            if lowpoly.data.users == 1:
                lowpoly.data.name = target_name
        self.report(
            {"INFO"},
            f"Resculpting setup: {lowpoly.name} projects to {highpoly.name}",
        )
        return self.after_setup(context, lowpoly)

    # Hooks for variations of the setup (Reshape): the lowpoly keeps its name, and the result is processed.
    rename_lowpoly = True

    def before_setup(self, lowpoly):
        """Return an error text to refuse the setup, or None."""
        return None

    def after_setup(self, context, lowpoly):
        return {"FINISHED"}


class OBJECT_OT_polygroups_setup_resculpting(SetupResculptingMixin, bpy.types.Operator):
    bl_idname = "object.polygroups_setup_resculpting"
    bl_label = "Setup Resculpting"
    bl_description = "Auto-select the matching Generated highpoly, prepare the active lowpoly and disable the highpoly afterward"
    bl_options = {"REGISTER", "UNDO"}


RESHAPE_KEY = "Reshape"


def reshape_key(obj):
    keys = getattr(getattr(obj, "data", None), "shape_keys", None)
    return keys.key_blocks.get(RESHAPE_KEY) if keys else None


class OBJECT_OT_polygroups_reshape(SetupResculptingMixin, bpy.types.Operator):
    """Setup Resculpting, then bake the result into the base mesh as a ``Reshape`` shape key."""
    bl_idname = "object.polygroups_reshape"
    bl_label = "Reshape"
    bl_description = ("Run Setup Resculpting, apply the Multires base and remove the modifier; the lowpoly keeps its "
                      "original shape as Basis and the result as the Reshape shape key (a before / after slider)")
    bl_options = {"REGISTER", "UNDO"}
    rename_lowpoly = False

    def before_setup(self, lowpoly):
        if lowpoly.data.shape_keys:
            return "Reshape needs a mesh without shape keys: remove them (or the old Reshape key) first"
        if lowpoly.library or lowpoly.data.library:
            return "Make the lowpoly mesh local before Reshape"
        self._original = [vertex.co.copy() for vertex in lowpoly.data.vertices]
        return None

    def execute(self, context):
        settings = context.scene.polygroups_resculpting_settings
        saved = settings.apply_shrinkwrap
        # The shrinkwrap result is what Reshape keeps, so it must be applied here.
        settings.apply_shrinkwrap = True
        try:
            return super().execute(context)
        finally:
            settings.apply_shrinkwrap = saved

    def after_setup(self, context, lowpoly):
        modifier = lowpoly.modifiers.get(MULTIRES_MODIFIER_NAME)
        if modifier is None or len(lowpoly.data.vertices) != len(self._original):
            self.report({"ERROR"}, "Reshape: the Multires setup did not complete")
            return {"CANCELLED"}
        _set_object_mode(context)
        context.view_layer.objects.active = lowpoly
        if modifier.total_levels and "FINISHED" not in bpy.ops.object.multires_base_apply(modifier=modifier.name):
            self.report({"ERROR"}, "Reshape: Apply Base failed")
            return {"CANCELLED"}
        lowpoly.modifiers.remove(modifier)
        mesh = lowpoly.data
        reshaped = [vertex.co.copy() for vertex in mesh.vertices]
        # Basis = the shape before, Reshape = the result; the slider blends between them.
        basis = lowpoly.shape_key_add(name="Basis", from_mix=False)
        for vertex, key, before in zip(mesh.vertices, basis.data, self._original):
            vertex.co = before
            key.co = before
        key = lowpoly.shape_key_add(name=RESHAPE_KEY, from_mix=False)
        for point, after in zip(key.data, reshaped):
            point.co = after
        key.slider_min, key.slider_max, key.value = 0.0, 1.0, 1.0
        lowpoly.active_shape_key_index = 1
        mesh.update()
        self.report({"INFO"}, f"Reshape: {lowpoly.name} has a '{RESHAPE_KEY}' shape key (0 = before, 1 = after)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_toggle_reshape(bpy.types.Operator):
    bl_idname = "object.polygroups_toggle_reshape"
    bl_label = "Show / Hide Reshape"
    bl_description = "Switch the Reshape shape key of the selected meshes between 0 (before) and 1 (after)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(reshape_key(obj) for obj in _reshape_targets(context))

    def execute(self, context):
        targets = [obj for obj in _reshape_targets(context) if reshape_key(obj)]
        # One decision for all meshes: hide when the active one shows the reshape, otherwise show.
        lead = reshape_key(context.active_object) or reshape_key(targets[0])
        value = 0.0 if lead.value > 0.5 else 1.0
        for obj in targets:
            reshape_key(obj).value = value
        self.report({"INFO"}, f"Reshape {'shown' if value else 'hidden'} on {len(targets)} mesh(es)")
        return {"FINISHED"}


def _reshape_targets(context):
    objects = list(context.selected_objects)
    if context.active_object and context.active_object not in objects:
        objects.append(context.active_object)
    return [obj for obj in objects if obj.type == "MESH"]
