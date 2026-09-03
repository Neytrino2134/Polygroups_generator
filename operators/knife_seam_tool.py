import bpy
import bmesh
import math
from bpy.app.handlers import persistent
from mathutils import Vector

from ..localization import t


ACTIVE_KNIFE_OPERATORS = []


@persistent
def stop_knife_seams(*_args):
    for operator in list(ACTIVE_KNIFE_OPERATORS):
        operator._finish(bpy.context)


def _draw_knife_preview(operator):
    if (operator._finished or bpy.context.area != operator._area
            or bpy.context.region != operator._region):
        return
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader

    start = operator._start_region_pos
    end = operator._end_region_pos or operator._mouse_region_pos
    if end is None:
        return
    scale = bpy.context.preferences.system.ui_scale
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    fill_shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    previous_blend = gpu.state.blend_get()
    previous_depth = gpu.state.depth_test_get()

    def line(points, color, width):
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", width * scale)
        shader.uniform_float("color", color)
        batch_for_shader(shader, "LINES", {"pos": points}).draw(shader)

    def dot(point, radius, color):
        points = [(point[0], point[1])]
        points.extend((point[0] + radius * scale * math.cos(i * math.tau / 24),
                       point[1] + radius * scale * math.sin(i * math.tau / 24))
                      for i in range(25))
        fill_shader.bind()
        fill_shader.uniform_float("color", color)
        batch_for_shader(fill_shader, "TRI_FAN", {"pos": points}).draw(fill_shader)

    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        cyan = (0.1, 0.85, 1.0, 1.0)
        gold = (1.0, 0.65, 0.12, 1.0)
        if start is not None:
            direction = Vector(end) - Vector(start)
            if direction.length >= 2:
                direction.normalize()
                extent = math.hypot(operator._region.width, operator._region.height)
                points = []
                distance = -extent
                while distance < extent:
                    points.extend((Vector(start) + direction * distance,
                                   Vector(start) + direction * (distance + 7 * scale)))
                    distance += 13 * scale
                line(points, (1.0, 0.65, 0.12, 0.55), 1)
                line((start, end), (0.02, 0.02, 0.02, 0.9), 5)
                line((start, end), cyan, 2.5)
            dot(start, 6, (0.03, 0.03, 0.03, 1))
            dot(start, 4, gold)
        dot(end, 6, (0.03, 0.03, 0.03, 1))
        dot(end, 4, cyan if operator._end_region_pos is None else gold)
        blf.size(0, 13 * scale)
        blf.color(0, 1, 1, 1, 1)
        # An on-screen hint remains visible even if Blender's status bar is hidden.
        hint = operator._hint()
        x, y = 24 * scale, 40 * scale
        width, height = blf.dimensions(0, hint)
        fill_shader.bind()
        fill_shader.uniform_float("color", (0.025, 0.025, 0.025, 0.85))
        batch_for_shader(fill_shader, "TRI_FAN", {"pos": (
            (x - 8 * scale, y - 6 * scale), (x + width + 8 * scale, y - 6 * scale),
            (x + width + 8 * scale, y + height + 6 * scale), (x - 8 * scale, y + height + 6 * scale),
        )}).draw(fill_shader)
        blf.position(0, x, y, 0)
        blf.draw(0, hint)
    finally:
        gpu.state.depth_test_set(previous_depth)
        gpu.state.blend_set(previous_blend)


def _finish_native_cut(mesh_names, mark_seam, clear_selection):
    count = 0
    for name in mesh_names:
        mesh = bpy.data.meshes.get(name)
        if mesh is None or not mesh.is_editmode:
            continue
        bm = bmesh.from_edit_mesh(mesh)
        for edge in bm.edges:
            if edge.select and not edge.hide:
                if mark_seam:
                    edge.seam = True
                count += 1
        if clear_selection:
            for elements in (bm.faces, bm.edges, bm.verts):
                for element in elements:
                    element.select = False
            bm.select_history.clear()
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    return count


