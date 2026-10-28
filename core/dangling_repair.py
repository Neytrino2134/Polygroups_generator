"""Conservative removal of attached open sheets and collapsed folded tails.

Plans refer to original BMesh elements, so Find Problems can use the same rule.
Only the validated polygonal neck of an accepted region is filled and triangulated.
"""
import math

import bmesh


def repair_dangling(bm, selected_only=False):
    from .mesh_fold_repair import _visible, _mark_uv_cuts

    layers = list(bm.loops.layers.uv.values())
    pin = bm.edges.layers.int.get('polygroups_pin_edge')
    affected, removed_faces = set(), 0
    removed_edges = filled = 0
    selected = {f for f in bm.faces if f.select}
    original_verts = len(bm.verts)
    edge_ids = {e: e.index for e in bm.edges if e.index >= 0}
    vert_ids = {v: v.index for v in bm.verts if v.index >= 0}
    affected_edges, affected_verts = set(), set()

    def allowed(patch):
        return (all(_visible(f) for f in patch)
                and (not selected_only or bool(patch & selected))
                and not (pin and any(e[pin] for f in patch for e in f.edges))
                and not any(l[layer].pin_uv for f in patch for l in f.loops for layer in layers))

    def delete_patch(patch):
        nonlocal removed_faces, removed_edges
        edges = {e for f in patch for e in f.edges}
        verts = {v for f in patch for v in f.verts}
        affected_edges.update(edge_ids[e] for e in edges if e in edge_ids)
        affected_verts.update(vert_ids[v] for v in verts if v in vert_ids)
        affected.update(f.index for f in patch if f.index >= 0)
        removed_faces += len(patch)
        bmesh.ops.delete(bm, geom=list(patch), context='FACES_ONLY')
        loose = [e for e in edges if e.is_valid and not e.link_faces]
        removed_edges += len(loose)
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='EDGES')
        loose = [v for v in verts if v.is_valid and not v.link_edges]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')

    from collections import defaultdict
    from .repair_regions import candidate_regions, folded_region_plan
    triangles = defaultdict(list)
    for triangle in bm.calc_loop_triangles():
        triangles[triangle[0].face].append(tuple(loop.vert for loop in triangle))
    for patch, boundary in candidate_regions(bm):
        if not all(face.is_valid for face in patch) or not allowed(patch):
            continue
        planned = folded_region_plan(patch, boundary, layers, triangles)
        if planned is None:
            continue
        ordered, sources, cap = planned
        if any(not math.isfinite(x) for layer in layers
               for loop in sources[layer].values() for x in loop[layer].uv):
            continue
        anchor = max(patch, key=lambda face: face.calc_area())
        new = cap if cap is not None else bm.faces.new(ordered, anchor)
        if cap is not None:
            affected.update(f.index for f in patch if f.index >= 0)
            loop = next(l for l in new.loops if l.vert == ordered[0])
            if loop.link_loop_next.vert != ordered[1]:
                new.normal_flip()
        for loop in new.loops:
            corner = next((old for old in anchor.loops if old.vert == loop.vert), None)
            if corner is None:
                corner = next(old for face in patch for old in face.loops if old.vert == loop.vert)
            for kind in ('float', 'int', 'string', 'color', 'float_color', 'float_vector'):
                for attribute in getattr(bm.loops.layers, kind).values():
                    loop[attribute] = corner[attribute]
            for layer in layers:
                loop[layer].uv = sources[layer][loop.vert][layer].uv
                loop[layer].pin_uv = sources[layer][loop.vert][layer].pin_uv
        delete_patch(patch-{new})
        bmesh.ops.triangulate(bm, faces=[new])
        _mark_uv_cuts(boundary, layers)
        filled += 1
        if any(not edge.is_manifold for edge in boundary):
            raise ValueError('Dangling repair would open the patch neck')
        bm.normal_update()

    # Classify full folded regions first: stripping individual non-manifold
    # sheets before that can destroy the region neck after triangulation.
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
                or sum(f.calc_area() for f in patch) >= total_area * .5):
            continue
        delete_patch(patch)

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
    affected_verts.update(vert_ids[v] for v in loose if v in vert_ids)
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.normal_update()
    return dict(affected=affected, dangling_faces=removed_faces,
                affected_edges=affected_edges, affected_verts=affected_verts,
                dangling_edges=removed_edges, dangling_verts=original_verts-len(bm.verts), dangling_filled=filled)

