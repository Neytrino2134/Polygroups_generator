"""Mesh knots: tiny tangles of faces that no seam can unwrap cleanly.

Two kinds are found, then grown into one face cluster each:

- Folded faces: a face whose normal points against the area-weighted normal of its
  1-ring lies folded over its neighbours (generated retopo leaves these at vertices
  that nearly merged).
- Pinched cones: a hole whose rim was welded to one nearby vertex. That vertex has
  two face fans; the small one is a closed cone.

Faces overlapping a knot face (three shared vertices) and sliver faces touching it
join the knot. A knot small enough is collapsed into one point; a collapse that
would leave the mesh non-manifold is skipped.
"""
import bmesh


FOLD_DOT = -0.2       # face normal vs 1-ring normal
SLIVER_AREA = 0.1     # share of the median face area


def vertex_fans(vert):
    """Face groups around ``vert`` joined through manifold spoke edges."""
    around = set(vert.link_faces)
    fans, seen = [], set()
    for start in vert.link_faces:
        if start in seen:
            continue
        fan, stack = {start}, [start]
        seen.add(start)
        while stack:
            for edge in stack.pop().edges:
                if vert not in edge.verts or len(edge.link_faces) != 2:
                    continue
                for other in edge.link_faces:
                    if other in around and other not in seen:
                        seen.add(other)
                        fan.add(other)
                        stack.append(other)
        fans.append(fan)
    return fans


def _pinch_cones(verts, max_verts):
    cones = []
    for vert in verts:
        if vert.is_manifold or vert.is_boundary:
            continue
        # Edges shared by 3+ faces are real non-manifold joins, not a welded hole.
        if any(len(e.link_faces) != 2 for e in vert.link_edges):
            continue
        # The surface keeps its widest fan; the welded cone is the small one.
        fans = sorted(vertex_fans(vert), key=lambda fan: sum(f.calc_area() for f in fan))
        for fan in fans[:-1]:
            spokes = {e for f in fan for e in f.edges if vert in e.verts}
            if len(spokes) < max_verts and all(
                    sum(f in fan for f in e.link_faces) == 2 for e in spokes):
                cones.append(fan)
    return cones


def _folded(face):
    ring = {g for v in face.verts for g in v.link_faces} - {face}
    normal = face.normal * 0.0
    for other in ring:
        normal += other.normal * other.calc_area()
    return normal.length > 1e-20 and face.normal.dot(normal.normalized()) < FOLD_DOT


def find_knots(bm, faces=None, max_verts=8):
    """[set(faces)] knots in ``faces`` (default: visible faces) with <= ``max_verts`` vertices."""
    pool = set(faces) if faces is not None else {f for f in bm.faces if not f.hide}
    if not pool:
        return []
    areas = sorted(f.calc_area() for f in pool)
    sliver = areas[len(areas) // 2] * SLIVER_AREA
    seeds = {f for f in pool if _folded(f)}
    for cone in _pinch_cones({v for f in pool for v in f.verts}, max_verts):
        seeds |= cone
    knots, left = [], set(seeds)
    while left:
        start = left.pop()
        knot, stack = {start}, [start]
        while stack:
            face = stack.pop()
            for vert in face.verts:
                for other in vert.link_faces:
                    if other in knot or other not in pool:
                        continue
                    join = other in left or other.calc_area() < sliver or \
                        len(set(other.verts) & set(face.verts)) >= 3
                    if join:
                        left.discard(other)
                        knot.add(other)
                        stack.append(other)
            if len(knot) > max_verts * 2:
                break
        verts = {v for f in knot for v in f.verts}
        if len(verts) > max_verts:
            continue
        if any(v.is_boundary for v in verts):
            continue
        knots.append(knot)
    return knots


def _local_ok(vert):
    """Manifold, closed surface around the merged point."""
    if vert is None or not vert.is_valid or not vert.is_manifold:
        return False
    near = {v for e in vert.link_edges for v in e.verts}
    return all(len(e.link_faces) == 2 for v in near for e in v.link_edges)


def _merge(bm, points, center):
    bmesh.ops.pointmerge(bm, verts=points, merge_co=center)
    survivor = next((v for v in points if v.is_valid), None)
    if survivor is None:
        return None
    nearby = {e for f in survivor.link_faces for e in f.edges} | set(survivor.link_edges)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-9, edges=list(nearby))
    return survivor if survivor.is_valid else None


def _collapse(bm, indices, max_verts):
    """Merge verts ``indices`` at their center; pull in joints stacked on one edge."""
    bm.verts.ensure_lookup_table()
    points = [bm.verts[i] for i in indices]
    center = sum((v.co for v in points), points[0].co * 0.0) / len(points)
    survivor = _merge(bm, points, center)
    # Faces that shared the knot rim with the outer surface may now stack on one
    # edge; pull that edge in too, so the knot ends as one manifold point.
    for _step in range(max_verts):
        if survivor is None:
            break
        joint = next((e for e in survivor.link_edges if len(e.link_faces) > 2), None)
        if joint is None:
            break
        survivor = _merge(bm, list(joint.verts), survivor.co.copy())
    return survivor


def collapse_knots(bm, faces=None, max_verts=8, limit=100):
    """Collapse every knot into one point. Returns the merged positions."""
    merged, skipped = [], set()
    pool = set(faces) if faces is not None else None
    for _ in range(limit):
        if pool is not None:
            pool = {f for f in pool if f.is_valid}
        bm.verts.index_update()
        knots = [k for k in find_knots(bm, pool, max_verts)
                 if frozenset(v.co.to_tuple(6) for f in k for v in f.verts) not in skipped]
        if not knots:
            break
        knot = knots[0]
        indices = sorted({v.index for f in knot for v in f.verts})
        # Dry run on a copy: never leave a worse mesh than the knot itself.
        trial = bm.copy()
        ok = _local_ok(_collapse(trial, indices, max_verts))
        trial.free()
        if not ok:
            skipped.add(frozenset(v.co.to_tuple(6) for f in knot for v in f.verts))
            continue
        survivor = _collapse(bm, indices, max_verts)
        if pool is not None:
            pool.update(survivor.link_faces)
        merged.append(survivor.co.copy())
    return merged
