"""Collapsing fixes weld into a vertex that keeps the surface, not into the group's average position."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core.merge_target import best_vertex, plane_error

# A flat 4x4 grid in Z=0 with one raised spike next to a flat vertex.
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=2.0)
bm.verts.ensure_lookup_table()
flat = min(bm.verts, key=lambda v: (v.co - Vector((0.0, 0.0, 0.0))).length)
neighbor = next(e.other_vert(flat) for e in flat.link_edges)
neighbor.co.z = 0.4
bm.normal_update()
group = [flat, neighbor]
faces = {f for v in group for f in v.link_faces}
chosen = best_vertex(group)
# The target is one of the group's own vertices and has the lowest plane error of them.
assert chosen in group
assert plane_error(chosen.co, faces) == min(plane_error(v.co, faces) for v in group)
# Faces entirely inside the group are the collapsed ones and do not count.
inside = {f for f in chosen.link_faces if all(v in set(chosen.link_faces[0].verts) for v in f.verts)}
assert best_vertex(list(chosen.link_faces[0].verts), removed=inside) in chosen.link_faces[0].verts
bm.free()
print('smart weld target ok')