"""Screen-projected, editable local contour cutters.

The sketch is a ruled sheet: each screen point has a front and a back vertex.
Both rails project to the same stroke, while Edit Mode can move either rail
independently before the sheet is promoted to a regular Local Contour cutter.
"""

import bpy
from math import ceil
from mathutils import Vector
from bpy_extras import view3d_utils

from . import object_seam_cutter as cutter_api


TEMP_PROP = "polygroups_local_contour_sketch"
TARGET_PROP = "polygroups_local_contour_sketch_target"


def _simplify_screen_points(points, tolerance=2.0):
    if len(points) < 3:
        return points
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        start, end = pending.pop()
        a, b = points[start], points[end]
        segment = b - a
        length_squared = segment.length_squared
        best_index, best_distance = None, tolerance
        for index in range(start + 1, end):
            point = points[index]
            amount = max(0.0, min(1.0, (point - a).dot(segment) / length_squared)) if length_squared else 0.0
            distance = (point - a.lerp(b, amount)).length
            if distance > best_distance:
                best_index, best_distance = index, distance
        if best_index is not None:
            keep.add(best_index)
            pending.extend(((start, best_index), (best_index, end)))
    return [points[index] for index in sorted(keep)]


def _sample_screen_path(points, spacing=4.0):
    """Sample long Path segments so surface hits are found between clicks."""
    points = [Vector(point) for point in points]
    length = sum((b - a).length for a, b in zip(points, points[1:]))
    if length < 2.0:
        raise ValueError("Draw a longer path across the target")
    spacing = max(spacing, length / 2048.0)
    sampled = [points[0]]
    for start, end in zip(points, points[1:]):
        count = max(1, ceil((end - start).length / spacing))
        sampled.extend(start.lerp(end, index / count) for index in range(1, count + 1))
    return sampled


