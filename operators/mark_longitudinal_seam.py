import heapq
import itertools

import bmesh
import bpy
from mathutils import Vector

from ..core.smart_seam_routing import route_seams
from ..pin_edges import pin_layer, set_pinned
from .unwrap_angle_based import unwrap_selected_angle_based


TOOL_ID = "polygroups_generator.longitudinal_seam_tool"


def _selected_faces(bm):
    return {face for face in bm.faces if face.select}


def _face_components(faces):
    remaining = set(faces)
    components = []

    while remaining:
        start_face = remaining.pop()
        stack = [start_face]
        component = {start_face}

        while stack:
            face = stack.pop()
            for edge in face.edges:
                for linked_face in edge.link_faces:
                    if linked_face not in remaining:
                        continue
                    remaining.remove(linked_face)
                    component.add(linked_face)
                    stack.append(linked_face)

        components.append(component)

    return components


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


def _ordered_edge_component_vertices(component_edges):
    """Return a stable walk around an open or closed boundary component."""
    incident = {}
    for edge in component_edges:
        for vert in edge.verts:
            incident.setdefault(vert, []).append(edge)
    if not incident:
        return []
    endpoints = [vert for vert, edges in incident.items() if len(edges) == 1]
    current = min(endpoints or incident, key=lambda vert: vert.index)
    ordered = [current]
    previous_edge = None
    while True:
        candidates = [edge for edge in incident[current] if edge is not previous_edge]
        if not candidates:
            break
        edge = min(candidates, key=lambda item: item.index)
        following = edge.other_vert(current)
        if following == ordered[0] or following in ordered:
            break
        ordered.append(following)
        previous_edge, current = edge, following
    return ordered


def _offset_boundary_vertex(component, guide_position, offset):
    ordered = _ordered_edge_component_vertices(component[0])
    if not ordered:
        return None
    nearest = min(range(len(ordered)), key=lambda index: (ordered[index].co - guide_position).length)
    if len(component[0]) == len(ordered):
        return ordered[(nearest + offset) % len(ordered)]
    return ordered[max(0, min(len(ordered) - 1, nearest + offset))]


def _active_selection_position(bm, selected_faces=None):
    component_verts = None
    if selected_faces is not None:
        component_verts = set()
        for face in selected_faces:
            component_verts.update(face.verts)

    active = bm.select_history.active
    if isinstance(active, bmesh.types.BMVert) and (component_verts is None or active in component_verts):
        return active.co.copy()
    if isinstance(active, bmesh.types.BMEdge) and (
        selected_faces is None or any(face in selected_faces for face in active.link_faces)
    ):
        return sum((vert.co for vert in active.verts), Vector()) / 2.0
    if isinstance(active, bmesh.types.BMFace) and (selected_faces is None or active in selected_faces):
        return active.calc_center_median()

    selected_edges = [
        edge
        for edge in bm.edges
        if edge.select and (selected_faces is None or any(face in selected_faces for face in edge.link_faces))
    ]
    if selected_edges:
        edge = selected_edges[0]
        return sum((vert.co for vert in edge.verts), Vector()) / 2.0

    selected_verts = [
        vert
        for vert in bm.verts
        if vert.select and (component_verts is None or vert in component_verts)
    ]
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
    return _shortest_path_edges(graph, sources, targets)


def _shortest_path_edges(graph, sources, targets):
    if not sources or not targets:
        return []

    _, previous, target = _dijkstra(graph, sources, targets)
    if target is None:
        return []
    return _edges_from_previous(previous, target)


def _current_view_direction_world(context):
    space = getattr(context, "space_data", None)
    region_3d = getattr(space, "region_3d", None)
    if region_3d is not None:
        return (region_3d.view_rotation @ Vector((0.0, 0.0, -1.0))).normalized()

    screen = getattr(context, "screen", None)
    if screen is None:
        return None

    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type == "VIEW_3D" and space.region_3d is not None:
                return (space.region_3d.view_rotation @ Vector((0.0, 0.0, -1.0))).normalized()

    return None


