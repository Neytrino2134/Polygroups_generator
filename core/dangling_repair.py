"""Conservative removal of attached open sheets and collapsed folded tails.

Plans refer to original BMesh elements, so Find Problems can use the same rule.
Only the triangular neck of an accepted folded tail is filled and triangulated.
"""
import math

import bmesh


def repair_dangling(bm, selected_only=False):
    from .mesh_fold_repair import _boundary, _visible, _uv_boundary, _mark_uv_cuts

    layers = list(bm.loops.layers.uv.values())
    pin = bm.edges.layers.int.get('polygroups_pin_edge')
    affected, removed_faces = set(), 0
    removed_edges = removed_verts = filled = 0
    selected = {f for f in bm.faces if f.select}
    original_verts = len(bm.verts)
    edge_ids = {e: e.index for e in bm.edges}
    vert_ids = {v: v.index for v in bm.verts}
    affected_edges, affected_verts = set(), set()

    def allowed(patch):
        return (all(_visible(f) for f in patch)
                and (not selected_only or bool(patch & selected))
                and not (pin and any(e[pin] for f in patch for e in f.edges))
                and not any(l[layer].pin_uv for f in patch for l in f.loops for layer in layers))

    def delete_patch(patch):
        nonlocal removed_faces, removed_edges, removed_verts
        edges = {e for f in patch for e in f.edges}
        verts = {v for f in patch for v in f.verts}
        affected_edges.update(edge_ids[e] for e in edges if e in edge_ids)
        affected_verts.update(vert_ids[v] for v in verts if v in vert_ids)
        affected.update(f.index for f in patch)
        removed_faces += len(patch)
        bmesh.ops.delete(bm, geom=list(patch), context='FACES_ONLY')
        loose = [e for e in edges if e.is_valid and not e.link_faces]
        removed_edges += len(loose)
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='EDGES')
        loose = [v for v in verts if v.is_valid and not v.link_edges]
        removed_verts += len(loose)
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')

    # A sheet attached to an otherwise two-sided surface through a 3+-face
    # edge encloses no volume. Split there, never across an ordinary join.
    unseen = set(bm.faces)
    components = []
    while unseen:
        face = unseen.pop()
        patch, todo = {face}, [face]
        while todo:
            for edge in todo.pop().edges:
                if len(edge.link_faces) != 2:
                    continue
                for neighbor in edge.link_faces:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        patch.add(neighbor)
                        todo.append(neighbor)
        components.append(patch)
    total_area = sum(f.calc_area() for f in bm.faces)
    for patch in sorted(components, key=len):
        if not all(f.is_valid for f in patch) or not allowed(patch):
            continue
        edges = {e for f in patch for e in f.edges}
        joins = {e for e in edges if any(f not in patch for f in e.link_faces)}
        if (not joins or not any(e.is_boundary for e in edges)
                or any(sum(f not in patch for f in e.link_faces) != 2 for e in joins)
                or sum(f.calc_area() for f in patch) > total_area * .01):
            continue
        delete_patch(patch)

    # A backtracking valence-two tip can grow into a long chain of folded
    # quads. Absorb faces sharing two boundary edges until its neck is reached.
    checked = set()
    for tip in list(bm.verts):
        if not tip.is_valid or len(tip.link_edges) != 2 or not tip.link_faces:
            continue
        patch = set(tip.link_faces)
        while len(patch) <= 128:
            boundary = _boundary(patch)
            add = {f for e in boundary for f in e.link_faces if f not in patch
                   and len(set(f.edges) & boundary) >= 2}
            if not add:
                break
            patch.update(add)
        key = frozenset(patch)
        if key in checked:
            continue
        checked.add(key)
        if len(patch) > 128 or not allowed(patch):
            continue
        edges = {e for f in patch for e in f.edges}
        boundary = _boundary(patch)
        corners = {v for e in boundary for v in e.verts}
        if (len(boundary) != 3 or len(corners) != 3
                or any(not e.is_manifold for e in edges)
                or any(e.seam for e in edges - boundary)
                or len({f.material_index for f in patch}) != 1):
            continue
        interior = {v for f in patch for v in f.verts} - corners
        if any(any(f not in patch for f in v.link_faces) for v in interior):
            continue
        edge = min(boundary, key=lambda e: e.index)
        loop = next(l for f in edge.link_faces if f in patch for l in f.loops if l.edge == edge)
        ordered = [loop.vert, loop.link_loop_next.vert]
        ordered.append(next(v for v in corners if v not in ordered))
        a, b, c = (v.co for v in ordered)
        normal = (b-a).cross(c-a)
        span = max((v.co-a).length for f in patch for v in f.verts)
        if normal.length <= span * span * 1e-12:
            continue
        normal.normalize()
        outside = {f for e in boundary for f in e.link_faces if f not in patch}
        if any(f.normal.dot(normal) <= .05 for f in outside):
            continue
        # Use a local origin for translation stability. Tiny signed volume alone
        # is insufficient: demand strong cancellation of oppositely folded faces.
        origin = (a+b+c)/3
        volume = absolute = area = 0.0
        for face in patch:
            points = [v.co-origin for v in face.verts]
            for i in range(1, len(points)-1):
                x, y, z = points[0], points[i], points[i+1]
                value = x.dot(y.cross(z))/6
                volume += value
                absolute += abs(value)
                area += (y-x).cross(z-x).length/2
        if (area == 0 or abs(volume) > area*span*.001
                or absolute > area*span*1e-6 and abs(volume) > absolute*.05
                or not any(f.normal.dot(normal) < -.2 for f in patch)):
            continue
        sources = _uv_boundary(patch, boundary, layers)
        if sources is None or any(not math.isfinite(x) for layer in layers
                                  for l in sources[layer].values() for x in l[layer].uv):
            continue
        anchor = max(patch, key=lambda f: f.calc_area())
        new = bm.faces.new(ordered, anchor)
        for l in new.loops:
            corner = next(old for old in anchor.loops if old.vert == l.vert) if l.vert in anchor.verts else next(
                old for f in patch for old in f.loops if old.vert == l.vert)
            for kind in ('float', 'int', 'string', 'color', 'float_color', 'float_vector'):
                for attribute in getattr(bm.loops.layers, kind).values():
                    l[attribute] = corner[attribute]
            for layer in layers:
                l[layer].uv = sources[layer][l.vert][layer].uv
                l[layer].pin_uv = sources[layer][l.vert][layer].pin_uv
        delete_patch(patch)
        bmesh.ops.triangulate(bm, faces=[new])
        _mark_uv_cuts(boundary, layers)
        filled += 1
        if any(not e.is_manifold for e in boundary):
            raise ValueError('Dangling repair would open the patch neck')
        bm.normal_update()

    # Remove wire debris as well, including debris already present in LODs.
    loose = [e for e in bm.edges if not e.link_faces and not e.hide
             and not any(v.hide for v in e.verts)
             and (not selected_only or e.select) and not (pin and e[pin])]
    removed_edges += len(loose)
    affected_edges.update(edge_ids[e] for e in loose if e in edge_ids)
    affected_verts.update(vert_ids[v] for e in loose for v in e.verts if v in vert_ids)
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='EDGES')
    loose = [v for v in bm.verts if not v.link_edges and not v.hide
             and (not selected_only or v.select)]
    removed_verts += len(loose)
    affected_verts.update(vert_ids[v] for v in loose if v in vert_ids)
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.normal_update()
    return dict(affected=affected, dangling_faces=removed_faces,
                affected_edges=affected_edges, affected_verts=affected_verts,
                dangling_edges=removed_edges, dangling_verts=original_verts-len(bm.verts), dangling_filled=filled)

