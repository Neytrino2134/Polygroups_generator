"""Local folded-pocket repair and optional singleton UV triangle contraction.

Closed manifold pockets retain their outer boundary. Explicit UV outlier
contractions validate the surrounding vertex fan before merging to center.
"""
import math
from statistics import median

import bmesh
from mathutils import Vector
from mathutils.geometry import tessellate_polygon


def inspect_triangle_quality(bm, selected_only=False, thin_quality=0.01, uv_stretch=50.0):
    """Return face indices and scale-independent triangle/UV diagnostics.

    Cross products avoid the cancellation in BMFace.calc_area on tiny triangles
    far from the origin. Thin/UV findings are inspection targets, not deletions.
    """
    bm.faces.index_update()
    uv = bm.loops.layers.uv.active
    found = set()
    counts = dict(zero_triangles=0, thin_triangles=0, uv_triangles=0)
    for triangle in bm.calc_loop_triangles():
        face = triangle[0].face
        if not _visible(face) or (selected_only and not face.select):
            continue
        a, b, c = (l.vert.co for l in triangle)
        x, y = b - a, c - a
        cross = x.cross(y).length
        if cross == 0.0:
            counts['zero_triangles'] += 1
            found.add(face.index)
            continue
        quality = 2 * math.sqrt(3) * cross / max(
            x.length_squared + y.length_squared + (c - b).length_squared, 1e-300)
        if quality < thin_quality:
            counts['thin_triangles'] += 1
            found.add(face.index)
        if uv is not None:
            points = [l[uv].uv for l in triangle]
            u, v = points[1] - points[0], points[2] - points[0]
            j1 = u / x.length
            j2 = (v - j1 * (x.dot(y) / x.length)) / (cross / x.length)
            trace = j1.length_squared + j2.length_squared
            det = abs(j1.x * j2.y - j1.y * j2.x)
            largest = (trace + math.sqrt(max(0, trace * trace - 4 * det * det))) * .5
            stretch = largest / det if det else math.inf
            if not math.isfinite(stretch) or stretch >= uv_stretch:
                counts['uv_triangles'] += 1
                found.add(face.index)
    return found, counts


def _visible(face):
    return not face.hide and not any(v.hide for v in face.verts)


def _boundary(patch):
    return {e for f in patch for e in f.edges
            if sum(f in patch for f in e.link_faces) == 1}


def _uv_boundary(patch, boundary, layers):
    """Use existing neighbors across uncut edges, patch corners at UV seams."""
    result = {}
    for layer in layers:
        values = {}
        for edge in boundary:
            inside = next((f for f in edge.link_faces if f in patch), None)
            outside = next(f for f in edge.link_faces if f not in patch)
            face = inside if edge.seam and inside is not None else outside
            priority = 1 if edge.seam and inside is not None else 2
            for vert in edge.verts:
                loop = next(l for l in face.loops if l.vert == vert)
                values.setdefault(vert, []).append((priority, loop))
        result[layer] = {}
        for vert, candidates in values.items():
            priority = max(p for p, _ in candidates)
            loops = [l for p, l in candidates if p == priority]
            if any((l[layer].uv - loops[0][layer].uv).length > 1e-6 for l in loops):
                return None  # Unmarked UV cut: do not choose an arbitrary island.
            result[layer][vert] = loops[0]
    return result


