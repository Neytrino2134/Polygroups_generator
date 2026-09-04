"""Seam-only erasers using Blender's native viewport selection and edge routing."""
import bpy
import bmesh
from math import ceil, hypot

from ..core.edge_seam_path import find_edge_path
from ..localization import t
from .connect_vertex_seam import edit_meshes, invoke_seam_click

AREA_TOOL_ID = "polygroups_generator.seam_eraser_tool"
PATH_TOOL_ID = "polygroups_generator.edge_seam_eraser_tool"


def erase_pair(context, obj, bm, start, end):
    path = find_edge_path(bm, start, end, obj.matrix_world)
    for edge in path:
        edge.seam = False
    if path:
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return len(path)


class MESH_OT_polygroups_edge_seam_eraser_click(bpy.types.Operator):
    bl_idname = "mesh.polygroups_edge_seam_eraser_click"
    bl_label = "Erase Seam Along Edge Path"
    bl_description = "Ctrl-click successive vertices to clear seams along existing edge rows"
    bl_options = {"UNDO"}
    reset: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return (context.mode == "EDIT_MESH" and context.area is not None
                and context.area.type == "VIEW_3D" and context.region is not None
                and context.region.type == "WINDOW")

    def invoke(self, context, event):
        return invoke_seam_click(self, context, event, erase_pair, "edge_seam_failed")


def resize_circle(context, radius, event):
    step = max(1, round(radius * 0.1))
    radius = max(1, min(500, radius + (step if event.type == "WHEELUPMOUSE" else -step)))
    tool = context.workspace.tools.from_space_view3d_mode("EDIT_MESH", create=False)
    if tool is not None and tool.idname == AREA_TOOL_ID:
        tool.operator_properties("mesh.polygroups_seam_eraser").radius = radius
    context.area.tag_redraw()
    return radius


class MESH_OT_polygroups_seam_eraser_resize(bpy.types.Operator):
    bl_idname = "mesh.polygroups_seam_eraser_resize"
    bl_label = "Resize Circle Seam Eraser"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        tool = context.workspace.tools.from_space_view3d_mode("EDIT_MESH", create=False)
        if tool is None or tool.idname != AREA_TOOL_ID:
            return {"PASS_THROUGH"}
        props = tool.operator_properties("mesh.polygroups_seam_eraser")
        if props.shape != "CIRCLE":
            return {"PASS_THROUGH"}
        resize_circle(context, props.radius, event)
        return {"FINISHED"}


def draw_eraser_cursor(context, tool, xy):
    import gpu
    from gpu_extras.presets import draw_circle_2d
    props = tool.operator_properties("mesh.polygroups_seam_eraser")
    if props.shape != "CIRCLE":
        return
    blend = gpu.state.blend_get()
    try:
        gpu.state.blend_set("ALPHA")
        draw_circle_2d(xy, (1, 0.35, 0.15, 0.9), props.radius, segments=64)
    finally:
        gpu.state.blend_set(blend)


