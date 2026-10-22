"""Conservative local fold repair, preserving the surrounding mesh and UVs.

Only closed manifold pockets with a triangular outer boundary are replaced.
This is deliberately narrower than deleting thin faces or a global weld.
"""
import math

import bmesh
from mathutils import Vector


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
            inside = next(f for f in edge.link_faces if f in patch)
            outside = next(f for f in edge.link_faces if f not in patch)
            face = inside if edge.seam else outside
            priority = 1 if edge.seam else 2
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


def _plan(patch, layers, tolerance):
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
    # A real fold reverses part of its patch; protect ordinary curved surfaces.
    if not any(f.normal.dot(normal) < -0.2 for f in patch if f.calc_area() > tolerance ** 2):
        return None
    outside = {f for e in boundary for f in e.link_faces if f not in patch}
    # No new flipped or nearly perpendicular boundary joins.
    if any(f.normal.dot(normal) <= 0.05 for f in outside):
        return None
    uv_sources = _uv_boundary(patch, boundary, layers)
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


def repair_local_folds(bm, fix_folds=True, fix_degenerate=True,
                       selected_only=False, relative_tolerance=1e-7,
                       fix_zero_area=False):
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
    pin = bm.edges.layers.int.get('polygroups_pin_edge')
    affected = set()
    collapsed = folds = 0
    invalid_edges_before = sum(not e.is_manifold for e in bm.edges)
    seam_collapsed = 0
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
            bm.faces.active = new
            bm.normal_update()
            if any(not e.is_manifold for e in boundary):
                raise ValueError('Repair would open the patch boundary')
            folds += 1
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
                remaining_degenerate=len(remaining), remaining_zero_triangles=zero_triangles,
                seam_collapsed=seam_collapsed)