def _plan(patch, layers, tolerance, backtracking_ear=False):
    patch = set(patch)
    # Absorb a concave neighboring face that shares two sides of the pocket.
    # Merely dissolving the first two faces would leave an overlapping ear.
    while len(patch) <= 8:
        boundary = _boundary(patch)
        adjacent = {f for e in boundary for f in e.link_faces if f not in patch}
        absorb = [f for f in adjacent if len(set(f.edges) & boundary) >= 2]
        if not absorb:
            break
        patch.update(absorb)
    if len(patch) > 8 or any(not _visible(f) for f in patch):
        return None
    edges = {e for f in patch for e in f.edges}
    boundary = _boundary(patch)
    if len(boundary) != 3 or any(not e.is_manifold for e in edges):
        return None
    verts = {v for e in boundary for v in e.verts}
    if len(verts) != 3 or any(sum(v in e.verts for e in boundary) != 2 for v in verts):
        return None
    internal = edges - boundary
    if any(e.seam for e in internal) or len({f.material_index for f in patch}) != 1:
        return None
    if any(l[layer].pin_uv for f in patch for l in f.loops for layer in layers):
        return None
    interior_verts = {v for f in patch for v in f.verts} - verts
    if any(any(f not in patch for f in v.link_faces) for v in interior_verts):
        return None
    # Follow a boundary edge in the same direction as its original inside face.
    edge = min(boundary, key=lambda e: e.index)
    face = next(f for f in edge.link_faces if f in patch)
    loop = next(l for l in face.loops if l.edge == edge)
    ordered = [loop.vert, loop.link_loop_next.vert]
    ordered.append(next(v for v in verts if v not in ordered))
    a, b, c = (v.co for v in ordered)
    normal = (b - a).cross(c - a)
    if normal.length <= tolerance * tolerance:
        return None
    normal.normalize()
    ear_sources = None
    crossed_ear = False
    if backtracking_ear:
        # A degree-two tip can turn a quad back over its closing triangle.
        # Removing that tip retains the quad's boundary corners, including its
        # UV island, rather than inheriting the detached triangle's packed UVs.
        triangles = [f for f in patch if len(f.verts) == 3]
        quads = [f for f in patch if len(f.verts) == 4]
        if len(patch) != 2 or len(triangles) != 1 or len(quads) != 1 or len(interior_verts) != 1:
            return None
        tip = next(iter(interior_verts))
        triangle, quad = triangles[0], quads[0]
        if len(tip.link_edges) != 2 or tip not in triangle.verts:
            return None
        span = max(e.calc_length() for e in boundary)
        depth = abs((tip.co - a).dot(normal)) / span
        flat_ear = (quad.normal.dot(normal) >= .99
                    and triangle.normal.dot(normal) <= -.9 and depth <= .05)
        # A twisted quad can have a misleading averaged face normal. Test its
        # two tip-diagonal triangles: both must oppose the closing triangle,
        # while their own normals diverge strongly. This is separate from the
        # nearly coplanar ear rule; do not loosen that rule's thresholds.
        corners = list(quad.verts)
        start = corners.index(tip)
        corners = corners[start:] + corners[:start]
        p, q, r, s = (v.co for v in corners)
        n1, n2 = (q - p).cross(r - p), (r - p).cross(s - p)
        twisted_ear = False
        if n1.length > tolerance ** 2 and n2.length > tolerance ** 2:
            n1.normalize()
            n2.normalize()
            twisted_ear = (depth <= .1 and quad.normal.dot(normal) >= .5
                           and triangle.normal.dot(normal) <= -.2
                           and triangle.normal.dot(quad.normal) <= -.9
                           and n1.dot(n2) <= .25
                           and max(n1.dot(triangle.normal), n2.dot(triangle.normal)) <= -.5)
            # A crossed quad can average to the SAME normal as its closing
            # triangle, even though one tip-diagonal subtriangle is reversed.
            # Require the degree-two tip to project outside the outer triangle.
            ab, ac, ap = b - a, c - a, tip.co - a
            denominator = ab.length_squared * ac.length_squared - ab.dot(ac) ** 2
            if denominator > tolerance ** 4:
                u = (ap.dot(ab) * ac.length_squared - ap.dot(ac) * ab.dot(ac)) / denominator
                v = (ap.dot(ac) * ab.length_squared - ap.dot(ab) * ab.dot(ac)) / denominator
                crossed_ear = (depth <= .05 and min(1-u-v, u, v) < -.05
                               and triangle.normal.dot(normal) >= .9
                               and quad.normal.dot(normal) >= .9 and n1.dot(n2) <= -.5
                               and min(n1.dot(triangle.normal), n2.dot(triangle.normal)) <= -.7
                               and max(n1.dot(triangle.normal), n2.dot(triangle.normal)) >= .9)
        if not (flat_ear or twisted_ear or crossed_ear):
            return None
        base = [v for v in triangle.verts if v != tip]
        opposite = next(v for v in verts if v not in base)
        direction = base[1].co - base[0].co
        side = direction.cross(tip.co - base[0].co).dot(
            direction.cross(opposite.co - base[0].co))
        if (crossed_ear and side <= 0) or (not crossed_ear and side >= 0):
            return None
        ear_sources = {layer: {l.vert: l for l in quad.loops if l.vert in verts}
                       for layer in layers}
    # A real fold reverses part of its patch; protect ordinary curved surfaces.
    if not crossed_ear and not any(f.normal.dot(normal) < -0.2 for f in patch if f.calc_area() > tolerance ** 2):
        return None
    outside = {f for e in boundary for f in e.link_faces if f not in patch}
    if crossed_ear and any(f.normal.dot(normal) <= .5 for f in outside):
        return None
    # No new flipped or nearly perpendicular boundary joins.
    if not backtracking_ear and any(f.normal.dot(normal) <= 0.05 for f in outside):
        return None
    uv_sources = ear_sources if backtracking_ear else _uv_boundary(patch, boundary, layers)
    if uv_sources is None:
        return None
    for layer in layers:
        points = [uv_sources[layer][v][layer].uv for v in ordered]
        if not all(math.isfinite(x) for p in points for x in p):
            return None
        x, y = points[1] - points[0], points[2] - points[0]
        if abs(x.x * y.y - x.y * y.x) < 1e-16:
            return None
    return patch, boundary, internal, interior_verts, ordered, uv_sources


