"""Draw a world-aligned box and fill it with finite cutter planes."""
from itertools import product

import bpy
from mathutils import Vector, Quaternion
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils

from ..localization import t
from .object_seam_cutter import (
    CUTTER_PROP, CUTTER_TYPE_PROP, _add_solidify_modifier, _material,
    _tool_collection, _view3d_under_mouse, _surface_hit_from_region_pos, _target_bounds,
)

TOOL_ID = "polygroups_generator.draw_cutter_grid_tool"


def evaluated_bounds(context, target):
    """World-aligned bounds of the displayed mesh, including modifiers."""
    evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        if mesh is None or not mesh.vertices:
            raise ValueError("The active mesh is empty")
        lower = Vector((float("inf"),) * 3)
        upper = -lower
        for vert in mesh.vertices:
            point = evaluated.matrix_world @ vert.co
            for axis in range(3):
                lower[axis] = min(lower[axis], point[axis])
                upper[axis] = max(upper[axis], point[axis])
        return lower, upper
    finally:
        evaluated.to_mesh_clear()


def select_grid(context, target, cutters):
    bpy.ops.object.select_all(action="DESELECT")
    for cutter in cutters:
        cutter.select_set(True)
    target.select_set(True)
    context.view_layer.objects.active = target


class OBJECT_OT_polygroups_generate_cutter_grid(bpy.types.Operator):
    bl_idname = "object.polygroups_generate_cutter_grid"
    bl_label = "Generate Auto"
    bl_description = "Create the cutter grid inside the active object's world bounding box, including modifiers"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.active_object is not None and context.active_object.type == "MESH"

    def execute(self, context):
        target = context.active_object
        try:
            cutters = create_grid(*evaluated_bounds(context, target),
                                  context.scene.polygroups_object_seam_cutter_settings)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        select_grid(context, target, cutters)
        self.report({"INFO"}, t(context, "grid_created", count=len(cutters)))
        return {"FINISHED"}


def grid_planes(lower, upper, axes, counts):
    """Exactly N internal planes along each enabled world axis (no boundary planes)."""
    for axis in range(3):
        if not axes[axis]:
            continue
        count = counts[axis]
        u, v = [i for i in range(3) if i != axis]
        for index in range(count):
            position = lower[axis] + (upper[axis] - lower[axis]) * (index + 1) / (count + 1)
            corners = []
            for a, b in ((0, 0), (1, 0), (1, 1), (0, 1)):
                point = Vector(lower)
                point[axis] = position
                point[u] = upper[u] if a else lower[u]
                point[v] = upper[v] if b else lower[v]
                corners.append(point)
            yield axis, index, corners


def create_grid(lower, upper, settings):
    if any(upper[i] - lower[i] <= 1e-6 for i in range(3)):
        raise ValueError("The cutter volume must have a non-zero size on every axis")
    if not any(enabled and count for enabled, count in zip(settings.cutter_grid_axes, settings.cutter_grid_counts)):
        raise ValueError("Enable at least one axis with at least one cutter plane")
    collection = bpy.data.collections.new("Seam Cutter Grid")
    _tool_collection("GRID_PLANE").children.link(collection)
    created = []
    try:
        for axis, index, corners in grid_planes(lower, upper, settings.cutter_grid_axes, settings.cutter_grid_counts):
            center = sum(corners, Vector()) / 4
            mesh = bpy.data.meshes.new("Grid Plane")
            try:
                mesh.from_pydata([p - center for p in corners], [], [(0, 1, 2, 3)])
                mesh.update()
                obj = bpy.data.objects.new(f"Seam_Grid_{'XYZ'[axis]}_{index + 1:02d}", mesh)
            except Exception:
                bpy.data.meshes.remove(mesh)
                raise
            created.append(obj)
            collection.objects.link(obj)
            obj.location = center
            obj[CUTTER_PROP] = True
            obj[CUTTER_TYPE_PROP] = "GRID_PLANE"
            obj.data.materials.append(_material(settings.cutter_alpha))
            _add_solidify_modifier(obj, settings.cutter_thickness)
        return created
    except Exception:
        for obj in created:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)
        bpy.data.collections.remove(collection)
        raise