def _view_side_weighted_graph(graph, context, obj, prefer_backside=True):
    view_direction = _current_view_direction_world(context)
    if view_direction is None or obj is None:
        return None

    matrix_world = obj.matrix_world
    world_positions = {vert: matrix_world @ vert.co for vert in graph}
    if not world_positions:
        return None

    center = sum(world_positions.values(), Vector()) / len(world_positions)
    depths = {
        vert: (position - center).dot(view_direction)
        for vert, position in world_positions.items()
    }
    min_depth = min(depths.values())
    max_depth = max(depths.values())
    depth_range = max_depth - min_depth
    if depth_range <= 0.000001:
        return None

    weighted_graph = {}
    for vert, links in graph.items():
        for neighbor, base_weight, edge in links:
            edge_depth = (depths[vert] + depths[neighbor]) * 0.5
            backside_factor = (edge_depth - min_depth) / depth_range
            wrong_side_factor = (1.0 - backside_factor) if prefer_backside else backside_factor
            weight = base_weight * (1.0 + (wrong_side_factor**2) * 20.0)
            weighted_graph.setdefault(vert, []).append((neighbor, weight, edge))

    return weighted_graph


def _backside_weighted_graph(graph, context, obj):
    return _view_side_weighted_graph(graph, context, obj, prefer_backside=True)


def _frontside_weighted_graph(graph, context, obj):
    return _view_side_weighted_graph(graph, context, obj, prefer_backside=False)


def _backside_boundary_path_edges(graph, loop_a, loop_b, context, obj):
    weighted_graph = _backside_weighted_graph(graph, context, obj)
    if weighted_graph is None:
        return []

    return _shortest_boundary_path_edges(weighted_graph, loop_a, loop_b)


def _frontside_boundary_path_edges(graph, loop_a, loop_b, context, obj):
    weighted_graph = _frontside_weighted_graph(graph, context, obj)
    if weighted_graph is None:
        return []

    return _shortest_boundary_path_edges(weighted_graph, loop_a, loop_b)


def _selection_center(selected_faces):
    verts = {vert for face in selected_faces for vert in face.verts}
    if not verts:
        return None
    return sum((vert.co for vert in verts), Vector()) / len(verts)


def _opposite_guide_position(selected_faces, guide_position):
    center = _selection_center(selected_faces)
    if center is None or guide_position is None:
        return None
    return center + (center - guide_position)


def _avoid_primary_weighted_graph(graph, primary_edges):
    primary_verts = {vert for edge in primary_edges for vert in edge.verts}
    if not primary_verts:
        return None

    weighted_graph = {}
    for vert, links in graph.items():
        for neighbor, base_weight, edge in links:
            penalty = 50.0 if vert in primary_verts or neighbor in primary_verts else 0.0
            weighted_graph.setdefault(vert, []).append((neighbor, base_weight * (1.0 + penalty), edge))

    return weighted_graph


def _distinct_secondary_edges(primary_edges, secondary_edges):
    primary_set = set(primary_edges)
    secondary_set = set(secondary_edges)
    if not secondary_set or not (secondary_set - primary_set):
        return []
    return list(secondary_set)


def _opposite_boundary_path_edges(
    graph,
    loop_a,
    loop_b,
    selected_faces,
    primary_edges,
    context,
    obj,
    guide_position,
    prefer_backside,
):
    seam_edges = []
    if prefer_backside:
        seam_edges = _frontside_boundary_path_edges(graph, loop_a, loop_b, context, obj)

    if not seam_edges:
        opposite_guide = _opposite_guide_position(selected_faces, guide_position)
        if opposite_guide is not None:
            seam_edges = _guided_path_edges(graph, loop_a, loop_b, opposite_guide)

    if not seam_edges:
        weighted_graph = _frontside_weighted_graph(graph, context, obj)
        if weighted_graph is not None:
            seam_edges = _shortest_boundary_path_edges(weighted_graph, loop_a, loop_b)

    if not seam_edges:
        weighted_graph = _avoid_primary_weighted_graph(graph, primary_edges)
        if weighted_graph is not None:
            seam_edges = _shortest_boundary_path_edges(weighted_graph, loop_a, loop_b)

    return _distinct_secondary_edges(primary_edges, seam_edges)


def _guided_cone_path_edges(graph, apex, boundary_loop, guide_position):
    guide_vert = _nearest_graph_vertex(graph, guide_position)
    if guide_vert is None:
        return []

    distances, previous, _ = _dijkstra(graph, [guide_vert])
    if apex not in distances:
        return []

    boundary_verts = [vert for vert in boundary_loop if vert in distances]
    if not boundary_verts:
        return []

    target = min(boundary_verts, key=lambda vert: distances[vert])
    return _edges_from_previous(previous, apex) + _edges_from_previous(previous, target)