def _collapse_candidates(bm, tolerance, selected_only, preserve_seams=False):
    pin = bm.edges.layers.int.get('polygroups_pin_edge')
    layers = list(bm.loops.layers.uv.values())
    for edge in bm.edges:
        if (not edge.is_manifold or (edge.seam and not preserve_seams) or edge.calc_length() > tolerance
                or any(not _visible(f) for f in edge.link_faces)):
            continue
        faces = [f for f in edge.link_faces if len(f.verts) == 3
                 and f.calc_area() <= tolerance * max(e.calc_length() for e in f.edges)]
        if not faces or (selected_only and not any(f.select for f in faces)):
            continue
        a, b = edge.verts
        touched = set(a.link_faces) | set(b.link_faces)
        if (any(not _visible(f) for f in touched)
                or any(l[layer].pin_uv for f in touched for l in f.loops for layer in layers)
                or (not preserve_seams and pin is not None and
                    any(e[pin] for v in (a, b) for e in v.link_edges))):
            continue
        if any(not e.is_manifold for v in (a, b) for e in v.link_edges):
            continue
        # Link condition for a manifold edge contraction: no extra shared neighbors.
        na = {e.other_vert(a) for e in a.link_edges} - {b}
        nb = {e.other_vert(b) for e in b.link_edges} - {a}
        expected = {v for f in edge.link_faces if len(f.verts) == 3
                    for v in f.verts if v not in (a, b)}
        if na & nb != expected:
            continue
        if not preserve_seams and any((next(e for e in a.link_edges if e.other_vert(a) == v).seam,
                next(e for e in a.link_edges if e.other_vert(a) == v).smooth) !=
               (next(e for e in b.link_edges if e.other_vert(b) == v).seam,
                next(e for e in b.link_edges if e.other_vert(b) == v).smooth)
               for v in expected):
            continue
        yield edge, faces


def _mark_uv_cuts(boundary, layers):
    for edge in boundary:
        for layer in layers:
            for vert in edge.verts:
                corners = [next(l for l in f.loops if l.vert == vert)
                           for f in edge.link_faces]
                if (corners[0][layer].uv - corners[1][layer].uv).length > 1e-6:
                    edge.seam = True


