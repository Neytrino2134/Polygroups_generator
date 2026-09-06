"""Direction-aware seam routing inside a bounded selected-surface corridor."""
import heapq
import itertools
import math
import bmesh


def _chains(edges, anchors=()):
    incident = {}
    for edge in edges:
        for v in edge.verts:
            incident.setdefault(v, []).append(edge)
    remaining = set(edges)
    chains = []
    def walk(start, edge):
        vertices, path = [start], []
        while edge in remaining:
            remaining.remove(edge)
            path.append(edge)
            start = edge.other_vert(start)
            vertices.append(start)
            if len(incident[start]) != 2 or start in anchors:
                break
            edge = next((e for e in incident[start] if e in remaining), None)
            if edge is None:
                break
        return vertices, path
    for v in sorted(incident, key=lambda v: v.index):
        if len(incident[v]) != 2 or v in anchors:
            for e in sorted(incident[v], key=lambda e: e.index):
                if e in remaining:
                    chains.append(walk(v, e))
    while remaining:
        edge = min(remaining, key=lambda e: e.index)
        vertices, path = walk(edge.verts[0], edge)
        # Split closed loops into two anchored routes, preserving closure.
        mid = len(path) // 2
        if mid:
            chains.extend([(vertices[:mid+1], path[:mid]), (vertices[mid:], path[mid:])])
    return chains


def _convex(face):
    scale = max((e.calc_length() for e in face.edges), default=0)
    return scale > 1e-12 and all(
        (l.vert.co-l.link_loop_prev.vert.co).cross(l.link_loop_next.vert.co-l.vert.co).dot(face.normal)
        >= -scale*scale*1e-9 for l in face.loops)