def draw_grid_preview(operator):
    context = bpy.context
    if context.area != operator._area or context.region != operator._region:
        return
    bounds = operator.bounds()
    if bounds is None:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    lower, upper = bounds
    corners = [Vector(tuple(upper[i] if bits[i] else lower[i] for i in range(3)))
               for bits in product((0, 1), repeat=3)]
    edges = [corners[i] for a in range(8) for b in range(a + 1, 8)
             if (a ^ b) in (1, 2, 4) for i in (a, b)]
    groups = [[], [], []]
    settings = context.scene.polygroups_object_seam_cutter_settings
    for axis, _, plane in grid_planes(lower, upper, settings.cutter_grid_axes, settings.cutter_grid_counts):
        groups[axis].extend(plane[i] for a in range(4) for i in (a, (a + 1) % 4))
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    blend, depth = gpu.state.blend_get(), gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", 1.5)
        for points, color in zip([edges] + groups,
                                 [(1, .8, .2, 1), (1, .25, .25, .7), (.25, 1, .35, .7), (.3, .55, 1, .7)]):
            if points:
                shader.uniform_float("color", color)
                batch_for_shader(shader, "LINES", {"pos": points}).draw(shader)
    finally:
        gpu.state.blend_set(blend)
        gpu.state.depth_test_set(depth)


