import heapq
import itertools

import bmesh
import bpy
from mathutils import Vector

from .unwrap_angle_based import unwrap_selected_angle_based


def _selected_faces(bm):
    return {face for face in bm.faces if face.select}


def _selection_boundary_edges(bm, selected_faces):
    boundary_edges = set()
    for edge in bm.edges:
        linked_faces = set(edge.link_faces)
        selected_linked = linked_faces & selected_faces
        if not selected_linked:
            continue
        if linked_faces - selected_faces or len(linked_faces) == 1:
            boundary_edges.add(edge)
    return boundary_edges


def _edge_components(edges):
    edge_set = set(edges)
    vertex_edges = {}
    for edge in edge_set:
        for vert in edge.verts:
            vertex_edges.setdefault(vert, set()).add(edge)

    components = []
    while edge_set:
        start_edge = edge_set.pop()
        stack = [start_edge]
        component_edges = {start_edge}
        component_verts = set(start_edge.verts)

        while stack:
            edge = stack.pop()
            for vert in edge.verts:
                component_verts.add(vert)
                for linked_edge in vertex_edges.get(vert, ()):
                    if linked_edge not in edge_set:
                        continue
                    edge_set.remove(linked_edge)
                    component_edges.add(linked_edge)
                    stack.append(linked_edge)

        components.append((component_edges, component_verts))

    return components


def _path_graph(selected_faces, boundary_edges):
    graph = {}
    edge_lookup = {}

    for face in selected_faces:
        for edge in face.edges:
            if edge in boundary_edges:
                continue

            vert_a, vert_b = edge.verts
            weight = (vert_a.co - vert_b.co).length
            graph.setdefault(vert_a, []).append((vert_b, weight, edge))
            graph.setdefault(vert_b, []).append((vert_a, weight, edge))
            edge_lookup[frozenset((vert_a, vert_b))] = edge

    return graph, edge_lookup


def _dijkstra(graph, sources, targets=None):
    distances = {}
    previous = {}
    target_set = set(targets or ())
    queue = []
    counter = itertools.count()

    for source in sources:
        if source not in graph:
            continue
        distances[source] = 0.0
        heapq.heappush(queue, (0.0, next(counter), source))

    found_target = None
    while queue:
        distance, _, vert = heapq.heappop(queue)
        if distance != distances.get(vert):
            continue

        if target_set and vert in target_set:
            found_target = vert
            break

        for neighbor, weight, edge in graph.get(vert, ()):
            new_distance = distance + weight
            if new_distance >= distances.get(neighbor, float("inf")):
                continue
            distances[neighbor] = new_distance
            previous[neighbor] = (vert, edge)
            heapq.heappush(queue, (new_distance, next(counter), neighbor))

    return distances, previous, found_target


def _edges_from_previous(previous, target):
    edges = []
    current = target
    while current in previous:
        previous_vert, edge = previous[current]
        edges.append(edge)
        current = previous_vert
    edges.reverse()
    return edges


def _nearest_graph_vertex(graph, position):
    nearest_vert = None
    nearest_distance = float("inf")
    for vert in graph:
        distance = (vert.co - position).length
        if distance < nearest_distance:
            nearest_vert = vert
            nearest_distance = distance
    return nearest_vert


def _active_selection_position(bm):
    active = bm.select_history.active
    if isinstance(active, bmesh.types.BMVert):
        return active.co.copy()
    if isinstance(active, bmesh.types.BMEdge):
        return sum((vert.co for vert in active.verts), Vector()) / 2.0
    if isinstance(active, bmesh.types.BMFace):
        return active.calc_center_median()

    selected_edges = [edge for edge in bm.edges if edge.select]
    if selected_edges:
        edge = selected_edges[0]
        return sum((vert.co for vert in edge.verts), Vector()) / 2.0

    selected_verts = [vert for vert in bm.verts if vert.select]
    if selected_verts:
        return selected_verts[0].co.copy()

    return None