class MESH_OT_polygroups_finish_knife_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_finish_knife_seam"
    bl_label = "Mark Knife Cuts as Seams"
    bl_options = {"INTERNAL"}

    mark_seam: bpy.props.BoolProperty(default=True)
    clear_selection: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        _finish_native_cut(
            [obj.data.name for obj in context.objects_in_mode_unique_data if obj.type == "MESH"],
            self.mark_seam, self.clear_selection,
        )
        return {"FINISHED"}


class MESH_OT_polygroups_native_knife_seam(bpy.types.Macro):
    bl_idname = "mesh.polygroups_native_knife_seam"
    bl_label = "Multi-Point Knife Seam"
    bl_options = {"UNDO", "INTERNAL"}


def _screen_plane_world(context, start_region_pos, end_region_pos):
    from bpy_extras import view3d_utils

    region = context.region
    rv3d = context.region_data
    start = Vector(start_region_pos)
    end = Vector(end_region_pos)

    if (end - start).length < 2.0:
        return None, None

    start_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, start)
    end_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, end)
    start_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, start)
    end_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, end)

    if rv3d.is_perspective:
        plane_co = start_origin
        plane_no = start_vector.cross(end_vector)
    else:
        plane_co = start_origin
        plane_no = (end_origin - start_origin).cross(start_vector)

    if plane_no.length < 0.000001:
        return None, None

    plane_no.normalize()
    return plane_co, plane_no


def _world_plane_to_local(obj, plane_co, plane_no):
    matrix = obj.matrix_world
    local_co = matrix.inverted() @ plane_co
    local_no = matrix.to_3x3().transposed() @ plane_no
    local_no.normalize()
    return local_co, local_no


def _stable_view_cut(
    obj_name,
    plane_co,
    plane_no,
    only_selected,
    mark_seam,
    clear_selection_after_cutting,
):
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return None

    import bmesh

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    if only_selected:
        geom = [
            element
            for sequence in (bm.verts, bm.edges, bm.faces)
            for element in sequence
            if element.select and not element.hide
        ]
    else:
        geom = [
            element
            for sequence in (bm.verts, bm.edges, bm.faces)
            for element in sequence
            if not element.hide
        ]

    if not geom:
        return 0

    if clear_selection_after_cutting:
        for vertex in bm.verts:
            vertex.select = False
        for edge in bm.edges:
            edge.select = False
        for face in bm.faces:
            face.select = False

    local_co, local_no = _world_plane_to_local(obj, plane_co, plane_no)
    result = bmesh.ops.bisect_plane(
        bm,
        geom=geom,
        plane_co=local_co,
        plane_no=local_no,
        clear_inner=False,
        clear_outer=False,
    )

    cut_edges = [element for element in result.get("geom_cut", ()) if isinstance(element, bmesh.types.BMEdge)]
    for edge in cut_edges:
        edge.select = not clear_selection_after_cutting
        if mark_seam:
            edge.seam = True

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return len(cut_edges)