def _merge_backtracking_tip(bm, patch, interior, boundary, layers):
    """Directed weld: never average or move the surviving neighboring vertices."""
    tip = next(iter(interior))
    target = min((e.other_vert(tip) for e in tip.link_edges),
                 key=lambda v: ((v.co - tip.co).length_squared, v.index))
    quad = next(f for f in patch if len(f.verts) == 4)
    # Reconstruct only the surviving triangle's UVs. Anchor its longest uncut
    # boundary to its neighbor and unfold the third corner isometrically.
    # The folded quad's old UVs may themselves be severely stretched.
    base = max(boundary, key=lambda e: (not e.seam, e.calc_length()))
    a, b = base.verts
    c = next(v for e in boundary for v in e.verts if v not in (a, b))
    axis = b.co - a.co
    length = axis.length
    x = (c.co - a.co).dot(axis) / length
    height = axis.cross(c.co - a.co).length / length
    uv_layout = {}
    for layer in layers:
        source = (quad if base.seam else
                  next(f for f in base.link_faces if f not in patch))
        ua, ub = [next(l[layer].uv.copy() for l in source.loops if l.vert == v)
                  for v in (a, b)]
        old = {l.vert: l[layer].uv.copy() for l in quad.loops}
        u, v = old[b] - old[a], old[c] - old[a]
        sign = 1 if u.x * v.y - u.y * v.x >= 0 else -1
        direction = ub - ua
        if source != quad:
            other = [l[layer].uv for l in source.loops if l.vert not in (a, b)]
            reference = sum(other, Vector((0, 0))) / len(other) - ua
            side = direction.x * reference.y - direction.y * reference.x
            if abs(side) > 1e-16:
                sign = -1 if side > 0 else 1
        if direction.length < 1e-12:
            raise ValueError('Cannot unfold a tip onto a collapsed UV boundary')
        perpendicular = Vector((-direction.y, direction.x))
        uv_layout[layer] = {a: ua, b: ub,
                            c: ua + direction * (x / length) + perpendicular * (sign * height / length)}
    attributes = [attribute for kind in
                  ('float', 'int', 'string', 'color', 'float_color', 'float_vector')
                  for attribute in getattr(bm.loops.layers, kind).values()]
    corners = {}
    for loop in quad.loops:
        if loop.vert == tip:
            continue
        corners[loop.vert] = (
            [(layer, uv_layout[layer][loop.vert], loop[layer].pin_uv) for layer in layers],
            [(attribute, loop[attribute].copy() if hasattr(loop[attribute], 'copy')
              else loop[attribute]) for attribute in attributes])
    flags = [(edge, edge.seam, edge.smooth) for edge in boundary]
    bmesh.ops.weld_verts(bm, targetmap={tip: target})
    if not quad.is_valid or len(quad.verts) != 3:
        raise ValueError('Tip merge did not retain the surrounding face')
    for loop in quad.loops:
        uvs, custom = corners[loop.vert]
        for layer, uv, pinned in uvs:
            loop[layer].uv, loop[layer].pin_uv = uv, pinned
        for attribute, value in custom:
            loop[attribute] = value
    for edge, seam, smooth in flags:
        edge.seam, edge.smooth = seam, smooth
    _mark_uv_cuts(boundary, layers)
    quad.select_set(True)
    bm.faces.active = quad
    bm.normal_update()


def _uv_face_area(face, layer):
    points = [loop[layer].uv for loop in face.loops]
    return abs(sum(a.x*b.y-a.y*b.x for a,b in zip(points, points[1:]+points[:1]))) * .5


def _uv_cut(edge, face, layer):
    if edge.seam:
        return True
    outside = next(other for other in edge.link_faces if other != face)
    return any((next(loop[layer].uv for loop in face.loops if loop.vert == vertex)
                - next(loop[layer].uv for loop in outside.loops if loop.vert == vertex)).length > 1e-6
               for vertex in edge.verts)


def _triangle_uv_anisotropy(face, layer):
    a,b,c = [vertex.co for vertex in face.verts]
    x,y = b-a,c-a
    cross = x.cross(y).length
    if x.length == 0 or cross == 0:
        return math.inf
    points = [loop[layer].uv for loop in face.loops]
    u,v = points[1]-points[0],points[2]-points[0]
    j1 = u / x.length
    j2 = (v-j1*(x.dot(y)/x.length))/(cross/x.length)
    trace = j1.length_squared+j2.length_squared
    det = abs(j1.x*j2.y-j1.y*j2.x)
    return ((trace+math.sqrt(max(0,trace*trace-4*det*det)))*.5/det
            if det else math.inf)


