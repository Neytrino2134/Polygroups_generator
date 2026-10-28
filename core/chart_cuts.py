"""Topology Guard: add boundary rings and longitudinal seams until every chart is a disk.

Pure BMesh. Each pass classifies seam-bounded charts and makes one kind of cut per
chart, then the charts are rebuilt:

- HANDLE (genus > 0): cut the shortest non-separating loop. On quad meshes the loop
  is marched along the tube and placed as two rings at the lips, so the tube becomes
  its own annulus chart, exactly like manual Boundary + Longitudinal.
- ANNULUS / MULTI: connect the significant boundary loops with shortest paths.
- CLOSED (genus 0, no boundary): one slit between the two farthest points.
- DISK: optional neck cuts for protrusions (spikes, legs) and capped tubes (cups).
"""
import heapq
import itertools
import math
from collections import namedtuple

from .chart_topology import charts, classify, chart_kind, is_cut, significant_loops


GuardOptions = namedtuple("GuardOptions", (
    "fix_handles fix_annuli fix_closed fix_necks hole_ratio lip_angle max_flare "
    "sharp_preference neck_angle neck_elongation neck_max_share tube_tolerance "
    "cup_min_height max_passes"
))

DEFAULT_OPTIONS = GuardOptions(
    fix_handles=True, fix_annuli=True, fix_closed=True, fix_necks=True,
    hole_ratio=0.25, lip_angle=math.radians(45.0), max_flare=2.5,
    sharp_preference=1.0, neck_angle=math.radians(35.0), neck_elongation=0.3,
    neck_max_share=0.35, tube_tolerance=0.35, cup_min_height=0.5, max_passes=12,
)

GuardResult = namedtuple("GuardResult", "rings longitudinal before after passes")


# --------------------------------------------------------------------------- graphs

def _edge_cost(edge, sharp_preference):
    length = edge.calc_length()
    if sharp_preference <= 0.0 or not edge.is_manifold:
        return length
    return length / (1.0 + sharp_preference * edge.calc_face_angle(0.0) / math.pi)


def _node_graph(info, sharp_preference=0.0, blocked=()):
    """Corner-node adjacency over the chart's uncut edges."""
    graph = {}
    done = set()
    for face in info.faces:
        for edge in face.edges:
            if edge in done or edge in blocked or is_cut(edge, info.faces):
                continue
            done.add(edge)
            a, b = (info.nodes.node(face, v) for v in edge.verts)
            cost = _edge_cost(edge, sharp_preference)
            graph.setdefault(a, []).append((b, cost, edge))
            graph.setdefault(b, []).append((a, cost, edge))
    return graph


def _dijkstra(graph, sources, targets=None):
    targets = set(targets or ())
    serial = itertools.count()
    dist, prev, queue = {}, {}, []
    for node in sources:
        if node in graph and node not in dist:
            dist[node] = 0.0
            queue.append((0.0, next(serial), node))
    heapq.heapify(queue)
    while queue:
        d, _, node = heapq.heappop(queue)
        if d != dist[node]:
            continue
        if node in targets:
            return dist, prev, node
        for other, cost, edge in graph[node]:
            nd = d + cost
            if nd < dist.get(other, math.inf):
                dist[other] = nd
                prev[other] = (node, edge)
                heapq.heappush(queue, (nd, next(serial), other))
    return dist, prev, None


def _path(prev, node):
    edges = []
    while node in prev:
        node, edge = prev[node]
        edges.append(edge)
    return edges


def _shortest_path(graph, sources, targets):
    _, prev, found = _dijkstra(graph, sources, targets)
    return _path(prev, found) if found is not None else []


def _flood(faces, blocked):
    """Face components across uncut edges that are not in ``blocked``."""
    remaining, parts = set(faces), []
    while remaining:
        start = remaining.pop()
        part, stack = {start}, [start]
        while stack:
            for edge in stack.pop().edges:
                if edge in blocked or is_cut(edge, faces):
                    continue
                for other in edge.link_faces:
                    if other in remaining:
                        remaining.remove(other)
                        part.add(other)
                        stack.append(other)
        parts.append(part)
    return parts


def _non_separating(info, loop_edges):
    return len(_flood(info.faces, set(loop_edges))) == 1


