"""Topology-driven folded-region discovery, independent of polygon tessellation.

A candidate must separate across a simple neck. Existing holes inside the
candidate are allowed; no other connection to the retained surface is allowed.
"""
from collections import defaultdict
import math
import bmesh
from mathutils import Vector
from mathutils.geometry import tessellate_polygon, intersect_line_line_2d

MAX_REGION_FACES = 512
MAX_NECK_EDGES = 12


def ordered_cycle(edges, patch):
    """Follow a simple cycle in the winding of its original inside face."""
    adjacency = defaultdict(list)
    for edge in edges:
        for vertex in edge.verts:
            adjacency[vertex].append(edge)
    if not 3 <= len(edges) <= MAX_NECK_EDGES or any(len(es) != 2 for es in adjacency.values()):
        return None
    first = min(edges, key=lambda edge: (not any(f in patch for f in edge.link_faces), edge.index))
    inside = next((f for f in first.link_faces if f in patch), None)
    if inside is None:
        return None
    loop = next(l for l in inside.loops if l.edge == first)
    ordered = [loop.vert, loop.link_loop_next.vert]
    used = {first}
    while len(used) < len(edges):
        edge = next((e for e in adjacency[ordered[-1]] if e not in used), None)
        if edge is None:
            return None
        used.add(edge)
        vertex = edge.other_vert(ordered[-1])
        if vertex == ordered[0]:
            return ordered if len(used) == len(edges) else None
        if vertex in ordered:
            return None
        ordered.append(vertex)
    return None


def polygon_geometry(ordered):
    """Validate and tessellate a simple, nearly planar neck without a fixed axis."""
    origin = sum((v.co for v in ordered), Vector())/len(ordered)
    points = [v.co-origin for v in ordered]
    if any(not math.isfinite(x) for p in points for x in p):
        return None
    span = max(p.length for p in points)
    normal = sum((a.cross(b) for a, b in zip(points, points[1:]+points[:1])), Vector())
    if span == 0 or normal.length <= span*span*1e-12:
        return None
    normal.normalize()
    if max(abs(p.dot(normal)) for p in points) > span*.05:
        return None
    axis = max(range(3), key=lambda i: abs(normal[i]))
    axes = [i for i in range(3) if i != axis]
    projected = [Vector((p[axes[0]], p[axes[1]])) for p in points]
    size = len(points)
    for i in range(size):
        for j in range(i+1, size):
            if (j-i) in (1, size-1):
                continue
            if intersect_line_line_2d(projected[i], projected[(i+1)%size],
                                      projected[j], projected[(j+1)%size]) is not None:
                return None
    triangles = [tuple(points[i] for i in triangle) for triangle in tessellate_polygon([points])]
    if len(triangles) != size-2 or any((b-a).cross(c-a).dot(normal) <= span*span*1e-12
                                     for a, b, c in triangles):
        return None
    return origin, normal


def _split_side(neck, seed):
    patch, todo = {seed}, [seed]
    while todo and len(patch) <= MAX_REGION_FACES:
        face = todo.pop()
        for edge in face.edges:
            if edge in neck:
                continue
            for neighbor in edge.link_faces:
                if neighbor not in patch:
                    patch.add(neighbor)
                    todo.append(neighbor)
    return patch, not todo and len(patch) <= MAX_REGION_FACES


def _complete_neck(joins, patch):
    """A missing face may open the neck itself: close its two ends along the
    retained surface's existing boundary, rather than demanding manifold edges."""
    if ordered_cycle(joins, patch) is not None:
        return joins
    degree = defaultdict(int)
    for edge in joins:
        for vertex in edge.verts:
            degree[vertex] += 1
    ends = [v for v, count in degree.items() if count == 1]
    if len(ends) != 2 or any(count>2 for count in degree.values()):
        return joins
    todo = [(ends[0], [])]
    visited = {ends[0]}
    for vertex, path in todo:
        if len(path)+len(joins) >= MAX_NECK_EDGES:
            continue
        for edge in vertex.link_edges:
            if not edge.is_boundary or any(f in patch for f in edge.link_faces):
                continue
            other = edge.other_vert(vertex)
            if other == ends[1]:
                return joins | set(path) | {edge}
            if other not in visited:
                visited.add(other)
                todo.append((other, path+[edge]))
    return joins


def _boundary_components(edges):
    pending = set(edges)
    while pending:
        first = next(iter(pending))
        component, todo = {first}, [first]
        while todo:
            for vertex in todo.pop().verts:
                for edge in vertex.link_edges:
                    if edge in pending and edge not in component:
                        component.add(edge)
                        todo.append(edge)
        pending -= component
        yield component