def _stretched_single_triangle_plan(face, layers, tolerance, ratio, pin=None):
    """A single-face UV island with an extreme local scale/stretch outlier.

    Prove the entire contracted vertex fan stays closed and faces retain their
    orientation before moving the triangle's three vertices to its center.
    """
    if len(face.verts) != 3 or not layers or not _visible(face):
        return None
    vertices = set(face.verts)
    if any(not edge.is_manifold for vertex in vertices for edge in vertex.link_edges):
        return None
    neighbors = {other for edge in face.edges for other in edge.link_faces if other != face}
    if len(neighbors) != 3 or any(len(other.verts) == 3 for other in neighbors):
        return None  # The fold rules handle triangle/quad ears first.
    touched = {other for vertex in vertices for other in vertex.link_faces}
    if (any(not _visible(other) for other in touched)
            or any(not edge.is_manifold for other in touched for edge in other.edges)
            or any(loop[layer].pin_uv for other in touched for loop in other.loops for layer in layers)
            or (pin is not None and any(edge[pin] for vertex in vertices for edge in vertex.link_edges))):
        return None
    area = (face.verts[1].co-face.verts[0].co).cross(face.verts[2].co-face.verts[0].co).length * .5
    if area <= tolerance*tolerance:
        return None
    severe = False
    for layer in layers:
        if not all(_uv_cut(edge, face, layer) for edge in face.edges):
            continue
        density = _uv_face_area(face, layer) / area
        references = [_uv_face_area(other, layer)/other.calc_area() for other in neighbors
                      if other.calc_area() > tolerance*tolerance and _uv_face_area(other, layer) > 1e-16]
        if len(references) != 3 or not math.isfinite(density) or density <= 0:
            continue
        # Compare linear texel scale, not just triangle shape. A nearly
        # equilateral but enormously enlarged UV island is also an outlier.
        if (math.sqrt(density/median(references)) >= ratio
                or _triangle_uv_anisotropy(face, layer) >= ratio):
            severe = True
            break
    if not severe:
        return None
    center = sum((vertex.co for vertex in sorted(vertices,key=lambda v:v.index)), Vector((0,0,0))) / 3
    target = min(vertices, key=lambda vertex:vertex.index)
    sentinel = target
    face_keys, spokes = set(), {}
    surviving = touched - {face}
    for other in surviving:
        mapped = [sentinel if vertex in vertices else vertex for vertex in other.verts]
        compact = [vertex for index,vertex in enumerate(mapped) if vertex != mapped[index-1]]
        if len(compact) < 3 or len(set(compact)) != len(compact):
            return None
        key = frozenset(compact)
        if key in face_keys:
            return None
        face_keys.add(key)
        positions = [center if vertex == sentinel else vertex.co for vertex in compact]
        origin = positions[0]
        normal = sum(((a-origin).cross(b-origin) for a,b in zip(positions, positions[1:]+positions[:1])), Vector((0,0,0)))
        if normal.length <= tolerance*tolerance or normal.normalized().dot(other.normal) <= .2:
            return None
        triangles = [[positions[item] if isinstance(item,int) else item for item in triangle]
                     for triangle in tessellate_polygon([positions])]
        if not triangles or any((b-a).cross(c-a).length <= tolerance*tolerance
                or (b-a).cross(c-a).normalized().dot(other.normal) <= .05 for a,b,c in triangles):
            return None
        index = compact.index(sentinel)
        for vertex in (compact[index-1], compact[(index+1)%len(compact)]):
            spokes.setdefault(vertex, []).append(other)
    if any(len(faces) != 2 for faces in spokes.values()):
        return None
    # One connected fan avoids creating a bow-tie/non-manifold vertex.
    pending = [next(iter(surviving))]
    visited = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(other for faces in spokes.values() if current in faces for other in faces)
    if visited != surviving:
        return None
    return vertices, target, center, surviving