class OBJECT_OT_polygroups_draw_cutter_grid(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_grid"
    bl_label = "Draw Cutter Grid Volume"
    bl_description = "Draw two base corners, then set depth; create finite cutter planes along world X/Y/Z"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.active_object is not None and context.active_object.type == "MESH"

    def invoke(self, context, event):
        self._target = context.active_object.name
        self._area = self._region = self._view = self._start = self._end = None
        self._handle = None
        self._stage = 0
        self._saved_view = None
        self._auto_rotated = False
        if self.use_event_as_start and not self.start(context, event):
            return {"CANCELLED"}
        context.workspace.status_text_set(t(context, "grid_hint_base"))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def start(self, context, event):
        area, region, view, mouse = _view3d_under_mouse(context, event)
        if region is None:
            return False
        self._area, self._region, self._view = area, region, view
        target = bpy.data.objects.get(self._target)
        evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
        hit = _surface_hit_from_region_pos(region, view, mouse, evaluated)
        anchor = hit[0] if hit else _target_bounds(evaluated)[0]
        direction = view3d_utils.region_2d_to_vector_3d(region, view, mouse)
        self._depth_axis = max(range(3), key=lambda i: abs(direction[i]))
        self._normal = Vector(tuple(1 if i == self._depth_axis else 0 for i in range(3)))
        self._sign = 1 if direction[self._depth_axis] >= 0 else -1
        if hit is None:
            # Outside the silhouette, anchor the base at the near side of the
            # target bounds so the default cube extends through the target.
            depths = [(evaluated.matrix_world @ Vector(p))[self._depth_axis] for p in evaluated.bound_box]
            anchor[self._depth_axis] = min(depths) if self._sign > 0 else max(depths)
        self._anchor = anchor
        self._start = self.project(mouse)
        if self._start is None:
            return False
        self._end = self._start.copy()
        self._depth = 0
        self._stage = 1
        self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_grid_preview, (self,), "WINDOW", "POST_VIEW")
        area.tag_redraw()
        return True

    def project(self, mouse):
        origin = view3d_utils.region_2d_to_origin_3d(self._region, self._view, mouse)
        direction = view3d_utils.region_2d_to_vector_3d(self._region, self._view, mouse)
        return intersect_line_plane(origin, origin + direction, self._anchor, self._normal, False)

    def bounds(self):
        if self._start is None:
            return None
        other = self._end.copy()
        other[self._depth_axis] = self._start[self._depth_axis] + self._depth
        return (Vector(tuple(min(a, b) for a, b in zip(self._start, other))),
                Vector(tuple(max(a, b) for a, b in zip(self._start, other))))

    def update(self, mouse):
        if self._stage == 1:
            point = self.project(mouse)
            if point is not None:
                self._end = point
                self._depth = self._sign * max(abs(point[i] - self._start[i]) for i in range(3) if i != self._depth_axis)
        elif self._auto_rotated:
            point = view3d_utils.region_2d_to_location_3d(self._region, self._view, mouse, self._start)
            self._depth = point[self._depth_axis] - self._start[self._depth_axis]
        else:
            self._depth = self._base_depth + self._sign * (mouse.y - self._depth_mouse_y) * self._pixel_scale

    def rotate_for_depth(self):
        view = self._view
        self._saved_view = (view.view_rotation.copy(), view.view_location.copy(),
                            view.view_distance, view.view_perspective)
        lower, upper = self.bounds()
        # Right view exposes Y after a front/back base and Z after a top base.
        # A front view exposes X when drawing the base from the side.
        view.view_rotation = (Quaternion((2 ** -.5, 2 ** -.5, 0, 0))
                              if self._depth_axis == 0 else Quaternion((.5, .5, .5, .5)))
        view.view_perspective = "ORTHO"
        view.view_location = (lower + upper) * .5
        view.update()
        self._auto_rotated = True
        self._area.tag_redraw()

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self.finish(context, cancelled=True)
            return {"CANCELLED"}
        target = bpy.data.objects.get(self._target)
        if target is None or context.mode != "OBJECT":
            self.finish(context, cancelled=True)
            return {"CANCELLED"}
        area, region, _, mouse = _view3d_under_mouse(context, event)
        if self._stage and (area != self._area or region != self._region):
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE" and self._stage:
            self.update(Vector(mouse))
            lower, upper = self.bounds()
            size = upper - lower
            hint = ("grid_hint_base" if self._stage == 1 else
                    "grid_hint_depth_side" if self._auto_rotated else "grid_hint_depth")
            context.workspace.status_text_set(
                f"{t(context, hint)} | X: {size.x:.4f}  Y: {size.y:.4f}  Z: {size.z:.4f}")
            self._area.tag_redraw()
        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}
        if self._stage == 0:
            self.start(context, event)
            return {"RUNNING_MODAL"}
        self.update(Vector(mouse))
        if self._stage == 1:
            lower, upper = self.bounds()
            if any(upper[i] - lower[i] < 1e-6 for i in range(3)):
                self.report({"WARNING"}, "Draw a larger rectangular base")
                return {"RUNNING_MODAL"}
            self._stage = 2
            self._depth_mouse_y, self._base_depth = mouse[1], self._depth
            a = view3d_utils.region_2d_to_location_3d(region, self._view, Vector(mouse), self._start)
            b = view3d_utils.region_2d_to_location_3d(region, self._view, Vector(mouse) + Vector((0, 1)), self._start)
            self._pixel_scale = max((b - a).length, 1e-8)
            if context.scene.polygroups_object_seam_cutter_settings.cutter_grid_auto_rotate:
                self.rotate_for_depth()
            hint = "grid_hint_depth_side" if self._auto_rotated else "grid_hint_depth"
            context.workspace.status_text_set(t(context, hint))
            return {"RUNNING_MODAL"}
        try:
            cutters = create_grid(*self.bounds(), context.scene.polygroups_object_seam_cutter_settings)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"RUNNING_MODAL"}
        except Exception:
            self.finish(context, cancelled=True)
            raise
        select_grid(context, target, cutters)
        self.finish(context)
        self.report({"INFO"}, t(context, "grid_created", count=len(cutters)))
        return {"FINISHED"}

    def finish(self, context, cancelled=False):
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None
        if cancelled and self._saved_view is not None:
            rotation, location, distance, perspective = self._saved_view
            self._view.view_rotation = rotation
            self._view.view_location = location
            self._view.view_distance = distance
            self._view.view_perspective = perspective
            self._view.update()
        context.workspace.status_text_set(None)
        if self._area is not None:
            self._area.tag_redraw()