def _cone_longitudinal_path_edges(graph, boundary_loop, context, obj, guide_position, prefer_backside):
    distances, previous_from_boundary, _ = _dijkstra(graph, boundary_loop)
    apex_candidates = [
        vert
        for vert in graph
        if vert not in boundary_loop and vert in distances
    ]
    if not apex_candidates:
        return []

    apex = max(apex_candidates, key=lambda vert: distances[vert])
    seam_edges = []
    if prefer_backside:
        weighted_graph = _backside_weighted_graph(graph, context, obj)
        if weighted_graph is not None:
            seam_edges = _shortest_path_edges(weighted_graph, [apex], boundary_loop)

    if not seam_edges and guide_position is not None:
        seam_edges = _guided_cone_path_edges(graph, apex, boundary_loop, guide_position)

    if not seam_edges:
        seam_edges = _edges_from_previous(previous_from_boundary, apex)

    return seam_edges


def _opposite_cone_longitudinal_path_edges(
    graph,
    boundary_loop,
    selected_faces,
    primary_edges,
    context,
    obj,
    guide_position,
    prefer_backside,
):
    distances, _previous_from_boundary, _ = _dijkstra(graph, boundary_loop)
    apex_candidates = [
        vert
        for vert in graph
        if vert not in boundary_loop and vert in distances
    ]
    if not apex_candidates:
        return []

    apex = max(apex_candidates, key=lambda vert: distances[vert])
    seam_edges = []
    if prefer_backside:
        weighted_graph = _frontside_weighted_graph(graph, context, obj)
        if weighted_graph is not None:
            seam_edges = _shortest_path_edges(weighted_graph, [apex], boundary_loop)

    if not seam_edges:
        opposite_guide = _opposite_guide_position(selected_faces, guide_position)
        if opposite_guide is not None:
            seam_edges = _guided_cone_path_edges(graph, apex, boundary_loop, opposite_guide)

    if not seam_edges:
        weighted_graph = _avoid_primary_weighted_graph(graph, primary_edges)
        if weighted_graph is not None:
            seam_edges = _shortest_path_edges(weighted_graph, [apex], boundary_loop)

    return _distinct_secondary_edges(primary_edges, seam_edges)


def _mark_boundary_edges(boundary_edges):
    marked_count = 0
    for edge in boundary_edges:
        if not edge.seam:
            marked_count += 1
        edge.seam = True
    return marked_count


def _longitudinal_seam_edges_for_faces(
    bm,
    selected_faces,
    context=None,
    obj=None,
    prefer_backside=False,
    double_seam=False,
    seam_offset=0,
    path_method="SIMPLE",
    create_new_edges=True,
):
    boundary_edges = _selection_boundary_edges(bm, selected_faces)
    components = _edge_components(boundary_edges)
    components.sort(key=lambda item: len(item[0]), reverse=True)

    graph, _edge_lookup = _path_graph(selected_faces, boundary_edges)
    if not graph:
        return None, "No side-surface edge path found"

    guide_position = _active_selection_position(bm, selected_faces)
    if guide_position is None:
        guide_position = _selection_center(selected_faces)
    seam_edges = []
    if len(components) >= 2:
        loop_a = components[0][1]
        loop_b = components[1][1]
        if seam_offset:
            source = _offset_boundary_vertex(components[0], guide_position, seam_offset)
            seam_edges = _shortest_path_edges(graph, [source] if source else (), loop_b)
        elif prefer_backside:
            seam_edges = _backside_boundary_path_edges(graph, loop_a, loop_b, context, obj)

        if not seam_edges and guide_position is not None:
            seam_edges = _guided_path_edges(graph, loop_a, loop_b, guide_position)

        if not seam_edges:
            seam_edges = _shortest_boundary_path_edges(graph, loop_a, loop_b)

        if double_seam:
            seam_edges += _opposite_boundary_path_edges(
                graph,
                loop_a,
                loop_b,
                selected_faces,
                seam_edges,
                context,
                obj,
                guide_position,
                prefer_backside,
            )

    elif len(components) == 1:
        boundary_loop = components[0][1]
        if seam_offset:
            source = _offset_boundary_vertex(components[0], guide_position, seam_offset)
            distances, _previous, _target = _dijkstra(graph, boundary_loop)
            apexes = [vert for vert in graph if vert not in boundary_loop and vert in distances]
            apex = max(apexes, key=lambda vert: distances[vert]) if apexes else None
            seam_edges = _shortest_path_edges(graph, [apex] if apex else (), [source] if source else ())
        else:
            seam_edges = _cone_longitudinal_path_edges(
                graph, boundary_loop, context, obj, guide_position, prefer_backside,
            )
        if double_seam:
            seam_edges += _opposite_cone_longitudinal_path_edges(
                graph,
                boundary_loop,
                selected_faces,
                seam_edges,
                context,
                obj,
                guide_position,
                prefer_backside,
            )

    else:
        return None, "Selection needs boundary edges or a cone-like side selection"

    if not seam_edges:
        return None, "Could not find a longitudinal path"

    marked_count = 0
    for edge in set(seam_edges):
        if not edge.seam:
            marked_count += 1
        edge.seam = True
        edge.select = True

    cuts = 0
    if path_method == "SMART":
        _rerouted, cuts = route_seams(
            bm,
            0.785398,
            create_edges=create_new_edges,
            turn_weight=6.0,
            corridor_width=2.5,
            edge_preference=0.35,
        )

    return (marked_count, boundary_edges, cuts), None