def _ordered_verts(edges):
    incident = {}
    for edge in edges:
        for vert in edge.verts:
            incident.setdefault(vert, []).append(edge)
    if any(len(items) != 2 for items in incident.values()):
        return None
    start = min(incident, key=lambda v: v.index)
    order, previous, current = [start], None, start
    while True:
        edge = next(e for e in incident[current] if e is not previous)
        current = edge.other_vert(current)
        if current is start:
            break
        order.append(current)
        previous = edge
        if len(order) > len(edges):
            return None
    return order if len(order) == len(edges) else None


def _loop_axis(edges):
    order = _ordered_verts(edges)
    if not order:
        return None
    center = sum((v.co for v in order), order[0].co * 0.0) / len(order)
    area = order[0].co * 0.0
    for a, b in zip(order, order[1:] + order[:1]):
        area += (a.co - center).cross(b.co - center)
    return area.normalized() if area.length > 1e-12 else None


def _loop_length(edges):
    return sum(e.calc_length() for e in edges)


# --------------------------------------------------------------------- quad loops

def _quad_loop(edge, faces):
    """Closed quad edge loop through ``edge`` made only of uncut chart edges."""
    loop = [edge]
    prev, vert = edge, edge.verts[0]
    while True:
        # A loop through a seam vertex is open on the cut surface.
        if len(vert.link_edges) != 4 or any(len(f.verts) != 4 or f not in faces
                                            for f in vert.link_faces) \
                or any(is_cut(e, faces) for e in vert.link_edges):
            return None
        shared = set(prev.link_faces)
        following = [e for e in vert.link_edges if e is not prev and not shared & set(e.link_faces)]
        if len(following) != 1:
            return None
        nxt = following[0]
        if nxt is edge:
            return frozenset(loop)
        if is_cut(nxt, faces) or len(loop) > len(faces):
            return None
        loop.append(nxt)
        prev, vert = nxt, nxt.other_vert(vert)


def _quad_loops(info):
    seen, result = set(), []
    for face in info.faces:
        for edge in face.edges:
            if edge in seen or is_cut(edge, info.faces):
                continue
            loop = _quad_loop(edge, info.faces)
            if loop is None:
                seen.add(edge)
                continue
            seen.update(loop)
            result.append(loop)
    return result


def _loop_sides(loop, faces):
    """Split faces touching a quad loop into its two sides."""
    touching = {f for e in loop for f in e.link_faces if f in faces}
    start = next(iter(next(iter(loop)).link_faces))
    side, stack = {start}, [start]
    while stack:
        face = stack.pop()
        for edge in face.edges:
            if edge in loop:
                continue
            for other in edge.link_faces:
                if other in touching and other not in side:
                    side.add(other)
                    stack.append(other)
    other_side = touching - side
    return (side, other_side) if side and other_side else None


def _march(loop, side_faces, info, options, base_length, visited):
    """Step parallel quad loops away from ``loop`` until the tube flares into a lip."""
    lip = math.sin(options.lip_angle)
    current, side = loop, side_faces
    while True:
        axis = _loop_axis(current)
        if axis is None:
            return current, False
        following = set()
        for edge in current:
            face = next((f for f in edge.link_faces if f in side), None)
            if face is None or len(face.verts) != 4:
                return current, False
            corner = next(l for l in face.loops if l.edge is edge)
            following.add(corner.link_loop_next.link_loop_next.edge)
        following = frozenset(following)
        if following in visited:
            return current, True  # walked all the way around a closed handle
        if (len(following) != len(current) or any(is_cut(e, info.faces) for e in following)
                or _ordered_verts(following) is None
                or _loop_length(following) > base_length * options.max_flare):
            return current, False
        area = tilt = 0.0
        for face in side:
            a = face.calc_area()
            area += a
            tilt += abs(face.normal.dot(axis)) * a
        if area > 0.0 and tilt / area > lip:
            return current, False
        visited.add(following)
        side = {f for e in following for f in e.link_faces if f in info.faces} - side
        current = following


# -------------------------------------------------------------------- tree-cotree