def _guided_path_edges(graph, loop_a, loop_b, guide_position):
    guide_vert = _nearest_graph_vertex(graph, guide_position)
    if guide_vert is None:
        return []

    distances, previous, _ = _dijkstra(graph, [guide_vert])
    loop_a_verts = [vert for vert in loop_a if vert in distances]
    loop_b_verts = [vert for vert in loop_b if vert in distances]
    if not loop_a_verts or not loop_b_verts:
        return []

    target_a = min(loop_a_verts, key=lambda vert: distances[vert])
    target_b = min(loop_b_verts, key=lambda vert: distances[vert])
    return _edges_from_previous(previous, target_a) + _edges_from_previous(previous, target_b)


def _shortest_boundary_path_edges(graph, loop_a, loop_b):
    sources = [vert for vert in loop_a if vert in graph]
    targets = [vert for vert in loop_b if vert in graph]
    if not sources or not targets:
        return []

    _, previous, target = _dijkstra(graph, sources, targets)
    if target is None:
        return []
    return _edges_from_previous(previous, target)


def _mark_boundary_edges(boundary_edges):
    marked_count = 0
    for edge in boundary_edges:
        if not edge.seam:
            marked_count += 1
        edge.seam = True
    return marked_count


def _mark_longitudinal_seam_edges(bm):
    selected_faces = _selected_faces(bm)
    if not selected_faces:
        return None, "Select cylinder side faces first"

    boundary_edges = _selection_boundary_edges(bm, selected_faces)
    components = _edge_components(boundary_edges)
    if len(components) < 2:
        return None, "Selection needs at least two boundary loops"

    components.sort(key=lambda item: len(item[0]), reverse=True)
    loop_a = components[0][1]
    loop_b = components[1][1]

    graph, _edge_lookup = _path_graph(selected_faces, boundary_edges)
    if not graph:
        return None, "No side-surface edge path found"

    guide_position = _active_selection_position(bm)
    seam_edges = []
    if guide_position is not None:
        seam_edges = _guided_path_edges(graph, loop_a, loop_b, guide_position)

    if not seam_edges:
        seam_edges = _shortest_boundary_path_edges(graph, loop_a, loop_b)

    if not seam_edges:
        return None, "Could not find a path between boundary loops"

    marked_count = 0
    for edge in set(seam_edges):
        if not edge.seam:
            marked_count += 1
        edge.seam = True
        edge.select = True

    return (marked_count, boundary_edges), None


class MESH_OT_polygroups_mark_longitudinal_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_longitudinal_seam"
    bl_label = "Create Longitudinal Seam"
    bl_description = "Create one lengthwise seam between two boundary loops of the selected side faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()

        result, warning = _mark_longitudinal_seam_edges(bm)
        if warning:
            self.report({"WARNING"}, warning)
            return {"CANCELLED"}

        bmesh.update_edit_mesh(mesh)
        auto_unwrapped = False
        if context.scene.polygroups_seam_finalization_settings.auto_unwrap_after_seam:
            auto_unwrapped = unwrap_selected_angle_based(context)

        suffix = " and unwrapped selected faces" if auto_unwrapped else ""
        self.report({"INFO"}, f"Marked {result[0]} longitudinal seam edge(s){suffix}")
        return {"FINISHED"}


class MESH_OT_polygroups_mark_boundary_and_longitudinal_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_boundary_and_longitudinal_seam"
    bl_label = "Boundary + Longitudinal Seam"
    bl_description = "Mark selected face boundary seams, then create one lengthwise seam"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()

        result, warning = _mark_longitudinal_seam_edges(bm)
        if warning:
            self.report({"WARNING"}, warning)
            return {"CANCELLED"}

        longitudinal_count, boundary_edges = result
        boundary_count = _mark_boundary_edges(boundary_edges)

        bmesh.update_edit_mesh(mesh)
        auto_unwrapped = False
        if context.scene.polygroups_seam_finalization_settings.auto_unwrap_after_seam:
            auto_unwrapped = unwrap_selected_angle_based(context)

        suffix = " and unwrapped selected faces" if auto_unwrapped else ""
        self.report(
            {"INFO"},
            f"Marked {boundary_count} boundary seam edge(s) and {longitudinal_count} longitudinal seam edge(s){suffix}",
        )
        return {"FINISHED"}
