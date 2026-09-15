"""Find and remove small disconnected mesh components from the active object."""

from collections import deque

import bpy
import bmesh
from mathutils import Vector


SCORE_EPSILON = 1.0e-18


def _bounding_box_score(coordinates):
    """Return a volume-like size that also works for flat and linear parts."""
    if not coordinates:
        return 0.0
    minimum = [min(co[axis] for co in coordinates) for axis in range(3)]
    maximum = [max(co[axis] for co in coordinates) for axis in range(3)]
    extents = sorted((maximum[axis] - minimum[axis] for axis in range(3)), reverse=True)
    largest = extents[0]
    if largest <= SCORE_EPSILON:
        return 0.0
    significant = [extent for extent in extents if extent > largest * 1.0e-6]
    if len(significant) == 1:
        return significant[0] ** 3
    if len(significant) == 2:
        return (significant[0] * significant[1]) ** 1.5
    return significant[0] * significant[1] * significant[2]


def _closed_component_volume(
    vertex_indices,
    coordinate_by_index,
    edge_indices,
    triangles,
    edge_face_counts,
):
    """Return a reliable enclosed volume, or None for an open/invalid shell."""
    if not edge_indices or any(edge_face_counts[index] != 2 for index in edge_indices):
        return None

    center = sum((coordinate_by_index[index] for index in vertex_indices), Vector()) / len(vertex_indices)
    signed_volume = 0.0
    absolute_volume = 0.0
    for triangle in triangles:
        world = [coordinate_by_index[index] - center for index in triangle]
        tetrahedron = world[0].dot(world[1].cross(world[2])) / 6.0
        signed_volume += tetrahedron
        absolute_volume += abs(tetrahedron)

    volume = abs(signed_volume)
    # Badly inconsistent normals can cancel an otherwise closed component.
    if absolute_volume > SCORE_EPSILON and volume < absolute_volume * 0.25:
        return None
    return volume if volume > SCORE_EPSILON else None


def analyze_loose_parts(obj, metric="BOUNDING_BOX"):
    """Return connected components and relative size scores for one mesh object."""
    mesh = obj.data
    vertex_count = len(mesh.vertices)
    if vertex_count == 0:
        return []

    adjacency = [set() for _index in range(vertex_count)]
    for edge in mesh.edges:
        first, second = edge.vertices
        adjacency[first].add(second)
        adjacency[second].add(first)

    components = []
    unvisited = set(range(vertex_count))
    while unvisited:
        start = min(unvisited)
        unvisited.remove(start)
        queue = deque([start])
        vertices = []
        while queue:
            vertex = queue.popleft()
            vertices.append(vertex)
            neighbors = adjacency[vertex] & unvisited
            unvisited.difference_update(neighbors)
            queue.extend(neighbors)
        components.append(sorted(vertices))

    component_by_vertex = {}
    for component_index, vertices in enumerate(components):
        for vertex_index in vertices:
            component_by_vertex[vertex_index] = component_index

    face_counts = [0] * len(components)
    for polygon in mesh.polygons:
        if polygon.vertices:
            face_counts[component_by_vertex[polygon.vertices[0]]] += 1

    component_edges = [[] for _component in components]
    for edge in mesh.edges:
        component_edges[component_by_vertex[edge.vertices[0]]].append(edge.index)

    edge_face_counts = None
    component_triangles = None
    if metric == "VOLUME":
        edge_face_counts = [0] * len(mesh.edges)
        edge_lookup = {tuple(sorted(edge.vertices)): edge.index for edge in mesh.edges}
        for polygon in mesh.polygons:
            for edge_key in polygon.edge_keys:
                edge_index = edge_lookup.get(tuple(sorted(edge_key)))
                if edge_index is not None:
                    edge_face_counts[edge_index] += 1
        mesh.calc_loop_triangles()
        component_triangles = [[] for _component in components]
        for triangle in mesh.loop_triangles:
            component_index = component_by_vertex[triangle.vertices[0]]
            component_triangles[component_index].append(tuple(triangle.vertices))

    matrix = obj.matrix_world
    results = []
    for component_index, vertices in enumerate(components):
        coordinate_by_index = {
            index: matrix @ mesh.vertices[index].co
            for index in vertices
        }
        coordinates = list(coordinate_by_index.values())
        bounds_score = _bounding_box_score(coordinates)
        score = bounds_score
        used_metric = "BOUNDING_BOX"
        if metric == "VOLUME" and face_counts[component_index]:
            volume = _closed_component_volume(
                vertices,
                coordinate_by_index,
                component_edges[component_index],
                component_triangles[component_index],
                edge_face_counts,
            )
            if volume is not None:
                score = volume
                used_metric = "VOLUME"
        results.append({
            "vertices": vertices,
            "vertex_count": len(vertices),
            "edge_count": len(component_edges[component_index]),
            "face_count": face_counts[component_index],
            "score": score,
            "metric": used_metric,
        })
    return results