def _generator_loops(info, graph, roots=6):
    """Short non-contractible cycles via tree-cotree from a few far-apart roots."""
    nodes = list(graph)
    if not nodes:
        return []
    candidates = []
    root = min(nodes, key=lambda n: (n[1].index, n[0].index))
    for _ in range(roots):
        dist, prev, _found = _dijkstra(graph, [root])
        tree = {edge for _node, edge in prev.values()}
        # Dual spanning tree over uncut edges outside the primal tree.
        faces = info.faces
        start = next(iter(faces))
        dual_seen, stack, cotree = {start}, [start], set()
        while stack:
            face = stack.pop()
            for edge in face.edges:
                if edge in tree or is_cut(edge, faces):
                    continue
                other = edge.link_faces[0] if edge.link_faces[1] is face else edge.link_faces[1]
                if other not in dual_seen:
                    dual_seen.add(other)
                    cotree.add(edge)
                    stack.append(other)
        for node, links in graph.items():
            for other, cost, edge in links:
                if edge in tree or edge in cotree or node not in dist or other not in dist:
                    continue
                cycle = set(_path(prev, node)) ^ set(_path(prev, other))
                cycle.add(edge)
                candidates.append((dist[node] + dist[other] + cost, frozenset(cycle)))
        root = max(dist, key=dist.get)
    unique = {}
    for length, cycle in candidates:
        unique.setdefault(cycle, length)
    return sorted(((length, cycle) for cycle, length in unique.items()), key=lambda item: item[0])


def _meridian(info, options):
    graph = _node_graph(info)
    shortest = None
    for _length, cycle in _generator_loops(info, graph):
        if _non_separating(info, cycle):
            shortest = cycle
            break
    quads = [loop for loop in _quad_loops(info) if _non_separating(info, loop)]
    if quads:
        best = min(quads, key=_loop_length)
        if shortest is None or _loop_length(best) <= _loop_length(shortest) * 1.5:
            return best, True
    return shortest, False


def _cut_handle(info, options):
    loop, is_quad = _meridian(info, options)
    if not loop:
        return set()
    if not is_quad:
        return set(loop)
    sides = _loop_sides(loop, info.faces)
    if sides is None:
        return set(loop)
    base_length = _loop_length(loop)
    visited = {loop}
    ends = []
    for side in sides:
        end, wrapped = _march(loop, side, info, options, base_length, visited)
        if wrapped:
            return set(loop)
        ends.append(end)
    return set(ends[0]) | set(ends[1])


# ------------------------------------------------------------------ annuli/closed

def _connect_boundaries(info, options):
    major = significant_loops(info, options.hole_ratio)
    if len(major) < 2:
        return set()
    graph = _node_graph(info, options.sharp_preference)
    connected = set(major[0].nodes)
    cut = set()
    for loop in major[1:]:
        path = _shortest_path(graph, connected, loop.nodes)
        if not path:
            continue
        cut.update(path)
        connected.update(loop.nodes)
        for edge in path:
            for face in edge.link_faces:
                if face in info.faces:
                    connected.update(info.nodes.node(face, v) for v in edge.verts)
    return cut


def _boundary_cut_graph(info, options):
    """Safety net: arcs from tree-cotree rooted at the whole boundary.

    Cutting every leftover-edge arc turns any chart with a boundary into a disk,
    including non-orientable ones (Moebius bands from flipped faces).
    """
    if not info.loops:
        return set()
    graph = _node_graph(info, options.sharp_preference)
    sources = {node for loop in info.loops for node in loop.nodes}
    dist, prev, _ = _dijkstra(graph, sources)
    tree = {edge for _node, edge in prev.values()}
    faces = info.faces
    start = next(iter(faces))
    seen, stack, cotree = {start}, [start], set()
    while stack:
        face = stack.pop()
        for edge in face.edges:
            if edge in tree or is_cut(edge, faces):
                continue
            other = edge.link_faces[0] if edge.link_faces[1] is face else edge.link_faces[1]
            if other not in seen:
                seen.add(other)
                cotree.add(edge)
                stack.append(other)
    cut = set()
    for node, links in graph.items():
        for other, _cost, edge in links:
            if edge in tree or edge in cotree or node not in dist or other not in dist:
                continue
            cut |= set(_path(prev, node)) ^ set(_path(prev, other))
            cut.add(edge)
    return cut