def _projected_sheet(region, rv3d, screen_points, target):
    if len(screen_points) < 2:
        raise ValueError("Place at least two points")
    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    center = sum(corners, Vector()) / len(corners)
    direction = view3d_utils.region_2d_to_vector_3d(
        region, rv3d, Vector((region.width * 0.5, region.height * 0.5))
    ).normalized()
    depths = [(corner - center).dot(direction) for corner in corners]
    diagonal = max((corner - center).length for corner in corners) * 2.0
    # These planes only bracket ray casts. They never become the cutter surface.
    search_margin = max(diagonal * 0.1, 0.01)
    front = min(depths) - search_margin
    back = max(depths) + search_margin
    settings = bpy.context.scene.polygroups_object_seam_cutter_settings
    clearance = max(settings.cutter_contour_offset, diagonal * 1e-5, 1e-6)
    world_to_local = evaluated.matrix_world.inverted_safe()

    def surface_point(start, end):
        local_start = world_to_local @ start
        local_span = (world_to_local @ end) - local_start
        hit, location, _normal, _face = evaluated.ray_cast(
            local_start, local_span.normalized(), distance=local_span.length
        )
        return evaluated.matrix_world @ location if hit else None

    samples = []
    for point in _sample_screen_path(screen_points):
        origin = view3d_utils.region_2d_to_origin_3d(
            region, rv3d, Vector(point), clamp=max(diagonal * 2.0, 1.0)
        )
        ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, Vector(point)).normalized()
        divisor = ray.dot(direction)
        if divisor < 1e-5:
            raise ValueError("View ray is parallel to the cutter depth")
        front_bound, back_bound = (
            origin + ray * ((center + direction * depth - origin).dot(direction) / divisor)
            for depth in (front, back)
        )
        front_hit = surface_point(front_bound, back_bound)
        # The next crossing behind the visible surface is the exit of that
        # local shell. A reverse ray would choose the farthest disconnected
        # component and stretch the sheet through empty space between parts.
        back_hit = (surface_point(front_hit + ray * max(diagonal * 1e-5, 1e-6), back_bound)
                    if front_hit is not None else None)
        depth_pair = None
        if front_hit is not None and back_hit is not None:
            depth_pair = ((front_hit - center).dot(direction),
                          (back_hit - center).dot(direction))
        samples.append((origin, ray, divisor, depth_pair))

    hit_indices = [index for index, sample in enumerate(samples) if sample[3] is not None]
    if not hit_indices:
        raise ValueError("The path must cross the front and back surfaces of the target")
    nearest_left = []
    previous_hit = None
    for index, sample in enumerate(samples):
        if sample[3] is not None:
            previous_hit = index
        nearest_left.append(previous_hit)
    nearest_right = [None] * len(samples)
    next_hit = None
    for index in range(len(samples) - 1, -1, -1):
        if samples[index][3] is not None:
            next_hit = index
        nearest_right[index] = next_hit

    # Keep just one short off-silhouette segment at each end. Drawing can begin
    # far from the object without producing a long, bounding-box-sized sheet.
    first = max(0, hit_indices[0] - 1)
    last = min(len(samples) - 1, hit_indices[-1] + 1)
    vertices = []
    for index in range(first, last + 1):
        origin, ray, divisor, depth_pair = samples[index]
        if depth_pair is None:
            left = nearest_left[index]
            right = nearest_right[index]
            if left is None:
                depth_pair = samples[right][3]
            elif right is None:
                depth_pair = samples[left][3]
            else:
                factor = (index - left) / (right - left)
                depth_pair = tuple(
                    samples[left][3][side] * (1.0 - factor) + samples[right][3][side] * factor
                    for side in (0, 1)
                )
        for side, depth in enumerate(depth_pair):
            location = origin + ray * ((center + direction * depth - origin).dot(direction) / divisor)
            vertices.append(location + ray * (clearance if side else -clearance))
    faces = [(index * 2, index * 2 + 1, index * 2 + 3, index * 2 + 2)
             for index in range(len(vertices) // 2 - 1)]
    return vertices, faces


def _make_sketch(context, target, region, rv3d, points, source):
    vertices, faces = _projected_sheet(region, rv3d, points, target)
    mesh = bpy.data.meshes.new("Local_Contour_Sketch")
    mesh.from_pydata([tuple(point) for point in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Local_Contour_Sketch", mesh)
    cutter_api._tool_collection("LOCAL_CONTOUR").objects.link(obj)
    obj[TEMP_PROP] = source
    obj[TARGET_PROP] = target.name
    obj.display_type = "WIRE"
    obj.show_in_front = True
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def _draw_overlay(operator):
    if not operator._points:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader

    points = list(operator._points)
    if operator._mouse_pos is not None and not operator._drawing:
        points.append(operator._mouse_pos)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.line_width_set(2.0)
    try:
        if len(points) >= 2:
            batch = batch_for_shader(shader, "LINE_STRIP", {"pos": points})
            shader.bind()
            shader.uniform_float("color", (0.15, 1.0, 0.55, 1.0))
            batch.draw(shader)
        if getattr(operator, "_mode", getattr(operator, "mode", None)) == "PATH":
            batch = batch_for_shader(shader, "POINTS", {"pos": points})
            shader.bind()
            shader.uniform_float("color", (1.0, 0.85, 0.25, 1.0))
            gpu.state.point_size_set(6.0)
            batch.draw(shader)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.point_size_set(1.0)


class _LocalContourSketchInteraction:
    mode = "PATH"
    _points = None
    _mouse_pos = None
    _drawing = False
    _draw_handle = None

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.active_object is not None and context.active_object.type == "MESH" and not context.active_object.get(TEMP_PROP)

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._area = None
        self._region = None
        self._rv3d = None
        self._points = []
        self._mouse_pos = None
        self._drawing = False
        self._draw_handle = None
        self._view_matrix = None
        if self.use_event_as_start:
            self._add_point(context, event, force=True)
            self._drawing = self.mode == "DRAW"
        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (self,), "WINDOW", "POST_PIXEL"
        )
        context.workspace.status_text_set(
            "Local Contour: Ctrl+Shift+click points, Backspace undo, Space create editable sheet"
            if self.mode == "PATH" else
            "Local Contour: Ctrl+drag freely, release to create editable sheet"
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}
        if event.type == "SPACE" and event.value == "PRESS":
            if self.mode != "PATH":
                return {"RUNNING_MODAL"}
            return self._create_sketch(context)
        if event.type == "BACK_SPACE" and event.value == "PRESS" and not self._drawing:
            if self._points:
                self._points.pop()
                self._tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE",
                          "WHEELINMOUSE", "WHEELOUTMOUSE", "TRACKPADPAN", "TRACKPADZOOM"}:
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.alt:
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            if self._drawing and event.ctrl:
                self._add_point(context, event)
            elif self._points:
                _area, region, _rv3d, position = cutter_api._view3d_under_mouse(context, event)
                if region == self._region:
                    self._mouse_pos = position
                    self._tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and event.ctrl:
            if self.mode == "PATH" and not event.shift:
                return {"RUNNING_MODAL"}
            if self.mode == "DRAW":
                self._drawing = True
            self._add_point(context, event, force=True)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._drawing:
            self._add_point(context, event)
            self._drawing = False
            if len(self._points) < 2:
                self._points.clear()
                self.report({"WARNING"}, "Drag to draw a contour")
                return {"RUNNING_MODAL"}
            return self._create_sketch(context)
        return {"PASS_THROUGH"}

    def _create_sketch(self, context):
        if len(self._points) < 2:
            self.report({"WARNING"}, "Draw at least two distinct points")
            return {"RUNNING_MODAL"}
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}
        if any(abs(a - b) > 1e-5 for row_a, row_b in zip(self._view_matrix, self._rv3d.view_matrix)
               for a, b in zip(row_a, row_b)):
            self.report({"WARNING"}, "Finish the sketch from the original view")
            return {"RUNNING_MODAL"}
        try:
            _make_sketch(context, target, self._region, self._rv3d,
                         _simplify_screen_points(self._points) if self.mode == "DRAW" else self._points,
                         self.mode)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"RUNNING_MODAL"}
        self._finish(context)
        self.report({"INFO"}, "Edit the front/back sheet in Edit Mode, then Finalize Local Contour")
        return {"FINISHED"}

    def _add_point(self, context, event, force=False):
        area, region, rv3d, position = cutter_api._view3d_under_mouse(context, event)
        if region is None:
            return False
        if self._region is None:
            self._area, self._region, self._rv3d = area, region, rv3d
            self._view_matrix = rv3d.view_matrix.copy()
        elif region != self._region or area != self._area:
            return False
        position = Vector(position)
        if self._points and (position - self._points[-1]).length < (3.0 if self.mode == "DRAW" and not force else 1.0):
            return False
        self._points.append(position)
        self._mouse_pos = None
        self._tag_redraw()
        return True

    def _tag_redraw(self):
        if self._area is not None:
            self._area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_draw_local_contour_path(_LocalContourSketchInteraction, bpy.types.Operator):
    bl_idname = "object.polygroups_draw_local_contour_path"
    bl_label = "Local Contour Path"
    bl_description = "Place projected path points to create an editable front/back cutter sheet"
    bl_options = {"REGISTER", "UNDO"}
    mode = "PATH"
    use_event_as_start: bpy.props.BoolProperty(default=False, options={"HIDDEN"})


