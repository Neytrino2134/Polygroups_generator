"""Seam paths along existing edges; never split faces or create geometry."""
import bmesh
import bpy

from ..core.edge_seam_path import find_edge_path
from ..localization import t
from .connect_vertex_seam import edit_meshes, selected_vertices, invoke_seam_click

TOOL_ID = "polygroups_generator.edge_seam_path_tool"


def hovered_vertex(context, xy, radius):
    """Read-only screen proximity, with occlusion unless X-Ray is enabled."""
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d

    region, view = context.region, context.region_data
    mouse_x, mouse_y = xy[0] - region.x, xy[1] - region.y
    candidates = []
    for obj, bm in edit_meshes(context):
        projection = view.perspective_matrix @ obj.matrix_world
        for vert in bm.verts:
            if vert.hide:
                continue
            clip = projection @ vert.co.to_4d()
            if clip.w <= 0 or abs(clip.z) > clip.w:
                continue
            px = (clip.x / clip.w + 1) * region.width * 0.5
            py = (clip.y / clip.w + 1) * region.height * 0.5
            distance = (px - mouse_x) ** 2 + (py - mouse_y) ** 2
            if distance <= radius * radius:
                candidates.append((distance, obj, vert, (px, py)))
    shading = context.space_data.shading
    xray = (shading.show_xray_wireframe if shading.type == "WIREFRAME"
            else shading.show_xray if shading.type == "SOLID" else False)
    depsgraph = None
    for _, obj, vert, point in sorted(candidates, key=lambda item: item[0]):
        if not xray:
            if depsgraph is None:
                depsgraph = context.evaluated_depsgraph_get()
            world = obj.matrix_world @ vert.co
            origin = region_2d_to_origin_3d(region, view, point)
            direction = region_2d_to_vector_3d(region, view, point)
            tolerance = max(obj.dimensions.length * 1e-5, 1e-6)
            distance = (world - origin).dot(direction) - tolerance
            if distance > 0 and context.scene.ray_cast(
                    depsgraph, origin, direction, distance=distance)[0]:
                continue
        return obj, vert
    return None


def draw_edge_seam_cursor(_context, _tool, xy):
    """Only a crosshair; turn amber near a vertex without changing selection."""
    import gpu
    from gpu_extras.batch import batch_for_shader

    context = bpy.context
    if context.mode != "EDIT_MESH" or context.region_data is None:
        return
    scale = context.preferences.system.ui_scale
    hovered = hovered_vertex(context, xy, 12 * scale)
    size = (8 if hovered else 6) * scale
    x, y = xy
    points = ((x - size, y), (x + size, y), (x, y - size), (x, y + size))
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": points})
    blend = gpu.state.blend_get()
    try:
        gpu.state.blend_set("ALPHA")
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        # A dark outline keeps the cross visible on light and dark surfaces.
        shader.uniform_float("lineWidth", 4 * scale)
        shader.uniform_float("color", (0.02, 0.02, 0.02, 0.9))
        batch.draw(shader)
        shader.uniform_float("lineWidth", 2 * scale)
        shader.uniform_float("color", (1.0, 0.65, 0.12, 1.0) if hovered else (0.85, 0.95, 1.0, 1.0))
        batch.draw(shader)
    finally:
        gpu.state.blend_set(blend)


def mark_pair(context, obj, bm, start, end):
    path = find_edge_path(bm, start, end, obj.matrix_world)
    if not path:
        return 0
    # Explicit edge selection avoids selecting off-path chords/faces when all
    # their vertices happen to be on the route. The click helper then keeps only
    # the last vertex selected as the anchor of the next segment.
    bpy.ops.mesh.select_mode(type="EDGE")
    for owner, mesh in edit_meshes(context):
        for elements in (mesh.faces, mesh.edges, mesh.verts):
            for item in elements:
                item.select = False
        mesh.select_history.clear()
        if owner == obj:
            for edge in path:
                edge.seam = True
                edge.select_set(True)
            mesh.select_history.add(path[-1])
        bmesh.update_edit_mesh(owner.data, loop_triangles=False, destructive=False)
    return len(path)


class MESH_OT_polygroups_edge_seam_path(bpy.types.Operator):
    bl_idname = "mesh.polygroups_edge_seam_path"
    bl_label = "Edge Seam Path"
    bl_description = "Select and mark a seam between two selected vertices along existing edges, favoring straight rows and few turns"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "EDIT_MESH"

    def execute(self, context):
        selected = selected_vertices(edit_meshes(context))
        if len(selected) != 2 or selected[0][0] != selected[1][0]:
            self.report({"WARNING"}, t(context, "connect_seam_select_pair"))
            return {"CANCELLED"}
        obj, bm, start = selected[0]
        count = mark_pair(context, obj, bm, start, selected[1][2])
        if not count:
            self.report({"WARNING"}, t(context, "edge_seam_failed"))
            return {"CANCELLED"}
        self.report({"INFO"}, t(context, "connect_seam_done", count=count))
        return {"FINISHED"}


def mark_click_pair(context, obj, bm, start, end):
    # Interactive chaining stays in vertex mode. Avoid changing selection until
    # routing succeeds; the shared click handler restores it on failure.
    path = find_edge_path(bm, start, end, obj.matrix_world)
    for edge in path:
        edge.seam = True
    if path:
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return len(path)


class MESH_OT_polygroups_edge_seam_path_click(bpy.types.Operator):
    bl_idname = "mesh.polygroups_edge_seam_path_click"
    bl_label = "Edge Seam Path Tool"
    bl_description = "Click vertices to mark existing edges as seams with few turns; Space/Esc/right-click finishes the chain"
    bl_options = {"UNDO"}

    reset: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and context.mode == "EDIT_MESH"
                and context.area is not None and context.area.type == "VIEW_3D"
                and context.region is not None and context.region.type == "WINDOW")

    def invoke(self, context, event):
        return invoke_seam_click(self, context, event, mark_click_pair, "edge_seam_failed")