def small_part_candidates(parts, threshold_percent):
    """Return all parts below the requested percentage of the largest part."""
    if len(parts) < 2:
        return []
    largest_index = max(range(len(parts)), key=lambda index: parts[index]["score"])
    largest_score = parts[largest_index]["score"]
    candidates = []
    for index, part in enumerate(parts):
        if index == largest_index:
            continue
        ratio = 0.0 if largest_score <= SCORE_EPSILON else 100.0 * part["score"] / largest_score
        part["ratio_percent"] = ratio
        if ratio < threshold_percent:
            candidates.append(part)
    return candidates


def remove_small_loose_parts(obj, metric="BOUNDING_BOX", threshold_percent=8.0):
    """Delete qualifying parts in Object Mode and return removal statistics."""
    parts = analyze_loose_parts(obj, metric)
    candidates = small_part_candidates(parts, threshold_percent)
    if not candidates:
        return {
            "part_count": 0,
            "vertex_count": 0,
            "edge_count": 0,
            "face_count": 0,
            "total_parts": len(parts),
        }

    vertex_indices = sorted({
        index
        for part in candidates
        for index in part["vertices"]
    })
    result = {
        "part_count": len(candidates),
        "vertex_count": len(vertex_indices),
        "edge_count": sum(part["edge_count"] for part in candidates),
        "face_count": sum(part["face_count"] for part in candidates),
        "total_parts": len(parts),
    }
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        delete_vertices = [bm.verts[index] for index in vertex_indices]
        bmesh.ops.delete(bm, geom=delete_vertices, context="VERTS")
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    return result


def _select_candidate_vertices(context, obj, vertex_indices):
    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    for face in bm.faces:
        face.select = False
    for edge in bm.edges:
        edge.select = False
    for vertex in bm.verts:
        vertex.select = False
    for index in vertex_indices:
        bm.verts[index].select = True
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    context.tool_settings.mesh_select_mode = (True, False, False)


class OBJECT_OT_polygroups_small_loose_parts(bpy.types.Operator):
    bl_idname = "object.polygroups_small_loose_parts"
    bl_label = "Small Loose Parts"
    bl_description = "Select or delete disconnected mesh parts smaller than the configured relative size"
    bl_options = {"REGISTER", "UNDO"}

    delete: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.polygroups_model_preparation_settings
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        parts = analyze_loose_parts(obj, settings.small_loose_part_metric)
        if len(parts) < 2:
            self.report({"INFO"}, "The active mesh has only one connected part")
            return {"CANCELLED"}
        candidates = small_part_candidates(parts, settings.small_loose_part_threshold_percent)
        if not candidates:
            self.report({"INFO"}, "No loose parts are below the configured size threshold")
            return {"CANCELLED"}

        vertex_indices = sorted({
            index
            for part in candidates
            for index in part["vertices"]
        })
        removed_faces = sum(part["face_count"] for part in candidates)
        _select_candidate_vertices(context, obj, vertex_indices)
        if not self.delete:
            self.report(
                {"INFO"},
                f"Selected {len(candidates)} of {len(parts)} loose parts ({len(vertex_indices)} vertices)",
            )
            return {"FINISHED"}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        delete_vertices = [bm.verts[index] for index in vertex_indices]
        bmesh.ops.delete(bm, geom=delete_vertices, context="VERTS")
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        bpy.ops.object.mode_set(mode="OBJECT")
        obj.data.update()
        self.report(
            {"INFO"},
            f"Deleted {len(candidates)} small loose parts: {len(vertex_indices)} vertices, {removed_faces} faces",
        )
        return {"FINISHED"}