def _merge_triangle_center(bm, plan, layers):
    vertices, target, center, surviving = plan
    pin = bm.edges.layers.int.get('polygroups_pin_edge')
    flags = {}
    for vertex in vertices:
        for edge in vertex.link_edges:
            other = edge.other_vert(vertex)
            if other in vertices:
                continue
            seam,sharp,pinned = flags.get(other, (False,False,False))
            flags[other] = (seam or edge.seam, sharp or not edge.smooth,
                            pinned or (pin is not None and bool(edge[pin])))
    layouts = {}
    for face in surviving:
        layouts[face] = {}
        for layer in layers:
            merged = [loop[layer].uv.copy() for loop in face.loops if loop.vert in vertices]
            layouts[face][layer] = {loop.vert:loop[layer].uv.copy() for loop in face.loops
                                    if loop.vert not in vertices}
            layouts[face][layer][target] = sum(merged, Vector((0,0))) / len(merged)
    bmesh.ops.weld_verts(bm, targetmap={vertex:target for vertex in vertices if vertex != target})
    target.co = center
    for face,uvs in layouts.items():
        if not face.is_valid:
            raise ValueError('Triangle center merge would remove an adjacent face')
        for loop in face.loops:
            for layer in layers:
                loop[layer].uv = uvs[layer][loop.vert]
    for edge in target.link_edges:
        seam,sharp,pinned = flags[edge.other_vert(target)]
        edge.seam,edge.smooth = seam,not sharp
        if pin is not None:
            edge[pin] = int(pinned)
    if any(not edge.is_manifold for edge in target.link_edges):
        raise ValueError('Triangle center merge would open the local surface')
    _mark_uv_cuts(target.link_edges, layers)
    target.select_set(True)
    bm.normal_update()


