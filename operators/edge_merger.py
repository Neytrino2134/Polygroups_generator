"""Single-click edge merge tool for Edit Mode."""
import bmesh
import bpy
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
)

from .edge_seam_path import _HOVER_TREES, draw_colored_crosshair, draw_tool_badge, edit_meshes


TOOL_ID = "polygroups_generator.edge_merger_tool"


def _point_segment_distance_squared(point, start, end):
    segment = end - start
    length_squared = segment.length_squared
    if length_squared == 0.0:
        return (point - start).length_squared
    factor = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    return (point - (start + segment * factor)).length_squared


def hovered_edge(context, xy, radius):
    """Return an edge near the cursor on the visible mesh surface."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    region = context.region
    mouse = Vector((xy[0] - region.x, xy[1] - region.y))
    origin = region_2d_to_origin_3d(region, context.region_data, mouse)
    direction = region_2d_to_vector_3d(region, context.region_data, mouse)
    nearest = None
    for obj, bm in edit_meshes(context):
        key = (obj.as_pointer(), obj.data.as_pointer())
        signature = (len(bm.verts), len(bm.edges), len(bm.faces))
        cached = _HOVER_TREES.get(key)
        if cached is None or cached[0] != signature:
            cached = (signature, BVHTree.FromBMesh(bm))
            _HOVER_TREES[key] = cached
        tree = cached[1]
        inverse = obj.matrix_world.inverted_safe()
        location, _normal, face_index, _distance = tree.ray_cast(
            inverse @ origin,
            (inverse.to_3x3() @ direction).normalized(),
        )
        if location is not None:
            world_distance = (obj.matrix_world @ location - origin).length_squared
            if nearest is None or world_distance < nearest[0]:
                nearest = (world_distance, obj, bm, face_index)
    if nearest is None:
        return None
    _distance, obj, bm, face_index = nearest
    bm.faces.ensure_lookup_table()
    if not 0 <= face_index < len(bm.faces):
        return None
    best = None
    best_distance = radius * radius
    for edge in bm.faces[face_index].edges:
        points = [
            location_3d_to_region_2d(region, context.region_data, obj.matrix_world @ vert.co)
            for vert in edge.verts
        ]
        if any(point is None for point in points):
            continue
        distance = _point_segment_distance_squared(mouse, points[0], points[1])
        if distance <= best_distance:
            best, best_distance = edge, distance
    return best


def draw_edge_merger_cursor(_context, _tool, xy):
    context = bpy.context
    if context.mode != "EDIT_MESH" or context.region_data is None:
        return
    edge = hovered_edge(context, xy, 10 * context.preferences.system.ui_scale)
    color = (1.0, 0.12, 0.08, 1.0) if edge is not None else (1.0, 0.55, 0.08, 1.0)
    draw_colored_crosshair(context, xy, color)
    draw_tool_badge(context, "Edge Merger", xy, "Click: Merge edge at center")


class MESH_OT_polygroups_edge_merger_click(bpy.types.Operator):
    bl_idname = "mesh.polygroups_edge_merger_click"
    bl_label = "Merge Edge at Center"
    bl_description = "Pick one edge and immediately merge its vertices at the center"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def invoke(self, context, event):
        obj = context.active_object
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.view3d.select(
            location=(event.mouse_region_x, event.mouse_region_y),
            deselect_all=True,
        )
        bm = bmesh.from_edit_mesh(obj.data)
        selected = [edge for edge in bm.edges if edge.select and not edge.hide]
        if len(selected) != 1:
            return {"CANCELLED"}
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
        bm = bmesh.from_edit_mesh(obj.data)
        selected = [edge for edge in bm.edges if edge.select and not edge.hide]
        if len(selected) != 1:
            self.report({"WARNING"}, "Select exactly one edge")
            return {"CANCELLED"}
        edge = selected[0]
        for vert in bm.verts:
            vert.select_set(vert in edge.verts)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        result = bpy.ops.mesh.merge(type="CENTER", uvs=True)
        if "FINISHED" not in result:
            return result
        return {"FINISHED"}