def route_seams(bm, surface_angle, create_edges=False, turn_weight=2.5,
                corridor_width=2.0, edge_preference=0.6, protected=()):
    """Route only internal seams; selection boundaries and junctions are anchors.

    Diagonals use native BMesh face splitting, including warped convex quads.
    No vertices are moved. As with Connect Vertex Path, polygon tessellation may change.
    """
    protected = set(protected)
    bm.verts.index_update()
    bm.edges.index_update()
    eligible = {e for e in bm.edges if e.seam and e not in protected and not e.hide
                and e.is_manifold and all(f.select and not f.hide for f in e.link_faces)}
    anchors = {v for e in bm.edges if e.seam and e not in eligible for v in e.verts}
    chains = _chains(eligible, anchors)
    rerouted = cuts = 0
    for vertices, old_edges in chains:
        if len(old_edges) < 2 or not all(e.is_valid and e.seam for e in old_edges):
            continue
        bm.faces.index_update()
        bm.edges.index_update()
        start, end = vertices[0], vertices[-1]
        original = set(old_edges)
        scale = sorted(e.calc_length() for e in old_edges)[len(old_edges)//2]
        if scale < 1e-12:
            continue
        radius = max(0.1, corridor_width) * scale
        # Geodesic distance to the original seam, measured only through selected faces.
        local_faces = set(f for e in old_edges for f in e.link_faces)
        frontier = set(local_faces)
        for _ in range(min(8, math.ceil(corridor_width) + 1)):
            frontier = {g for f in frontier for v in f.verts for g in v.link_faces
                        if g.select and not g.hide} - local_faces
            local_faces.update(frontier)
        local_edges = {e for f in local_faces for e in f.edges if not e.hide}
        local_verts = {v for e in local_edges for v in e.verts}
        distances = {v: 0.0 for v in vertices}
        serial = itertools.count()
        queue = [(0.0, next(serial), v) for v in vertices]
        heapq.heapify(queue)
        while queue:
            distance, _, v = heapq.heappop(queue)
            if distance != distances[v]:
                continue
            for edge in v.link_edges:
                if edge not in local_edges:
                    continue
                other = edge.other_vert(v)
                candidate = distance + edge.calc_length()
                if candidate <= radius and candidate < distances.get(other, float('inf')):
                    distances[other] = candidate
                    heapq.heappush(queue, (candidate, next(serial), other))
        # Do not touch another seam, a selection border, hidden or non-manifold geometry.
        blocked = {v for v in local_verts if v.hide or any(
            (e.seam and e not in original) or not e.is_manifold or
            any(not f.select or f.hide for f in e.link_faces) for e in v.link_edges)}
        blocked.difference_update((start, end))
        allowed = set(distances) - blocked
        graph = {v: [] for v in allowed}
        ridge = {v: max((min(1.0, e.calc_face_angle(0.0) / max(surface_angle, 0.01))
                         for e in v.link_edges if e in local_edges and e.is_manifold), default=0)
                 for v in allowed}
        def add(a, b, face=None):
            if a not in allowed or b not in allowed:
                return
            if isinstance(face, tuple):
                _, _, crossing, factor = face
                point = crossing.verts[0].co.lerp(crossing.verts[1].co, factor)
                length = (point-a.co).length + (b.co-point).length
            else:
                length = (b.co-a.co).length
            if length <= scale*1e-8:
                return
            deviation = (distances[a] + distances[b]) / (2*radius)
            fit = 0.6*(1-(ridge[a]+ridge[b])*0.5)
            cost = length*(1 + 3*deviation*deviation + fit + (edge_preference if face else 0))
            graph[a].append((b, cost, face))
            graph[b].append((a, cost, face))
        for edge in sorted(local_edges, key=lambda e: e.index):
            if edge.is_manifold and all(f.select and not f.hide for f in edge.link_faces):
                add(*edge.verts)
        if create_edges:
            for face in sorted(local_faces, key=lambda f: f.index):
                if len(face.verts) < 4 or len(face.verts) > 32 or not _convex(face):
                    continue
                vs = list(face.verts)
                for i, a in enumerate(vs):
                    for b in vs[i+1:]:
                        if bm.edges.get((a,b)) is None:
                            add(a, b, face)
            # A Connect Vertex Path equivalent across two adjacent triangles.
            # The crossing is placed on their shared edge, so both new segments
            # remain on the original piecewise-planar surface.
            for edge in sorted(local_edges, key=lambda e: e.index):
                if (not edge.is_manifold or edge.seam or edge in protected or
                        any(f not in local_faces or len(f.verts) != 3 for f in edge.link_faces)):
                    continue
                f, g = edge.link_faces
                a = next(v for v in f.verts if v not in edge.verts)
                b = next(v for v in g.verts if v not in edge.verts)
                if a not in allowed or b not in allowed or bm.edges.get((a,b)) is not None:
                    continue
                c, d = edge.verts
                n = f.normal + g.normal
                ab, cd, ac = b.co-a.co, d.co-c.co, c.co-a.co
                denominator = ab.cross(cd).dot(n)
                if abs(denominator) < scale*scale*1e-10:
                    continue
                t = ac.cross(cd).dot(n)/denominator
                u = ac.cross(ab).dot(n)/denominator
                if not (0.05 < t < 0.95 and 0.05 < u < 0.95):
                    continue
                add(a,b,(f,g,edge,u))
        if start not in graph or end not in graph:
            continue
        def turn(prev, v, nxt):
            if prev is None:
                return 0.0
            dot = (v.co-prev.co).normalized().dot((nxt.co-v.co).normalized())
            return scale*turn_weight*(1-max(-1.0,min(1.0,dot)))**2
        # State includes incoming direction, unlike ordinary shortest edge paths.
        first = (None, start)
        best = {first: 0.0}
        previous = {}
        queue = [(0.0, next(serial), first)]
        goal = None
        while queue:
            cost, _, state = heapq.heappop(queue)
            if cost != best[state]:
                continue
            prev, v = state
            if v == end:
                goal = state
                break
            for nxt, base, face in graph[v]:
                if nxt == prev or nxt == start:
                    continue
                new_cost = cost + base + turn(prev, v, nxt)
                new_state = (v, nxt)
                if new_cost < best.get(new_state, float('inf')):
                    best[new_state] = new_cost
                    previous[new_state] = (state, face)
                    heapq.heappush(queue, (new_cost, next(serial), new_state))
        if goal is None:
            continue
        route = []
        while goal != first:
            state, face = previous[goal]
            route.append((goal[0], goal[1], face))
            goal = state
        route.reverse()
        route_vertices = [start] + [b for a,b,f in route]
        if len(set(route_vertices)) != len(route_vertices):
            continue
        if route_vertices == vertices:
            continue
        # At most one diagonal in each polygon: no crossing chords or stale faces.
        diagonal_faces = [item for a,b,f in route if f is not None
                          for item in (f[:2] if isinstance(f,tuple) else (f,))]
        if len(set(diagonal_faces)) != len(diagonal_faces):
            continue
        old_cost = 0.0
        for i, (a,b) in enumerate(zip(vertices,vertices[1:])):
            match = next((cost for nxt,cost,f in graph.get(a,[]) if nxt == b and f is None), None)
            if match is None:
                old_cost = float('inf')
                break
            old_cost += match + turn(vertices[i-1] if i else None,a,b)
        new_cost = sum(next(cost for nxt,cost,f in graph[a] if nxt == b and f == face)
                       + turn(route_vertices[i-1] if i else None,a,b)
                       for i,(a,b,face) in enumerate(route))
        if new_cost >= old_cost - scale*1e-6:
            continue
        new_edges = []
        for a,b,face in route:
            edge = bm.edges.get((a,b))
            if edge is None and isinstance(face, tuple):
                f, g, crossing, factor = face
                _, point = bmesh.utils.edge_split(crossing, crossing.verts[0], factor)
                for source, endpoint in ((f,a),(g,b)):
                    # Graph arcs are undirected: match endpoints to their faces.
                    if endpoint not in source.verts:
                        endpoint = b if endpoint == a else a
                    new_face, loop = bmesh.utils.face_split(source,endpoint,point)
                    new_face.select_set(True)
                    source.select_set(True)
                    new_edges.append(loop.edge)
                    cuts += 1
                continue
            if edge is None:
                new_face, loop = bmesh.utils.face_split(face,a,b)
                new_face.select_set(True)
                face.select_set(True)
                edge = loop.edge
                cuts += 1
            new_edges.append(edge)
        for edge in old_edges:
            edge.seam = False
        for edge in new_edges:
            edge.seam = True
        rerouted += 1
    bm.normal_update()
    return rerouted, cuts