def candidate_regions(bm):
    """Bridge small holes for discovery only, then remove those virtual caps.
    This lets the same fan search handle an interrupted long quad/ngon strip.
    The final plan always validates the original, unfilled topology and UVs.
    """
    virtual = set()
    original = set(bm.faces)
    try:
        holes = [e for e in bm.edges if e.is_boundary]
        for edges in _boundary_components(holes):
            cycle = ordered_cycle(edges, original)
            if cycle is not None and not bm_face_exists(cycle) and polygon_geometry(cycle) is not None:
                virtual.add(bm.faces.new(list(reversed(cycle))))
        if virtual:
            bm.normal_update()
        return _candidate_regions(bm, virtual)
    finally:
        if virtual:
            bmesh.ops.delete(bm, geom=list(virtual), context='FACES_ONLY')
            bm.normal_update()


def _candidate_regions(bm, virtual):
    from .mesh_fold_repair import _boundary
    seen = set()
    rings_seen = set()
    candidates = []

    def add(patch, neck):
        patch = patch-virtual
        key = frozenset(patch)
        if key in seen or not 2 <= len(patch) <= MAX_REGION_FACES:
            return
        seen.add(key)
        candidates.append((patch, set(neck)))

    # Vertex fans cover triangular, quad and n-gon necks, including triangulated
    # tips. Degree two is a useful seed, not a prerequisite for a defect.
    for vertex in bm.verts:
        if not 2 <= len(vertex.link_faces) <= 8:
            continue
        patch = set(vertex.link_faces)
        while len(patch) <= MAX_REGION_FACES:
            boundary = _boundary(patch)
            extra = {f for e in boundary for f in e.link_faces if f not in patch
                     and len(set(f.edges)&boundary) >= 2}
            if not extra:
                break
            patch.update(extra)
        if len(patch) <= MAX_REGION_FACES:
            neck = {e for f in patch for e in f.edges if any(n not in patch for n in e.link_faces)}
            neck = _complete_neck(neck, patch)
            if ordered_cycle(neck, patch) is not None:
                add(patch, neck)
            # Ring expansion handles a long tube/strip with an n-gon neck.
            # Restrict these extra seeds to locally reversed fans; clean curved
            # surfaces need neither ring growth nor a large neighborhood search.
            local = list(vertex.link_faces)
            if any(a.normal.dot(b.normal)<-.2 for i, a in enumerate(local) for b in local[i+1:]):
                region = set(patch)
                while len(region) <= MAX_REGION_FACES:
                    key = frozenset(region)
                    if key in rings_seen:
                        break
                    rings_seen.add(key)
                    boundary = _boundary(region)
                    if ordered_cycle(boundary, region) is None:
                        break
                    add(region, boundary)
                    extra = {f for e in boundary for f in e.link_faces if f not in region}
                    if not extra:
                        break
                    region.update(extra)

    # A hole can interrupt fan growth. Search separating three/four-edge necks
    # directly in the edge graph, then flood each side without crossing the neck.
    neighbors = {v: {e.other_vert(v): e for e in v.link_edges if e.link_faces} for v in bm.verts}
    necks = set()
    for a, adjacent in neighbors.items():
        for b, ab in adjacent.items():
            if b.index <= a.index:
                continue
            for c in adjacent.keys() & neighbors[b].keys():
                neck = frozenset((ab, adjacent[c], neighbors[b][c]))
                if c.index > b.index and (bm.faces.get((a, b, c)) is None
                                         or any(len(e.link_faces)>2 for e in neck)):
                    necks.add(neck)
        # Four-cycles from pairs of common neighbors; exclude face boundaries.
        for c in {v for b in adjacent for v in neighbors[b] if v.index > a.index and v != a}:
            common = sorted(adjacent.keys() & neighbors[c].keys(), key=lambda v: v.index)
            for i, b in enumerate(common):
                for d in common[i+1:]:
                    neck = frozenset((adjacent[b], neighbors[c][b], neighbors[c][d], adjacent[d]))
                    if min(b.index, d.index) < a.index or (bm.faces.get((a, b, c, d)) is not None
                                                         and all(len(e.link_faces)<=2 for e in neck)):
                        continue
                    necks.add(neck)
    for neck in necks:
        sides, large = [], False
        large_seen = set()
        # A non-manifold neck can touch several disjoint interior layers.
        # Every neck edge contributes seeds, not just the edge with most faces.
        seeds = {face for edge in neck for face in edge.link_faces}
        for seed in sorted(seeds, key=lambda f: f.index):
            if seed in large_seen or any(seed in side for side in sides):
                continue
            patch, complete = _split_side(neck, seed)
            if not complete:
                large = True
                large_seen.update(patch)
            else:
                sides.append(patch)
        # Triangulated overfolds may have an extra triangle on the neck itself.
        # Combine all discarded sides, retaining one ordinary surface side.
        groups = [set().union(*sides)] if large and sides else []
        if not large:
            groups.extend(set().union(*(side for side in sides if side is not keep)) for keep in sides)
        for patch in groups:
            if patch and all(sum(f not in patch for f in e.link_faces)==1 for e in neck):
                add(patch, neck)
    # Repair the full validated region before its smaller internal sub-pockets.
    return sorted(candidates, key=lambda item: (-len(item[0]), min(f.index for f in item[0])))