class MESH_OT_polygroups_seam_eraser(bpy.types.Operator):
    bl_idname = "mesh.polygroups_seam_eraser"
    bl_label = "Circle / Lasso Seam Eraser"
    bl_description = "Drag to clear seams using native Circle or Lasso selection; respects X-Ray"
    bl_options = {"UNDO", "BLOCKING"}

    shape: bpy.props.EnumProperty(name="Mode", items=[
        ("CIRCLE", "Circle", "Paint over seam edges"),
        ("LASSO", "Lasso", "Clear seams inside a drawn region")], default="CIRCLE")
    radius: bpy.props.IntProperty(name="Radius", default=25, min=1, max=500, subtype="PIXEL")
    _active = set()

    @classmethod
    def poll(cls, context):
        return (context.mode == "EDIT_MESH" and context.area is not None
                and context.area.type == "VIEW_3D" and context.region is not None
                and context.region.type == "WINDOW")

    def invoke(self, context, event):
        self._area = context.area
        self._region = context.region
        self._workspace = context.workspace
        self._mode = tuple(context.tool_settings.mesh_select_mode)
        self._saved = [(obj, bm, [(el, el.select) for seq in (bm.verts, bm.edges, bm.faces) for el in seq],
                        list(bm.select_history), [(e, e.seam) for e in bm.edges])
                       for obj, bm in edit_meshes(context)]
        self._points = [(event.mouse_region_x, event.mouse_region_y)]
        self._handle = None
        self._closed = False
        self._clear_selection()
        bpy.ops.mesh.select_mode(type="EDGE")
        try:
            if self.shape == "CIRCLE":
                self._circle(self._points[0])
            else:
                self._handle = bpy.types.SpaceView3D.draw_handler_add(self._draw_lasso, (), "WINDOW", "POST_PIXEL")
            self._workspace.status_text_set(t(context, "seam_erase_drag_hint"))
            self._active.add(self)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception:
            self._finish(context, cancel=True)
            raise

    def _clear_selection(self):
        for obj, bm, _flags, _history, _seams in self._saved:
            for seq in (bm.faces, bm.edges, bm.verts):
                for el in seq:
                    el.select = False
            bm.select_history.clear()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

    def _erase_selected(self):
        for obj, bm, _flags, _history, _seams in self._saved:
            for edge in bm.edges:
                if edge.select and not edge.hide:
                    edge.seam = False
        self._clear_selection()

    def _circle(self, point):
        bpy.ops.view3d.select_circle(x=int(point[0]), y=int(point[1]), radius=self.radius,
                                    wait_for_input=False, mode="SET")
        self._erase_selected()

    def _draw_lasso(self):
        if bpy.context.area != self._area or bpy.context.region != self._region or len(self._points) < 2:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", 2.0)
        shader.uniform_float("color", (1, 0.35, 0.15, 1))
        batch_for_shader(shader, "LINE_STRIP", {"pos": self._points + [self._points[0]]}).draw(shader)

    def _finish(self, context, cancel=False):
        if self._closed:
            return
        self._closed = True
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None
        self._active.discard(self)
        self._workspace.status_text_set(None)
        if context.mode == "EDIT_MESH":
            bpy.ops.mesh.select_mode(type=("VERT", "EDGE", "FACE")[self._mode.index(True)])
        context.tool_settings.mesh_select_mode = self._mode
        for obj, bm, flags, history, seams in self._saved:
            if not bm.is_valid:
                continue
            for el, selected in flags:
                if el.is_valid:
                    el.select = False
            for el, selected in flags:
                if el.is_valid and selected:
                    el.select_set(True)
            bm.select_mode = {name for name, enabled in zip(("VERT", "EDGE", "FACE"), self._mode) if enabled}
            bm.select_flush_mode()
            bm.select_history.clear()
            for el in history:
                if el.is_valid:
                    bm.select_history.add(el)
            if cancel:
                for edge, seam in seams:
                    if edge.is_valid:
                        edge.seam = seam
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        self._area.tag_redraw()

    def modal(self, context, event):
        if self._closed:
            return {"CANCELLED"}
        if event.type in {"ESC", "RIGHTMOUSE", "WINDOW_DEACTIVATE"} or context.mode != "EDIT_MESH":
            self._finish(context, cancel=True)
            return {"CANCELLED"}
        try:
            if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"} and self.shape == "CIRCLE":
                self.radius = resize_circle(context, self.radius, event)
            elif event.type == "MOUSEMOVE":
                point = (event.mouse_region_x, event.mouse_region_y)
                if self.shape == "CIRCLE":
                    previous = self._points[-1]
                    steps = max(1, ceil(hypot(point[0]-previous[0], point[1]-previous[1]) / max(1, self.radius * 0.5)))
                    for i in range(1, steps + 1):
                        self._circle(tuple(a + (b-a)*i/steps for a,b in zip(previous, point)))
                    self._points = [point]
                elif point != self._points[-1]:
                    self._points.append(point)
                self._area.tag_redraw()
            elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
                if self.shape == "LASSO" and len(self._points) >= 3:
                    bpy.ops.view3d.select_lasso(path=[{"name": "", "loc": p, "time": i}
                                                    for i,p in enumerate(self._points)], mode="SET")
                    self._erase_selected()
                self._finish(context)
                return {"FINISHED"}
        except Exception as exc:
            self._finish(context, cancel=True)
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}


def stop_erasers():
    for operator in list(MESH_OT_polygroups_seam_eraser._active):
        operator._finish(bpy.context, cancel=True)