def _mark_longitudinal_seam_edges(bm, context=None, obj=None, prefer_backside=False,
                                  double_seam=False, seam_offset=0,
                                  path_method="SIMPLE", create_new_edges=True):
    selected_faces = _selected_faces(bm)
    if not selected_faces:
        return None, "Select cylinder or cone side faces first"

    total_marked_count = 0
    all_boundary_edges = set()
    processed_count = 0
    failed_count = 0
    last_warning = ""

    for face_component in _face_components(selected_faces):
        result, warning = _longitudinal_seam_edges_for_faces(
            bm,
            face_component,
            context=context,
            obj=obj,
            prefer_backside=prefer_backside,
            double_seam=double_seam,
            seam_offset=seam_offset,
            path_method=path_method,
            create_new_edges=create_new_edges,
        )
        if warning:
            failed_count += 1
            last_warning = warning
            continue

        marked_count, boundary_edges, _cuts = result
        total_marked_count += marked_count
        all_boundary_edges.update(boundary_edges)
        processed_count += 1

    if processed_count == 0:
        return None, last_warning or "Could not find a longitudinal path"

    return (total_marked_count, all_boundary_edges, processed_count, failed_count), None


class MESH_OT_polygroups_mark_longitudinal_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_longitudinal_seam"
    bl_label = "Create Longitudinal Seam"
    bl_description = "Create one lengthwise seam on selected cylinder or cone side faces"
    bl_options = {"REGISTER", "UNDO"}

    double_seam: bpy.props.BoolProperty(name="Double Seam", default=False)
    prefer_backside: bpy.props.BoolProperty(
        name="Prefer Backside",
        description="Prefer the side facing away from the current view",
        default=False,
    )
    seam_offset: bpy.props.IntProperty(
        name="Seam Offset",
        description="Move the seam left or right by boundary edge steps",
        default=0,
        min=-100,
        max=100,
    )
    path_method: bpy.props.EnumProperty(
        name="Path Search",
        items=(
            ("SIMPLE", "Simple", "Use the existing shortest edge-path algorithm"),
            ("SMART", "Smart", "Prefer smooth paths and optionally cut diagonally across faces"),
        ),
        default="SIMPLE",
    )
    create_new_edges: bpy.props.BoolProperty(
        name="Create New Edges",
        description="Allow Smart routing to split faces for a smoother diagonal path",
        default=True,
    )
    mark_as_pinned: bpy.props.BoolProperty(
        name="Mark Generated As Pinned",
        description="Pin seam edges generated by this operation",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "mark_as_pinned", toggle=True)
        row.prop(self, "double_seam", toggle=True)
        row.prop(self, "prefer_backside", toggle=True)
        layout.prop(self, "seam_offset")
        layout.prop(self, "path_method")
        if self.path_method == "SMART":
            layout.prop(self, "create_new_edges")

    def invoke(self, context, event):
        settings = context.scene.polygroups_seam_finalization_settings
        self.double_seam = settings.double_longitudinal_seam
        self.prefer_backside = settings.prefer_backside_longitudinal_seam
        self.mark_as_pinned = settings.pin_longitudinal_seam
        return self.execute(context)

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
        initial_seams = {edge for edge in bm.edges if edge.seam}

        settings = context.scene.polygroups_seam_finalization_settings
        result, warning = _mark_longitudinal_seam_edges(
            bm,
            context=context,
            obj=obj,
            prefer_backside=self.prefer_backside,
            double_seam=self.double_seam,
            seam_offset=self.seam_offset,
            path_method=self.path_method,
            create_new_edges=self.create_new_edges,
        )
        if warning:
            self.report({"WARNING"}, warning)
            return {"CANCELLED"}

        if self.mark_as_pinned:
            pins = pin_layer(bm, True)
            set_pinned(
                [edge for edge in bm.edges
                 if edge.seam and edge not in initial_seams
                 and any(face.select for face in edge.link_faces)],
                pins,
            )

        bmesh.update_edit_mesh(mesh)
        auto_unwrapped = False
        if settings.auto_unwrap_after_seam:
            auto_unwrapped = unwrap_selected_angle_based(
                context,
                average_islands=settings.auto_average_islands_scale_after_unwrap,
            )

        suffix = " and unwrapped selected faces" if auto_unwrapped else ""
        failed_suffix = f"; skipped {result[3]} shape(s)" if result[3] else ""
        self.report(
            {"INFO"},
            f"Marked {result[0]} longitudinal seam edge(s) on {result[2]} shape(s){failed_suffix}{suffix}",
        )
        return {"FINISHED"}


