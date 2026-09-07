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


def _find_gap_paths(bm, max_edges, max_distance, include_junctions=False):
    bm.verts.index_update()
    endpoints = _seam_endpoints(bm)
    endpoint_set = set(endpoints)
    targets = {v for v in bm.verts if _seam_degree(v) > 0} if include_junctions else endpoint_set
    if not endpoints:
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
                if next_vertex in targets and next_vertex != start:
                    if next_vertex not in endpoint_set:
                        # A junction must lie ahead of the open seam, not back along it.
                        seam = next(e for e in start.link_edges if e.seam)
                        forward = (start.co - seam.other_vert(start).co).normalized()
                        direction = (next_vertex.co - start.co).normalized()
                        if forward.dot(direction) < 0.5:
                            continue
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


def _find_wall_gaps(bm, max_distance):
    """Find an open seam aimed at the interior of a nearby seam edge.

    Requiring a shared face keeps this from bridging unrelated surfaces which
    merely happen to be close in 3D space.
    """
    max_distance = max(0.0, float(max_distance))
    gaps = []
    for start in _seam_endpoints(bm):
        incoming = next(edge for edge in start.link_edges if edge.seam)
        forward = start.co - incoming.other_vert(start).co
        if forward.length_squared <= 1.0e-12:
            continue
        forward.normalize()
        best = None
        for face in start.link_faces:
            for wall in face.edges:
                if not wall.seam or start in wall.verts or incoming == wall:
                    continue
                a, b = wall.verts
                ab = b.co - a.co
                if ab.length_squared <= 1.0e-12:
                    continue
                factor = (start.co - a.co).dot(ab) / ab.length_squared
                # End vertices are handled by the ordinary path/junction search.
                if not 0.05 < factor < 0.95:
                    continue
                point = a.co.lerp(b.co, factor)
                delta = point - start.co
                distance = delta.length
                if distance <= 1.0e-9 or (max_distance > 0.0 and distance > max_distance):
                    continue
                if forward.dot(delta / distance) < 0.5:
                    continue
                candidate = (distance, wall.index, start, wall, factor)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
        if best is not None:
            distance, _index, start, wall, factor = best
            gaps.append({"start": start, "wall": wall, "factor": factor, "distance": distance})
    gaps.sort(key=lambda item: item["distance"])
    return gaps


def _close_wall_gap(bm, gap):
    start, wall, factor = gap["start"], gap["wall"], gap["factor"]
    if not (start.is_valid and wall.is_valid):
        return None
    original_vert = wall.verts[0]
    new_wall, point = bmesh.utils.edge_split(wall, original_vert, factor)
    wall.seam = True
    new_wall.seam = True
    try:
        result = bmesh.ops.connect_vert_pair(bm, verts=[start, point])
    except Exception:
        result = {}
    connector = _edge_from_connect_result(result) or bm.edges.get((start, point))
    if connector is None:
        shared_face = next((face for face in start.link_faces if point in face.verts), None)
        if shared_face is not None:
            try:
                _new_face, loop = bmesh.utils.face_split(shared_face, start, point)
                connector = loop.edge
            except ValueError:
                connector = bm.edges.get((start, point))
    if connector is not None:
        connector.seam = True
        connector.select_set(True)
    return connector


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
            settings.seam_gap_include_junctions,
        )
        wall_gaps = _find_wall_gaps(bm, settings.seam_gap_max_distance)
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

        closed_wall_gaps = 0
        for gap in wall_gaps:
            wall = gap["wall"]
            if self.mode == "SELECT":
                if wall.is_valid:
                    wall.select_set(True)
                    selected_edges.add(wall)
                continue
            connector = _close_wall_gap(bm, gap)
            if connector is not None:
                selected_edges.add(connector)
                marked_count += 1
                closed_wall_gaps += 1

        bpy.context.tool_settings.mesh_select_mode = (False, True, False)
        bmesh.update_edit_mesh(mesh)

        gap_count = len(paths) + (len(wall_gaps) if self.mode == "SELECT" else closed_wall_gaps)
        edge_count = len(selected_edges)
        if self.mode == "MARK":
            status = f"Closed {gap_count} seam gap(s), marked {marked_count} edge(s)"
        else:
            status = f"Found {gap_count} seam gap(s), selected {edge_count} edge(s)"

        settings.seam_gap_status = status
        if gap_count:
            self.report({"INFO"}, status)
            return {"FINISHED"}

        settings.seam_gap_status = "No seam gaps found"
        self.report({"INFO"}, settings.seam_gap_status)
        return {"FINISHED"}


class MESH_OT_polygroups_check_and_close_seam_gaps(bpy.types.Operator):
    bl_idname = "mesh.polygroups_check_and_close_seam_gaps"
    bl_label = "Check and Close Seam Gaps"
    bl_description = "Check seam gaps, then close them using the current Seam Gap Check settings"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == "MESH"
            and context.mode in {"OBJECT", "EDIT_MESH"}
        )

    def execute(self, context):
        original_mode = context.active_object.mode
        if original_mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")
        try:
            bpy.ops.mesh.polygroups_check_seam_gaps(mode="SELECT")
            result = bpy.ops.mesh.polygroups_check_seam_gaps(mode="MARK")
        finally:
            if original_mode != "EDIT" and context.active_object.mode == "EDIT":
                bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"} if "FINISHED" in result else result


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
