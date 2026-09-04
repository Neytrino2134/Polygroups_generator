"""Seam paths along existing edges; never split faces or create geometry."""
import bmesh
import bpy

from ..core.edge_seam_path import find_edge_path
from ..localization import t
from .connect_vertex_seam import edit_meshes, selected_vertices, invoke_seam_click

TOOL_ID = "polygroups_generator.edge_seam_path_tool"


_HOVER_TREES = {}


def clear_hover_cache(*_args):
    _HOVER_TREES.clear()


def invalidate_hover_geometry(_scene, depsgraph):
    if any(update.is_updated_geometry for update in depsgraph.updates):
        clear_hover_cache()


def register_hover_cache():
    from bpy.app.handlers import persistent
    for handlers, callback in (
        (bpy.app.handlers.depsgraph_update_post, invalidate_hover_geometry),
        (bpy.app.handlers.undo_post, clear_hover_cache),
        (bpy.app.handlers.redo_post, clear_hover_cache),
        (bpy.app.handlers.load_post, clear_hover_cache),
    ):
        if callback not in handlers:
            handlers.append(persistent(callback))


def unregister_hover_cache():
    for handlers, callback in (
        (bpy.app.handlers.depsgraph_update_post, invalidate_hover_geometry),
        (bpy.app.handlers.undo_post, clear_hover_cache),
        (bpy.app.handlers.redo_post, clear_hover_cache),
        (bpy.app.handlers.load_post, clear_hover_cache),
    ):
        if callback in handlers:
            handlers.remove(callback)
    clear_hover_cache()


def hovered_vertex(context, xy, radius):
    """Approximate hover using cached BVHs and a fixed number of local ray queries.

    Never iterate an edit mesh here: this runs on every cursor redraw. Hover is
    visual feedback only; clicks still use Blender's native vertex selection.
    """
    from bpy_extras.view3d_utils import (
        region_2d_to_origin_3d, region_2d_to_vector_3d, location_3d_to_region_2d,
    )
    from mathutils import Vector

    region, view = context.region, context.region_data
    mouse = Vector((xy[0] - region.x, xy[1] - region.y))
    from mathutils.bvhtree import BVHTree
    surfaces = []
    active_keys = set()
    for obj, mesh in edit_meshes(context):
        key = (obj.as_pointer(), obj.data.as_pointer())
        active_keys.add(key)
        signature = (len(mesh.verts), len(mesh.edges), len(mesh.faces))
        cached = _HOVER_TREES.get(key)
        if cached is None or cached[0] != signature:
            mesh.faces.ensure_lookup_table()
            cached = (signature, BVHTree.FromBMesh(mesh))
            _HOVER_TREES[key] = cached
        surfaces.append((obj, mesh, cached[1], obj.matrix_world.copy(), obj.matrix_world.inverted_safe()))
    for key in list(_HOVER_TREES):
        if key not in active_keys:
            del _HOVER_TREES[key]
    seen_faces = set()
    best, best_distance = None, radius * radius
    # Offset rays also catch a vertex when the cursor is just outside a silhouette.
    for dx, dy in ((0, 0), (-radius, 0), (radius, 0), (0, -radius), (0, radius)):
        point = mouse + Vector((dx, dy))
        origin = region_2d_to_origin_3d(region, view, point)
        direction = region_2d_to_vector_3d(region, view, point)
        nearest = None
        for obj, mesh, tree, matrix, inverse in surfaces:
            local_direction = (inverse.to_3x3() @ direction).normalized()
            location, _, face_index, _ = tree.ray_cast(inverse @ origin, local_direction)
            if location is None:
                continue
            distance = (matrix @ location - origin).length_squared
            if nearest is None or distance < nearest[0]:
                nearest = (distance, obj, mesh, matrix, face_index)
        if nearest is None:
            continue
        _, obj, mesh, matrix, face_index = nearest
        key = (obj.as_pointer(), face_index)
        if key in seen_faces:
            continue
        seen_faces.add(key)
        mesh.faces.ensure_lookup_table()
        if not 0 <= face_index < len(mesh.faces):
            continue
        face = mesh.faces[face_index]
        if face.hide:
            continue
        # A giant n-gon must not reintroduce a full-mesh scan during drawing.
        if len(face.verts) > 64:
            continue
        for vert in face.verts:
            if vert.hide:
                continue
            projected = location_3d_to_region_2d(region, view, matrix @ vert.co)
            if projected is None:
                continue
            distance = (projected - mouse).length_squared
            if distance <= best_distance:
                best_distance = distance
                best = (obj.original, vert)
    return best


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