def _slit_closed(info, options):
    graph = _node_graph(info, options.sharp_preference)
    if not graph:
        return set()
    start = next(iter(graph))
    dist, _prev, _ = _dijkstra(graph, [start])
    a = max(dist, key=dist.get)
    dist, prev, _ = _dijkstra(graph, [a])
    b = max(dist, key=dist.get)
    return set(_path(prev, b))


# -------------------------------------------------------------------------- necks

def _crease_share(edges, faces, angle):
    """Length share of ``edges`` that are chart cuts or creases sharper than ``angle``."""
    total = sharp = 0.0
    for edge in edges:
        length = edge.calc_length()
        total += length
        if is_cut(edge, faces) or (edge.is_manifold and edge.calc_face_angle(0.0) >= angle):
            sharp += length
    return sharp / total if total > 0.0 else 0.0


def _tube_cuts(info, options):
    """Rings around wall regions whose normals are perpendicular to one axis.

    A spike, leg or cup wall is such a region; when both of its boundary loops are
    creases (or chart boundaries) and it is long enough, both loops become rings.
    """
    faces = info.faces
    tolerance = options.tube_tolerance
    limit = max(3, int(len(faces) * options.neck_max_share))
    # Walls are bounded by creases, so only faces touching a crease seed the search.
    seeds = sorted((f for f in faces if any(
        not is_cut(e, faces) and e.calc_face_angle(0.0) >= options.neck_angle for e in f.edges)),
        key=lambda f: f.index)
    rejected, taken, cut = [], set(), set()
    for seed in seeds:
        if seed in taken:
            continue
        # A wall seed has an edge along the tube axis; try each edge direction.
        for edge in seed.edges:
            axis = edge.verts[1].co - edge.verts[0].co
            if is_cut(edge, faces) or axis.length < 1e-12:
                continue
            axis.normalize()
            if any(seed in region and abs(axis.dot(other)) > 0.95 for other, region in rejected):
                continue
            region = _grow_wall(seed, axis, faces, taken, tolerance, limit)
            rings = _wall_rings(region, faces, options) if region else None
            if rings is None:
                if region:
                    rejected.append((axis, region))
                continue
            taken.update(region)
            cut.update(rings)
            break
    return cut


def _grow_wall(seed, axis, faces, taken, tolerance, limit):
    region, stack = {seed}, [seed]
    while stack:
        for edge in stack.pop().edges:
            if is_cut(edge, faces):
                continue
            for other in edge.link_faces:
                if other not in region and other not in taken and abs(other.normal.dot(axis)) <= tolerance:
                    region.add(other)
                    if len(region) > limit:
                        return None
                    stack.append(other)
    return region if len(region) >= 3 else None


def _wall_rings(region, faces, options):
    """Ring edges of an annular wall bounded by creases, or None."""
    wall = classify(region)
    if wall.genus != 0 or len(wall.loops) != 2:
        return None
    loop_a, loop_b = wall.loops
    if loop_b.length <= 0.0 or loop_a.length / loop_b.length > 2.0:
        return None
    if any(_crease_share(loop.edges, faces, options.neck_angle) < 0.6 for loop in wall.loops):
        return None
    diameter = (loop_a.length + loop_b.length) * 0.5 / math.pi
    dist, _prev, found = _dijkstra(_node_graph(wall), loop_a.nodes, loop_b.nodes)
    if found is None or dist[found] < options.cup_min_height * diameter:
        return None
    return {e for loop in wall.loops for e in loop.edges if not is_cut(e, faces)}


