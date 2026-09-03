"""Connect Vertex Path with seam marking; toolbar clicks are separate undo steps."""
import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..localization import t

TOOL_ID = "polygroups_generator.connect_vertex_seam_tool"


def edit_meshes(context):
    return [(obj, bmesh.from_edit_mesh(obj.data))
            for obj in context.objects_in_mode_unique_data if obj.type == "MESH"]


def selected_vertices(meshes):
    return [(obj, bm, vert) for obj, bm in meshes for vert in bm.verts
            if vert.select and not vert.hide]


def select_vertices(meshes, vertices):
    for obj, bm in meshes:
        for elements in (bm.faces, bm.edges, bm.verts):
            for element in elements:
                element.select = False
        bm.select_history.clear()
        for owner, vert in vertices:
            if owner == obj and vert.is_valid:
                vert.select_set(True)
                bm.select_history.add(vert)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def connect_pair(context, obj, bm, start, end):
    """Only the two endpoints are selected when calling Blender's J operator."""
    direct_edge = bm.edges.get((start, end))
    if direct_edge is not None:
        direct_edge.seam = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return 1
    result = bpy.ops.mesh.vert_connect_path()
    if "FINISHED" not in result:
        return 0
    # Blender selects the connecting path. Split portions of crossed edges are
    # not part of that selection and must not become additional branches/seams.
    path = [edge for edge in bm.edges if edge.select and not edge.hide]
    for edge in path:
        edge.seam = True
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return len(path)


class MESH_OT_polygroups_connect_vertex_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_connect_vertex_seam"
    bl_label = "Connect Vertices with Seam"
    bl_description = "Connect exactly two selected vertices using Connect Vertex Path and mark the connecting edges as seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "EDIT_MESH"

    def execute(self, context):
        meshes = edit_meshes(context)
        selected = selected_vertices(meshes)
        if len(selected) != 2 or selected[0][0] != selected[1][0]:
            self.report({"WARNING"}, t(context, "connect_seam_select_pair"))
            return {"CANCELLED"}
        obj, bm, start = selected[0]
        end = selected[1][2]
        try:
            count = connect_pair(context, obj, bm, start, end)
        except RuntimeError:
            count = 0
        if not count:
            self.report({"WARNING"}, t(context, "connect_seam_failed"))
            return {"CANCELLED"}
        self.report({"INFO"}, t(context, "connect_seam_done", count=count))
        return {"FINISHED"}


class MESH_OT_polygroups_connect_vertex_seam_click(bpy.types.Operator):
    bl_idname = "mesh.polygroups_connect_vertex_seam_click"
    bl_label = "Vertex Seam Path"
    bl_description = "Click a start vertex, then successive endpoints; Space/Esc/right-click finishes the chain"
    bl_options = {"UNDO"}

    reset: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and context.mode == "EDIT_MESH"
                and context.area is not None and context.area.type == "VIEW_3D"
                and context.region.type == "WINDOW")

    def invoke(self, context, event):
        meshes = edit_meshes(context)
        if self.reset:
            select_vertices(meshes, [])
            context.area.tag_redraw()
            return {"FINISHED"}

        # Native picking respects viewport occlusion and X-Ray. Save selection
        # so a click in empty space cannot discard the current starting point.
        old_mode = tuple(context.tool_settings.mesh_select_mode)
        saved = [(obj, bm, [(item, item.select) for seq in (bm.verts, bm.edges, bm.faces)
                           for item in seq], list(bm.select_history)) for obj, bm in meshes]
        old_active = context.view_layer.objects.active
        previous = selected_vertices(meshes)
        anchor = previous[0] if len(previous) == 1 else None

        def restore():
            context.tool_settings.mesh_select_mode = old_mode
            context.view_layer.objects.active = old_active
            for obj, bm, flags, history in saved:
                for item, selected in flags:
                    if item.is_valid:
                        item.select = False
                for item, selected in flags:
                    if item.is_valid and selected:
                        item.select_set(True)
                bm.select_flush_mode()
                bm.select_history.clear()
                for item in history:
                    if item.is_valid and item.select:
                        bm.select_history.add(item)
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        bpy.ops.mesh.select_mode(type="VERT")
        bpy.ops.view3d.select(
            location=(event.mouse_region_x, event.mouse_region_y),
            deselect_all=True,
        )
        picked = selected_vertices(meshes)
        if len(picked) != 1:
            restore()
            return {"CANCELLED"}
        obj, bm, end = picked[0]
        if anchor is None or anchor[0] != obj:
            select_vertices(meshes, [(obj, end)])
        elif anchor[2] == end:
            restore()
            return {"CANCELLED"}
        else:
            start = anchor[2]
            select_vertices(meshes, [(obj, start), (obj, end)])
            try:
                count = connect_pair(context, obj, bm, start, end)
            except RuntimeError:
                count = 0
            if not count:
                restore()
                self.report({"WARNING"}, t(context, "connect_seam_failed"))
                return {"CANCELLED"}
            select_vertices(meshes, [(obj, end)])
        context.area.tag_redraw()
        return {"FINISHED"}


def draw_vertex_seam_cursor(_context, _tool, xy):
    # WorkSpaceTool owns this callback; no modal handler or persistent BMesh
    # references survive undo, mode changes, tool changes, or file loading.
    context = bpy.context
    if context.mode != "EDIT_MESH" or context.region_data is None:
        return
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    from gpu_extras.presets import draw_circle_2d

    selected = selected_vertices(edit_meshes(context))
    anchor = selected[0] if len(selected) == 1 else None
    scale = context.preferences.system.ui_scale
    blend = gpu.state.blend_get()
    try:
        gpu.state.blend_set("ALPHA")
        draw_circle_2d(xy, (0.1, 0.85, 1, 1), 6 * scale)
        if anchor:
            obj, _bm, vert = anchor
            point = location_3d_to_region_2d(context.region, context.region_data, obj.matrix_world @ vert.co)
            if point is not None:
                # Cursor callbacks use window coordinates, projection uses region coordinates.
                start = (point.x + context.region.x, point.y + context.region.y)
                shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
                shader.bind()
                shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
                shader.uniform_float("lineWidth", 2 * scale)
                shader.uniform_float("color", (0.1, 0.85, 1, 0.8))
                batch_for_shader(shader, "LINES", {"pos": (start, xy)}).draw(shader)
                draw_circle_2d(start, (1, 0.65, 0.12, 1), 7 * scale)
        blf.size(0, 13 * scale)
        blf.color(0, 1, 1, 1, 1)
        blf.position(0, context.region.x + 24 * scale, context.region.y + 40 * scale, 0)
        blf.draw(0, t(context, "connect_seam_hint_next" if anchor else "connect_seam_hint_start"))
    finally:
        gpu.state.blend_set(blend)