class OBJECT_OT_polygroups_draw_local_contour_draw(_LocalContourSketchInteraction, bpy.types.Operator):
    bl_idname = "object.polygroups_draw_local_contour_draw"
    bl_label = "Local Contour Draw"
    bl_description = "Freehand draw a projected editable front/back cutter sheet"
    bl_options = {"REGISTER", "UNDO"}
    mode = "DRAW"
    use_event_as_start: bpy.props.BoolProperty(default=False, options={"HIDDEN"})


def _draw_gesture_overlay(operator):
    if operator._mode == "PLANE":
        cutter_api._draw_cutter_local_ring_overlay(operator)
    elif operator._mode in {"PATH", "DRAW"}:
        _draw_overlay(operator)


class OBJECT_OT_polygroups_local_contour_gesture(bpy.types.Operator):
    """Disambiguate click, drag and Shift-click in the main contour tool."""

    bl_idname = "object.polygroups_local_contour_gesture"
    bl_label = "Local Contour Gesture"
    bl_description = "Ctrl+click twice for a section, Ctrl+drag for Draw, Ctrl+Shift+click for Path"
    bl_options = {"REGISTER", "UNDO"}
    use_event_as_start: bpy.props.BoolProperty(default=False, options={"HIDDEN"})
    _drag_threshold = 6.0

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (context.mode == "OBJECT" and obj is not None and obj.type == "MESH"
                and not obj.get(TEMP_PROP) and not obj.get(cutter_api.CUTTER_PROP))

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._mode = "WAIT"
        self._points = []
        self._mouse_pos = None
        self._drawing = False
        self._button_down = False
        self._press_pos = None
        self._press_shift = False
        self._start_pos = None
        self._start_area = self._area = None
        self._start_region = self._region = None
        self._start_rv3d = self._rv3d = None
        self._view_matrix = None
        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_gesture_overlay, (self,), "WINDOW", "POST_PIXEL"
        )
        self._set_status(context)
        if self.use_event_as_start:
            self._handle_press(context, event)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}
        if event.type == "SPACE" and event.value == "PRESS":
            return self._finish_sketch(context, "PATH") if self._mode == "PATH" else {"RUNNING_MODAL"}
        if event.type == "BACK_SPACE" and event.value == "PRESS":
            if self._mode == "PATH" and self._points:
                self._points.pop()
            elif self._mode == "PLANE":
                self._start_pos = None
                self._mode = "WAIT"
            self._tag_redraw()
            self._set_status(context)
            return {"RUNNING_MODAL"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE",
                          "WHEELINMOUSE", "WHEELOUTMOUSE", "TRACKPADPAN", "TRACKPADZOOM"}:
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.alt:
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            area, region, _rv3d, position = cutter_api._view3d_under_mouse(context, event)
            if region is not None and region == self._region and area == self._area:
                self._mouse_pos = Vector(position)
                if self._mode == "PLANE" and event.shift and self._start_pos is not None:
                    self._mouse_pos = Vector(cutter_api._axis_locked_region_pos(
                        self._start_pos, self._mouse_pos, True
                    ))
                if self._button_down and self._mode != "PATH":
                    if self._mode != "DRAW" and (self._mouse_pos - self._press_pos).length >= self._drag_threshold:
                        self._mode = "DRAW"
                        self._points = [self._press_pos.copy()]
                        self._start_pos = None
                        self._drawing = True
                        self._set_status(context)
                    if self._mode == "DRAW":
                        self._append_point(self._mouse_pos, 3.0)
                self._tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and (event.ctrl or self._mode == "PLANE"):
            self._handle_press(context, event)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._button_down:
            self._button_down = False
            if self._mode == "DRAW":
                area, region, _rv3d, position = cutter_api._view3d_under_mouse(context, event)
                if region == self._region and area == self._area:
                    self._append_point(Vector(position), 1.0)
                self._drawing = False
                return self._finish_sketch(context, "DRAW")
            return self._finish_click(context)
        return {"PASS_THROUGH"}

    def _handle_press(self, context, event):
        area, region, rv3d, position = cutter_api._view3d_under_mouse(context, event)
        if region is None:
            return
        if self._region is None:
            self._area = self._start_area = area
            self._region = self._start_region = region
            self._rv3d = self._start_rv3d = rv3d
            self._view_matrix = rv3d.view_matrix.copy()
        elif region != self._region or area != self._area:
            self.report({"WARNING"}, "Use the same viewport for this contour")
            return
        position = Vector(position)
        if event.ctrl and event.shift:
            if self._mode != "PATH":
                self._mode = "PATH"
                self._points = []
                self._start_pos = None
            self._append_point(position, 1.0)
            self._mouse_pos = None
        elif self._mode != "PATH":
            if self._mode == "DRAW":
                self._mode = "WAIT"
                self._points = []
            self._press_pos = position
            self._press_shift = event.shift
            self._button_down = True
            self._mouse_pos = position
        self._set_status(context)
        self._tag_redraw()

    def _finish_click(self, context):
        if self._press_pos is None:
            return {"RUNNING_MODAL"}
        if self._start_pos is None:
            self._start_pos = self._press_pos.copy()
            self._mode = "PLANE"
            self._set_status(context)
            self._tag_redraw()
            return {"RUNNING_MODAL"}
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}
        settings = context.scene.polygroups_object_seam_cutter_settings
        end_pos = cutter_api._axis_locked_region_pos(
            self._start_pos, self._press_pos, self._press_shift
        )
        try:
            finished = cutter_api.OBJECT_OT_polygroups_draw_cutter_local_contour._create_cutter(
                self, context, target, end_pos, settings
            )
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"RUNNING_MODAL"}
        finished.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _finish_sketch(self, context, source):
        if len(self._points) < 2:
            self.report({"WARNING"}, "Draw at least two distinct points")
            return {"RUNNING_MODAL"}
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}
        if any(abs(a - b) > 1e-5 for row_a, row_b in zip(self._view_matrix, self._rv3d.view_matrix)
               for a, b in zip(row_a, row_b)):
            self.report({"WARNING"}, "Finish the sketch from the original view")
            return {"RUNNING_MODAL"}
        try:
            _make_sketch(context, target, self._region, self._rv3d,
                         _simplify_screen_points(self._points) if source == "DRAW" else self._points,
                         source)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"RUNNING_MODAL"}
        self._finish(context)
        self.report({"INFO"}, "Edit the front/back sheet, then Finalize Local Contour")
        return {"FINISHED"}

    def _append_point(self, position, distance):
        if not self._points or (position - self._points[-1]).length >= distance:
            self._points.append(position.copy())

    def _set_status(self, context):
        if self._mode == "PATH":
            message = "Local Contour Path: Ctrl+Shift+click points, Space creates editable sheet"
        elif self._mode == "DRAW":
            message = "Local Contour Draw: release Ctrl+drag to create editable sheet"
        elif self._mode == "PLANE":
            message = "Local Contour: click B for two-point cut, or Ctrl+drag to draw"
        else:
            message = "Local Contour: Ctrl+click twice, Ctrl+drag Draw, Ctrl+Shift+click Path"
        context.workspace.status_text_set(message)

    def _tag_redraw(self):
        if self._area is not None:
            self._area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_finalize_local_contour(bpy.types.Operator):
    bl_idname = "object.polygroups_finalize_local_contour"
    bl_label = "Finalize Local Contour"
    bl_description = "Convert the selected editable local contour sheet to an applicable cutter"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(
            obj.type == "MESH" and obj.get(TEMP_PROP) for obj in context.selected_objects
        )

    def execute(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        sketches = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.get(TEMP_PROP)]
        targets = {obj.get(TARGET_PROP) for obj in sketches}
        if len(targets) != 1:
            self.report({"WARNING"}, "Finalize sketches for one target at a time")
            return {"CANCELLED"}
        target = bpy.data.objects.get(next(iter(targets)))
        if target is None or target.type != "MESH":
            self.report({"WARNING"}, "Original target mesh was not found")
            return {"CANCELLED"}
        for obj in sketches:
            if len(obj.data.polygons) == 0:
                self.report({"WARNING"}, "Editable sheet has no faces")
                return {"CANCELLED"}
        for obj in sketches:
            source = obj[TEMP_PROP]
            del obj[TEMP_PROP]
            del obj[TARGET_PROP]
            obj.name = "Seam_Cutter_Local_Contour_" + source.title()
            obj.display_type = "TEXTURED"
            obj.show_in_front = False
            obj[cutter_api.CUTTER_PROP] = True
            obj[cutter_api.CUTTER_TYPE_PROP] = "LOCAL_CONTOUR"
            obj[cutter_api.CUTTER_SOURCE_TOOL_PROP] = "LOCAL_CONTOUR_" + source
            obj[cutter_api.CUTTER_PIN_SEAMS_PROP] = settings.cutter_local_contour_mark_pinned
            material = cutter_api._material(settings.cutter_alpha)
            if obj.data.materials:
                obj.data.materials[0] = material
            else:
                obj.data.materials.append(material)
            cutter_api._add_solidify_modifier(obj, settings.cutter_thickness)
        target.select_set(True)
        context.view_layer.objects.active = target
        self.report({"INFO"}, f"Finalized {len(sketches)} Local Contour cutter(s)")
        return {"FINISHED"}
