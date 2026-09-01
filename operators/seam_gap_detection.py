from collections import deque

import bmesh
import bpy


def _seam_degree(vertex):
    return sum(1 for edge in vertex.link_edges if edge.seam)


def _seam_endpoints(bm):
    return [
        vertex
        for vertex in bm.verts
        if vertex.is_valid and _seam_degree(vertex) == 1
    ]


def _find_gap_paths(bm, max_edges, max_distance):
    endpoints = _seam_endpoints(bm)
    endpoint_set = set(endpoints)
    if len(endpoints) < 2:
        return []

    max_edges = max(1, int(max_edges))
    max_distance = max(0.0, float(max_distance))
    paths = []
    seen_pairs = set()

    for start in endpoints:
        queue = deque([(start, [], 0.0)])
        visited = {start}

        while queue:
            vertex, path_edges, path_distance = queue.popleft()
            if len(path_edges) >= max_edges:
                continue

            for edge in vertex.link_edges:
                if edge.seam:
                    continue

                next_vertex = edge.other_vert(vertex)
                next_distance = path_distance + edge.calc_length()
                if max_distance > 0.0 and next_distance > max_distance:
                    continue

                next_path = path_edges + [edge]
                if next_vertex in endpoint_set and next_vertex != start:
                    pair_key = tuple(sorted((start.index, next_vertex.index)))
                    if pair_key in seen_pairs:
                        continue

                    seen_pairs.add(pair_key)
                    paths.append(
                        {
                            "edges": next_path,
                            "distance": next_distance,
                            "endpoints": (start, next_vertex),
                        },
                    )
                    continue

                if next_vertex in visited:
                    continue

                visited.add(next_vertex)
                queue.append((next_vertex, next_path, next_distance))

    paths.sort(key=lambda item: (len(item["edges"]), item["distance"]))
    return paths


def _nearest_endpoint_pairs(bm, max_distance):
    endpoints = _seam_endpoints(bm)
    max_distance = max(0.0, float(max_distance))
    candidates = []

    for index, start in enumerate(endpoints):
        for end in endpoints[index + 1:]:
            distance = (start.co - end.co).length
            if max_distance > 0.0 and distance > max_distance:
                continue
            candidates.append((distance, start, end))

    candidates.sort(key=lambda item: item[0])
    used = set()
    pairs = []
    for distance, start, end in candidates:
        if start in used or end in used:
            continue

        used.add(start)
        used.add(end)
        pairs.append(
            {
                "vertices": (start, end),
                "distance": distance,
            },
        )

    return pairs


def _edge_from_connect_result(result):
    for key in ("edges", "geom"):
        for element in result.get(key, []):
            if isinstance(element, bmesh.types.BMEdge) and element.is_valid:
                return element

    return None


def _connect_seam_gap_pair(bm, start, end):
    edge = bm.edges.get((start, end))
    if edge is not None:
        return edge, False

    try:
        result = bmesh.ops.connect_vert_pair(bm, verts=[start, end])
    except Exception:
        result = {}

    edge = _edge_from_connect_result(result)
    if edge is not None:
        return edge, True

    try:
        return bm.edges.new((start, end)), True
    except ValueError:
        edge = bm.edges.get((start, end))
        return edge, False


class MESH_OT_polygroups_check_seam_gaps(bpy.types.Operator):
    bl_idname = "mesh.polygroups_check_seam_gaps"
    bl_label = "Check Seam Gaps"
    bl_description = "Find short unmarked paths between seam endpoints"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("SELECT", "Select", "Select likely seam gap edges"),
            ("MARK", "Mark", "Mark likely seam gap edges as seams"),
        ),
        default="SELECT",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.polygroups_seam_preparation_settings
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        paths = _find_gap_paths(
            bm,
            settings.seam_gap_max_edges,
            settings.seam_gap_max_distance,
        )
        for edge in bm.edges:
            edge.select_set(False)

        selected_edges = set()
        marked_count = 0
        for path in paths:
            for edge in path["edges"]:
                if not edge.is_valid:
                    continue

                selected_edges.add(edge)
                edge.select_set(True)
                if self.mode == "MARK" and not edge.seam:
                    edge.seam = True
                    marked_count += 1

        bpy.context.tool_settings.mesh_select_mode = (False, True, False)
        bmesh.update_edit_mesh(mesh)

        gap_count = len(paths)
        edge_count = len(selected_edges)
        if self.mode == "MARK":
            status = f"Closed {gap_count} seam gap(s), marked {marked_count} edge(s)"
        else:
            status = f"Found {gap_count} seam gap(s), selected {edge_count} edge(s)"

        settings.seam_gap_status = status
        if gap_count:
            self.report({"INFO"}, status)
            return {"FINISHED"}

        self.report({"INFO"}, "No seam gaps found")
        return {"FINISHED"}


class MESH_OT_polygroups_connect_seam_gap_pairs(bpy.types.Operator):
    bl_idname = "mesh.polygroups_connect_seam_gap_pairs"
    bl_label = "Connect Seam Gap Pairs"
    bl_description = "Connect nearest open seam endpoints and mark the created edges as seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.polygroups_seam_preparation_settings
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        pairs = _nearest_endpoint_pairs(bm, settings.seam_gap_max_distance)
        for edge in bm.edges:
            edge.select_set(False)

        connected_count = 0
        marked_count = 0
        selected_edges = set()
        for pair in pairs:
            start, end = pair["vertices"]
            if start == end:
                continue

            edge, was_created = _connect_seam_gap_pair(bm, start, end)
            if edge is None:
                continue

            if was_created:
                connected_count += 1
            if not edge.seam:
                edge.seam = True
                marked_count += 1
            edge.select_set(True)
            selected_edges.add(edge)

        bpy.context.tool_settings.mesh_select_mode = (False, True, False)
        bm.normal_update()
        bmesh.update_edit_mesh(mesh)

        status = (
            f"Connected {connected_count} seam gap pair(s), "
            f"marked {marked_count} edge(s)"
        )
        settings.seam_gap_status = status
        if selected_edges:
            self.report({"INFO"}, status)
            return {"FINISHED"}

        status = "No seam endpoint pairs found"
        settings.seam_gap_status = status
        self.report({"INFO"}, status)
        return {"FINISHED"}