def folded_region_plan(patch, neck, layers, triangles):
    """Reject ambiguous geometry; return cap layout and data sources when safe."""
    from .mesh_fold_repair import _uv_boundary
    edges = {e for f in patch for e in f.edges}
    joins = {e for e in edges if any(f not in patch for f in e.link_faces)}
    # Internal non-manifold edges can be produced by triangulating a crossed
    # quad. They are safe to remove when every attached face belongs to this
    # region. Only retained-surface connections must match the neck exactly.
    if joins-neck or any(sum(f not in patch for f in e.link_faces)!=1 for e in neck):
        return None
    ordered = ordered_cycle(neck, patch)
    if ordered is None:
        return None
    cap = next((f for f in ordered[0].link_faces if len(f.verts)==len(ordered)
                and set(f.verts)==set(ordered)), None)
    if cap is not None and cap not in patch:
        return None
    # Derive cap winding from the surface that remains, including sharp 90°
    # corners. A dot-product-only test wrongly rejects ordinary box/cylinder rims.
    first_edge = next(e for e in ordered[0].link_edges if ordered[1] in e.verts and e in neck)
    outside_face = next(f for f in first_edge.link_faces if f not in patch)
    outside_loop = next(l for l in outside_face.loops if l.edge == first_edge)
    if outside_loop.vert == ordered[0]:
        ordered.reverse()
    for a, b in zip(ordered, ordered[1:]+ordered[:1]):
        edge = next(e for e in a.link_edges if b in e.verts and e in neck)
        outside = next(f for f in edge.link_faces if f not in patch)
        if next(l for l in outside.loops if l.edge == edge).vert == a:
            return None
    geometry = polygon_geometry(ordered)
    if geometry is None:
        return None
    origin, normal = geometry
    corners = set(ordered)
    if any(any(f not in patch for f in v.link_faces) for f in patch for v in f.verts if v not in corners):
        return None
    outside = {f for e in neck for f in e.link_faces if f not in patch}
    if any(f.normal.length_squared < .5 or f.normal.dot(normal) < -.05 for f in outside):
        return None
    if any(e.seam for e in edges-neck) or len({f.material_index for f in patch}) != 1:
        return None
    span = max((v.co-origin).length for f in patch for v in f.verts)
    volume = absolute = area = 0.0
    for face in patch:
        for corners_tri in triangles[face]:
            a, b, c = (v.co-origin for v in corners_tri)
            if any(not math.isfinite(x) for point in (a, b, c) for x in point):
                return None
            value = a.dot(b.cross(c))/6
            volume += value
            absolute += abs(value)
            area += (b-a).cross(c-a).length/2
    cap_points = [v.co-origin for v in ordered]
    cap_area = sum((cap_points[j]-cap_points[i]).cross(cap_points[k]-cap_points[i]).length/2
                   for i, j, k in tessellate_polygon([cap_points]))
    # Small volume plus a reversed normal also occurs on valid thin relief.
    # Demand substantial excess folded surface; replacing an ordinary sheet
    # with a larger cap is not a justified automatic cleanup.
    if area < cap_area*1.5:
        return None
    # Use the oriented boundary chain, not just edges with one linked face.
    # Triangulated overlaps can have three incidences, or several hole loops
    # meeting at a vertex. Their signed residual still defines a closed chain.
    residual = defaultdict(int)
    for face in patch:
        for loop in face.loops:
            residual[loop.edge] += 1 if loop.vert == loop.edge.verts[0] else -1
    for a, b in zip(ordered, ordered[1:]+ordered[:1]):
        edge = next(e for e in a.link_edges if b in e.verts and e in neck)
        residual[edge] -= 1 if a == edge.verts[0] else -1
    for component in _boundary_components({e for e, count in residual.items() if count}):
        vertices = {v for e in component for v in e.verts}
        center = sum((v.co-origin for v in vertices), Vector())/len(vertices)
        for edge in component:
            a, b = (v.co-origin for v in edge.verts)
            count = residual[edge]
            if count < 0:
                a, b = b, a
            value = b.dot(a.cross(center))/6
            volume += value*abs(count)
            absolute += abs(value)*abs(count)
    if (area == 0 or abs(volume) > area*span*.001
            or absolute > area*span*1e-6 and abs(volume) > absolute*.05
            or not any(f.normal.dot(normal)<-.2 for f in patch)):
        return None
    sources = _uv_boundary(patch, neck, layers)
    if sources is None:
        return None
    return ordered, sources, cap


def bm_face_exists(ordered):
    # Avoid creating a duplicate cap without depending on the BMesh instance.
    return any(len(f.verts)==len(ordered) and set(f.verts)==set(ordered)
               for f in ordered[0].link_faces)
