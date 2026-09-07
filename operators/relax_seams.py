from math import acos

import bmesh
import bpy
from mathutils.bvhtree import BVHTree


def _seam_adjacency(bm, selected_area_only=False):
    adjacency = {vert: set() for vert in bm.verts}
    seam_edges = []
    for edge in bm.edges:
        if not edge.seam or (selected_area_only and not any(
                face.select and not face.hide for face in edge.link_faces)):
            continue
        seam_edges.append(edge)
        a, b = edge.verts
        adjacency[a].add(b)
        adjacency[b].add(a)
    return adjacency, seam_edges


def _smart_protected_vertices(adjacency, angle_limit, radius, use_corner_angle=True):
    protected = set()
    for vert, neighbors in adjacency.items():
        degree = len(neighbors)
        if degree != 2:
            if degree >= 3:
                protected.add(vert)
            continue
        if use_corner_angle:
            a, b = neighbors
            va = (a.co - vert.co).normalized()
            vb = (b.co - vert.co).normalized()
            angle = acos(max(-1.0, min(1.0, va.dot(vb))))
            if angle < angle_limit:
                protected.add(vert)

    frontier = set(protected)
    for _step in range(max(0, int(radius))):
        frontier = {neighbor for vert in frontier for neighbor in adjacency[vert]} - protected
        if not frontier:
            break
        protected.update(frontier)
    return protected


def relax_seams(context, mode, iterations, angle_limit, protection_radius,
                use_corner_angle=True, select_result=True,
                selected_area_only=False):
    obj = context.edit_object
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    adjacency, seam_edges = _seam_adjacency(bm, selected_area_only)
    if not seam_edges:
        return 0, 0

    protected = set()
    if mode == "SMART":
        protected = _smart_protected_vertices(
            adjacency, angle_limit, protection_radius, use_corner_angle,
        )
    movable = [vert for vert, neighbors in adjacency.items()
               if len(neighbors) == 2 and vert not in protected]

    if select_result:
        for vert in bm.verts:
            vert.select_set(False)
        for edge in bm.edges:
            edge.select_set(False)
        for face in bm.faces:
            face.select_set(False)
        selected_edges = [edge for edge in seam_edges
                          if mode != "SMART" or not any(vert in protected for vert in edge.verts)]
        for edge in selected_edges:
            edge.select_set(True)
        context.tool_settings.mesh_select_mode = (False, True, False)

    surface = BVHTree.FromBMesh(bm)
    for _iteration in range(max(1, int(iterations))):
        positions = {}
        for vert in movable:
            a, b = adjacency[vert]
            target = (a.co + b.co) * 0.5
            smoothed = vert.co.lerp(target, 0.5)
            nearest = surface.find_nearest(smoothed)
            positions[vert] = nearest[0] if nearest is not None else smoothed
        for vert, position in positions.items():
            vert.co = position

    bm.normal_update()
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
    return len(movable), len(protected)


class MESH_OT_polygroups_relax_seams(bpy.types.Operator):
    bl_idname = "mesh.polygroups_relax_seams"
    bl_label = "Relax Seams"
    bl_description = "Relax seam chains while preserving endpoints and protected junctions"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and context.edit_object is not None

    def execute(self, context):
        settings = context.scene.polygroups_seam_preparation_settings
        moved, protected = relax_seams(
            context,
            settings.seam_relax_mode,
            settings.seam_relax_iterations,
            settings.seam_relax_corner_angle,
            settings.seam_relax_protection_radius,
            settings.seam_relax_use_corner_angle,
            selected_area_only=settings.seam_relax_selected_area_only,
        )
        if not moved:
            self.report({"WARNING"}, "No relaxable seam chain vertices found")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Relaxed {moved} seam vertices; protected {protected}")
        return {"FINISHED"}