def repair_local_folds(bm, fix_folds=True, fix_degenerate=True,
                       selected_only=False, relative_tolerance=1e-7,
                       fix_zero_area=False, fix_stretched_triangles=False,
                       stretched_triangle_ratio=50.0, fix_dangling=False):
    """Mutate a working BMesh. Caller commits only after successful validation.

    Return original face indices for inspection, plus repair/remaining counts.
    No fixed asset indices, axes, UV positions, or absolute mesh scale are used.
    """
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
    bm.normal_update()
    layers = list(bm.loops.layers.uv.values())
    if not bm.verts:
        return dict(folds=0, collapsed=0, affected=set(), remaining_degenerate=0)
    lo = Vector(tuple(min(v.co[i] for v in bm.verts) for i in range(3)))
    hi = Vector(tuple(max(v.co[i] for v in bm.verts) for i in range(3)))
    tolerance = max((hi - lo).length * relative_tolerance, 1e-15)
    ids = {f: f.index for f in bm.faces}
    seeded = {f for f in bm.faces if f.select}
    original_triangles = [f for f in bm.faces if len(f.verts) == 3]
    pin = bm.edges.layers.int.get('polygroups_pin_edge')
    affected = set()
    collapsed = folds = 0
    invalid_edges_before = sum(not e.is_manifold for e in bm.edges)
    seam_collapsed = 0
    stretched = 0
    dangling = {}
    if fix_degenerate or fix_zero_area:
        # Rebuild the candidate list after each weld; BMesh may invalidate edges.
        while True:
            candidate = (next(iter(_collapse_candidates(bm, tolerance, selected_only)), None)
                         if fix_degenerate else None)
            if candidate is None and fix_zero_area:
                candidate = next(((e, fs) for e, fs in _collapse_candidates(
                    bm, tolerance, selected_only, preserve_seams=True)
                    if e.calc_length() == 0.0), None)
            if candidate is None:
                break
            edge, faces = candidate
            a, b = sorted(edge.verts, key=lambda v: v.index)
            touched = set(a.link_faces) | set(b.link_faces)
            # Duplicated sides can disagree on seam/sharp flags. Union seams and
            # sharpness instead of letting BMesh choose one side arbitrarily.
            edge_flags = {}
            for v in (a, b):
                for linked in v.link_edges:
                    other = linked.other_vert(v)
                    if other in (a, b):
                        continue
                    seam, sharp, pinned = edge_flags.get(other, (False, False, False))
                    edge_flags[other] = (seam or linked.seam, sharp or not linked.smooth,
                                         pinned or (pin is not None and bool(linked[pin])))
            if fix_zero_area and any(e.seam for v in (a, b) for e in v.link_edges):
                seam_collapsed += 1
            seeded.update(touched)
            affected.update(ids[f] for f in faces if f in ids)
            bmesh.ops.weld_verts(bm, targetmap={b: a})
            for linked in a.link_edges:
                other = linked.other_vert(a)
                if other in edge_flags:
                    linked.seam, sharp, pinned = edge_flags[other]
                    linked.smooth = not sharp
                    if pin is not None:
                        linked[pin] = int(pinned)
            bm.normal_update()
            collapsed += 1
    if fix_folds:
        while True:
            planned = None
            checked = set()
            for face in bm.faces:
                neighbors = {f for e in face.edges for f in e.link_faces if f != face}
                for other in neighbors:
                    pair = frozenset((face, other))
                    if pair in checked:
                        continue
                    checked.add(pair)
                    if len(set(face.edges) & set(other.edges)) < 2:
                        continue
                    if selected_only and not any(f in seeded for f in pair):
                        continue
                    planned = _plan(pair, layers, tolerance, backtracking_ear=True)
                    ear_merge = planned is not None
                    if planned is None:
                        planned = _plan(pair, layers, tolerance)
                    if planned and pin and any(e[pin] for e in planned[2]):
                        planned = None
                    if planned:
                        break
                if planned:
                    break
            if not planned:
                break
            patch, boundary, internal, interior, ordered, sources = planned
            affected.update(ids[f] for f in patch if f in ids)
            if ear_merge:
                _merge_backtracking_tip(bm, patch, interior, boundary, layers)
                if any(not e.is_manifold for e in boundary):
                    raise ValueError('Tip merge would open the patch boundary')
                folds += 1
                continue
            # Create before deleting to copy all face/corner custom data safely.
            anchor = max(patch, key=lambda f: f.calc_area())
            new = bm.faces.new(ordered, anchor)
            for loop in new.loops:
                corner = (sources[layers[0]][loop.vert] if layers else
                          next(l for f in patch for l in f.loops if l.vert == loop.vert))
                for kind in ('float', 'int', 'string', 'color', 'float_color', 'float_vector'):
                    for attribute in getattr(bm.loops.layers, kind).values():
                        loop[attribute] = corner[attribute]
                for layer in layers:
                    loop[layer].uv = sources[layer][loop.vert][layer].uv
                    loop[layer].pin_uv = sources[layer][loop.vert][layer].pin_uv
            bmesh.ops.delete(bm, geom=list(patch), context='FACES_ONLY')
            loose = [e for e in internal if e.is_valid and not e.link_faces]
            if loose:
                bmesh.ops.delete(bm, geom=loose, context='EDGES')
            loose = [v for v in interior if v.is_valid and not v.link_edges]
            if loose:
                bmesh.ops.delete(bm, geom=loose, context='VERTS')
            new.select_set(True)
            # A pre-existing unmarked UV cut must remain a cut after repair.
            # Reconcile only this patch boundary; leave other islands untouched.
            _mark_uv_cuts(boundary, layers)
            bm.faces.active = new
            bm.normal_update()
            if any(not e.is_manifold for e in boundary):
                raise ValueError('Repair would open the patch boundary')
            folds += 1
    # Preserve the established exact-weld and small-pocket transforms before
    # the general region cleaner; they can also expose a previously blocked neck.
    if fix_dangling:
        from .dangling_repair import repair_dangling
        dangling = repair_dangling(bm, selected_only)
        affected.update(dangling.pop('affected'))
    if fix_stretched_triangles:
        for face in original_triangles:
            if not face.is_valid or (selected_only and face not in seeded):
                continue
            planned = _stretched_single_triangle_plan(face, layers, tolerance, stretched_triangle_ratio, pin)
            if planned is None:
                continue
            affected.add(ids[face])
            _merge_triangle_center(bm, planned, layers)
            stretched += 1
    areas = dict.fromkeys(bm.faces, 0.0)
    zero_triangles = 0
    for a, b, c in bm.calc_loop_triangles():
        area = (b.vert.co - a.vert.co).cross(c.vert.co - a.vert.co).length * .5
        areas[a.face] += area
        if area == 0.0 and _visible(a.face):
            zero_triangles += 1
    remaining = [f for f, area in areas.items() if _visible(f) and area <= tolerance * tolerance]
    if sum(not e.is_manifold for e in bm.edges) > invalid_edges_before:
        raise ValueError('Repair would create non-manifold or open edges')
    return dict(folds=folds, collapsed=collapsed, affected=affected,
                stretched=stretched,
                remaining_degenerate=len(remaining), remaining_zero_triangles=zero_triangles,
                seam_collapsed=seam_collapsed, **dangling)