class MESH_OT_polygroups_knife_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_knife_seam"
    bl_label = "Knife Seam"
    bl_description = "Use Knife Tool and mark its selected cut edges as seams after confirming"
    bl_options = {"REGISTER", "UNDO"}

    stable_view_cut: bpy.props.BoolProperty(
        name="Stable View Cut",
        description="Use a continuous viewport-plane cut instead of Blender's screen Knife Tool",
        default=True,
    )
    use_occlude_geometry: bpy.props.BoolProperty(
        name="Occlude Geometry",
        description="Limit the cut to visible geometry only",
        default=False,
    )
    only_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Only cut currently selected geometry",
        default=False,
    )
    xray: bpy.props.BoolProperty(
        name="X-Ray",
        description="Show the cut through the mesh while drawing",
        default=True,
    )
    mark_seam: bpy.props.BoolProperty(
        name="Mark As Seam",
        description="Mark selected knife-cut edges as seams after confirming the cut",
        default=True,
    )
    clear_selection_after_cutting: bpy.props.BoolProperty(
        name="Clear Selection After Cutting",
        description="Deselect vertices, edges, and faces after post-cut processing",
        default=False,
    )

    _timer = None
    _object_name = ""
    _finished = False
    _confirmation_requested = False
    _confirmation_delay = 0
    _cancel_requested = False
    _start_region_pos = None
    _end_region_pos = None
    _using_stable_view_cut = False
    _draw_handle = None

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"
                and context.area is not None and context.area.type == "VIEW_3D"
                and context.region is not None and context.region.type == "WINDOW")

    def invoke(self, context, event):
        stop_knife_seams()
        obj = context.active_object
        self._area = context.area
        self._region = context.region
        self._workspace = context.workspace
        self._window_manager = context.window_manager
        self._window = context.window
        self._mouse_region_pos = (event.mouse_x - self._region.x, event.mouse_y - self._region.y)
        self._draw_handle = None
        self._timer = None
        self._object_name = obj.name
        self._finished = False
        self._confirmation_requested = False
        self._confirmation_delay = 0
        self._cancel_requested = False
        self._start_region_pos = None
        self._end_region_pos = None
        settings = context.scene.polygroups_knife_seam_settings

        self.stable_view_cut = settings.stable_view_cut
        self.use_occlude_geometry = settings.use_occlude_geometry
        self.only_selected = settings.only_selected
        self.xray = settings.xray
        self.mark_seam = settings.mark_seam
        self.clear_selection_after_cutting = settings.clear_selection_after_cutting

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
        self._using_stable_view_cut = self.stable_view_cut

        if self._using_stable_view_cut:
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                self._start_region_pos = self._mouse_region_pos
            try:
                self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                    _draw_knife_preview, (self,), "WINDOW", "POST_PIXEL",
                )
                self._workspace.status_text_set(self._hint())
                context.window_manager.modal_handler_add(self)
                ACTIVE_KNIFE_OPERATORS.append(self)
                self._area.tag_redraw()
            except Exception:
                self._finish(context)
                raise
            return {"RUNNING_MODAL"}

        self._native_selection = []
        for edit_obj in context.objects_in_mode_unique_data:
            if edit_obj.type != "MESH":
                continue
            bm = bmesh.from_edit_mesh(edit_obj.data)
            self._native_selection.append((edit_obj.data, bm,
                [item for seq in (bm.verts, bm.edges, bm.faces) for item in seq if item.select],
                list(bm.select_history)))
        # Native Knife clears the face mask itself in Only Selected mode.
        # Otherwise isolate the result from any pre-existing edge selection.
        if not self.only_selected:
            bpy.ops.mesh.select_all(action="DESELECT")
        try:
            result = bpy.ops.mesh.polygroups_native_knife_seam(
                "INVOKE_DEFAULT",
                MESH_OT_knife_tool={
                    "use_occlude_geometry": self.use_occlude_geometry,
                    "only_selected": self.only_selected,
                    "xray": self.xray,
                    "wait_for_input": event.type != "LEFTMOUSE",
                },
                MESH_OT_polygroups_finish_knife_seam={
                    "mark_seam": self.mark_seam,
                    "clear_selection": self.clear_selection_after_cutting,
                },
            )
        except Exception:
            self._restore_native_selection()
            self._finish(context)
            raise
        if "RUNNING_MODAL" not in result:
            self._restore_native_selection()
            self._finish(context)
            return result

        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        ACTIVE_KNIFE_OPERATORS.append(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if self._finished:
            return {"CANCELLED"}
        obj = bpy.data.objects.get(self._object_name)
        if obj is None or obj.mode != "EDIT" or context.active_object != obj:
            self._finish(context)
            return {"CANCELLED"}
        if self._using_stable_view_cut:
            try:
                return self._modal_stable_view_cut(context, event)
            except Exception as error:
                self._finish(context)
                self.report({"ERROR"}, f"Knife Seam: {error}")
                return {"CANCELLED"}

        if event.type == "ESC" and event.value == "PRESS":
            # Let Knife consume its cancel event, then remove this observer on timer.
            self._cancel_requested = True
            return {"PASS_THROUGH"}

        if event.type in {"SPACE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            # Pass the confirmation to Knife first; selection appears a moment later.
            self._confirmation_requested = True
            self._confirmation_delay = 0
            return {"PASS_THROUGH"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Wait until Knife has actually committed/cancelled before touching its
        # BMesh. Right-click is NEW_CUT in native Knife, not cancellation.
        modal_operators = getattr(self._window, "modal_operators", None)
        if modal_operators is not None and any(
            operator.bl_idname in {"MESH_OT_knife_tool", "MESH_OT_polygroups_native_knife_seam"}
            for operator in modal_operators
        ):
            return {"PASS_THROUGH"}

        if self._cancel_requested:
            self._restore_native_selection()
            self._finish(context)
            return {"CANCELLED"}

        if not self._confirmation_requested:
            return {"PASS_THROUGH"}

        if self._confirmation_delay < 2:
            self._confirmation_delay += 1
            return {"PASS_THROUGH"}

        # The macro has already marked seams and stored one combined undo step.
        # This selection/cancellation observer must not add a second undo step.
        self._native_selection = []
        self._finish(context)
        return {"CANCELLED"}

    def _restore_native_selection(self):
        for mesh, bm, selected, history in self._native_selection:
            if not mesh.is_editmode or not bm.is_valid:
                continue
            for seq in (bm.faces, bm.edges, bm.verts):
                for item in seq:
                    item.select = False
            for item in selected:
                if item.is_valid:
                    item.select_set(True)
            bm.select_flush_mode()
            bm.select_history.clear()
            for item in history:
                if item.is_valid and item.select:
                    bm.select_history.add(item)
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        self._native_selection = []

    def _hint(self):
        key = ("knife_preview_start" if self._start_region_pos is None else
               "knife_preview_end" if self._end_region_pos is None else "knife_preview_confirm")
        return t(bpy.context, key)

    def _modal_stable_view_cut(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        position = (event.mouse_x - self._region.x, event.mouse_y - self._region.y)
        inside = 0 <= position[0] < self._region.width and 0 <= position[1] < self._region.height
        if event.type == "MOUSEMOVE":
            if inside:
                self._mouse_region_pos = position
                self._area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if not inside:
                return {"RUNNING_MODAL"}
            if self._start_region_pos is None:
                self._start_region_pos = position
            else:
                self._end_region_pos = position
            self._workspace.status_text_set(self._hint())
            self._area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type in {"SPACE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            if self._end_region_pos is None:
                self.report({"WARNING"}, "Click the end point before confirming the cut")
                return {"RUNNING_MODAL"}

            with context.temp_override(area=self._area, region=self._region):
                plane_co, plane_no = _screen_plane_world(
                    context, self._start_region_pos, self._end_region_pos,
                )
            if plane_co is None:
                self.report({"WARNING"}, "Knife Seam line is too short")
                self._finish(context)
                return {"CANCELLED"}

            cut_count = _stable_view_cut(
                self._object_name,
                plane_co,
                plane_no,
                self.only_selected,
                self.mark_seam,
                self.clear_selection_after_cutting,
            )
            self._finish(context)
            if cut_count is None:
                return {"CANCELLED"}
            if cut_count == 0:
                self.report({"WARNING"}, "Knife Seam did not intersect the editable mesh")
            return {"FINISHED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self._finish(context)

    def _finish(self, context):
        if self._finished:
            return

        self._finished = True
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        if self._timer is not None:
            self._window_manager.event_timer_remove(self._timer)
            self._timer = None
        if self in ACTIVE_KNIFE_OPERATORS:
            ACTIVE_KNIFE_OPERATORS.remove(self)
        self._workspace.status_text_set(None)
        self._area.tag_redraw()