def _neck_cuts(info, options):
    if not info.loops:
        return set()
    # Crease-bounded walls give the cleanest rings; smooth protrusions come second.
    walls = _tube_cuts(info, options)
    if walls or len(info.loops) != 1:
        return walls
    boundary_edges = set(info.loops[0].edges)
    boundary_length = info.loops[0].length
    chart_area = sum(f.calc_area() for f in info.faces)
    if chart_area <= 0.0:
        return set()
    candidates = _quad_loops(info)
    scored = []
    for loop in candidates:
        parts = _flood(info.faces, set(loop))
        if len(parts) != 2:
            continue
        cap, rest = parts
        if any(e in boundary_edges for f in cap for e in f.edges):
            cap, rest = rest, cap
        length = _loop_length(loop)
        if length <= 0.0:
            continue
        cap_area = sum(f.calc_area() for f in cap)
        elongation = cap_area / (length * length)
        if elongation >= options.neck_elongation and cap_area <= chart_area * options.neck_max_share:
            scored.append((elongation, loop, cap))
            continue
        # Capped tube: the boundary side is a straight wall ending at this loop.
        ratio = boundary_length / length
        if not 0.6 <= ratio <= 1.0 / 0.6:
            continue
        axis = _loop_axis(loop)
        if axis is None:
            continue
        rest_area = sum(f.calc_area() for f in rest)
        tilt = sum(abs(f.normal.dot(axis)) * f.calc_area() for f in rest) / max(rest_area, 1e-20)
        if tilt > options.tube_tolerance:
            continue
        rest_info = classify(rest)
        graph = _node_graph(rest_info)
        sources = {rest_info.nodes.node(f, v) for e in loop for f in e.link_faces
                   if f in rest for v in e.verts}
        targets = {rest_info.nodes.node(f, v) for e in boundary_edges for f in e.link_faces
                   if f in rest for v in e.verts}
        dist, _prev, found = _dijkstra(graph, sources, targets)
        height = dist[found] if found is not None else 0.0
        if height >= options.cup_min_height * length / math.pi:
            scored.append((height / length, loop, cap))
    scored.sort(key=lambda item: -item[0])
    taken, cut = set(), set()
    for _score, loop, cap in scored:
        if cap & taken or any(f in taken for e in loop for f in e.link_faces):
            continue
        taken.update(cap)
        cut.update(loop)
    return cut


# -------------------------------------------------------------------------- driver

def analyze_charts(bm, faces=None, hole_ratio=DEFAULT_OPTIONS.hole_ratio):
    """[(chart_faces, kind)] for every chart; kind as in ``chart_kind``."""
    return [(info.faces, chart_kind(info, hole_ratio))
            for info in (classify(chart) for chart in charts(bm, faces))]


def topology_guard(bm, faces=None, options=DEFAULT_OPTIONS, protected=()):
    """Mark seams so charts become disks. Returns GuardResult with new edge sets."""
    protected = set(protected)
    rings, longitudinal = set(), set()
    pool = set(faces) if faces is not None else None
    before = analyze_charts(bm, pool, options.hole_ratio)
    passes = 0
    # Seams are only ever added, so a chart that needed no cut stays settled.
    settled = set()
    for passes in range(1, options.max_passes + 1):
        changed = False
        necks_allowed = options.fix_necks
        for chart in charts(bm, pool):
            key = frozenset(chart)
            if key in settled:
                continue
            info = classify(chart)
            kind = chart_kind(info, options.hole_ratio)
            cut, bucket = set(), rings
            if kind == "HANDLE" and options.fix_handles:
                cut = _cut_handle(info, options)
            elif kind in ("ANNULUS", "MULTI") and options.fix_annuli:
                cut, bucket = _connect_boundaries(info, options), longitudinal
            elif kind == "CLOSED" and options.fix_closed:
                cut, bucket = _slit_closed(info, options), longitudinal
            elif kind == "DISK" and necks_allowed:
                cut = _neck_cuts(info, options)
            cut -= protected
            cut = {e for e in cut if not e.seam}
            if not cut and kind in ("HANDLE", "ANNULUS", "MULTI") and (
                    options.fix_handles if kind == "HANDLE" else options.fix_annuli):
                cut, bucket = _boundary_cut_graph(info, options) - protected, longitudinal
                cut = {e for e in cut if not e.seam}
            if cut:
                for edge in cut:
                    edge.seam = True
                bucket.update(cut)
                changed = True
            else:
                settled.add(key)
        if not changed:
            break
    after = analyze_charts(bm, pool, options.hole_ratio)
    return GuardResult(rings, longitudinal, before, after, passes)


def kind_counts(entries):
    counts = {}
    for _faces, kind in entries:
        counts[kind] = counts.get(kind, 0) + 1
    return counts