class MESH_OT_polygroups_longitudinal_seam_tool_click(bpy.types.Operator):
    bl_idname = "mesh.polygroups_longitudinal_seam_tool_click"
    bl_label = "Create Longitudinal Seam from Point"
    bl_description = "Pick a vertex, select its seam-bounded island, and create a longitudinal seam"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"
                and context.area is not None and context.area.type == "VIEW_3D"
                and context.region is not None and context.region.type == "WINDOW")

    def invoke(self, context, event):
        from .smart_angle_seams import select_linked_faces_by_seam

        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        old_mode = tuple(context.tool_settings.mesh_select_mode)
        flags = [(item, item.select) for sequence in (bm.verts, bm.edges, bm.faces)
                 for item in sequence]
        history = list(bm.select_history)
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="VERT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.view3d.select(location=(event.mouse_region_x, event.mouse_region_y), deselect_all=True)
        bm = bmesh.from_edit_mesh(obj.data)
        picked = [vert for vert in bm.verts if vert.select and not vert.hide]
        if len(picked) != 1:
            for item, selected in flags:
                if item.is_valid:
                    item.select = selected
            bm.select_history.clear()
            for item in history:
                if item.is_valid and item.select:
                    bm.select_history.add(item)
            context.tool_settings.mesh_select_mode = old_mode
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            return {"CANCELLED"}
        bm.select_history.clear()
        bm.select_history.add(picked[0])
        select_linked_faces_by_seam(bm, (True, False, False))
        return bpy.ops.mesh.polygroups_mark_longitudinal_seam("INVOKE_DEFAULT")


class MESH_OT_polygroups_mark_boundary_and_longitudinal_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_boundary_and_longitudinal_seam"
    bl_label = "Boundary + Longitudinal Seam"
    bl_description = "Mark selected face boundary seams, then create one lengthwise cylinder or cone seam"
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

        settings = context.scene.polygroups_seam_finalization_settings
        result, warning = _mark_longitudinal_seam_edges(
            bm,
            context=context,
            obj=obj,
            prefer_backside=settings.prefer_backside_longitudinal_seam,
            double_seam=settings.double_longitudinal_seam,
        )
        if warning:
            self.report({"WARNING"}, warning)
            return {"CANCELLED"}

        longitudinal_count, boundary_edges, processed_count, failed_count = result
        boundary_count = _mark_boundary_edges(boundary_edges)

        bmesh.update_edit_mesh(mesh)
        auto_unwrapped = False
        if settings.auto_unwrap_after_seam:
            auto_unwrapped = unwrap_selected_angle_based(
                context,
                average_islands=settings.auto_average_islands_scale_after_unwrap,
            )

        suffix = " and unwrapped selected faces" if auto_unwrapped else ""
        failed_suffix = f"; skipped {failed_count} shape(s)" if failed_count else ""
        self.report(
            {"INFO"},
            f"Marked {boundary_count} boundary seam edge(s) and {longitudinal_count} longitudinal seam edge(s) on {processed_count} shape(s){failed_suffix}{suffix}",
        )
        return {"FINISHED"}
