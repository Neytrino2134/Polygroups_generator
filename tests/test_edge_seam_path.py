"""Run in Blender background with --factory-startup --python-exit-code 1."""
import math
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.edge_seam_path import find_edge_path
from polygroups_generator.operators.connect_vertex_seam import select_vertices


def grid(width, height, curved=False):
    bm = bmesh.new()
    for y in range(height):
        for x in range(width):
            co = (4 * math.cos(x * 0.3), 4 * math.sin(x * 0.3), y) if curved else (x, y, 0)
            bm.verts.new(co)
    bm.verts.ensure_lookup_table()
    for y in range(height - 1):
        for x in range(width - 1):
            i = y * width + x
            bm.faces.new([bm.verts[j] for j in (i, i + 1, i + width + 1, i + width)])
    bm.normal_update()
    return bm


def walk(start, route):
    vertices = [start]
    for edge in route:
        assert vertices[-1] in edge.verts
        vertices.append(edge.other_vert(vertices[-1]))
    assert len(set(vertices)) == len(vertices), "Route contains a loop"
    return vertices


def turns(vertices, width):
    directions = [b.index - a.index for a, b in zip(vertices, vertices[1:])]
    assert all(abs(d) in {1, width} for d in directions)
    return sum(a != b for a, b in zip(directions, directions[1:]))


for curved in (False, True):
    bm = grid(12, 12, curved)
    a, b = bm.verts[13], bm.verts[130]
    for matrix in (Matrix.Identity(4), Matrix.Diagonal((2, 0.7, 3, 1))):
        route = find_edge_path(bm, a, b, matrix)
        vertices = walk(a, route)
        assert vertices[-1] == b and len(route) == 18
        assert turns(vertices, 12) == 1, "Grid path must make one turn, not stairs"
        reverse = walk(b, find_edge_path(bm, b, a, matrix))
        assert reverse[-1] == a and turns(reverse, 12) == 1
    bm.free()

# Hidden barrier requires a detour with two turns; it must not cross hidden edges.
bm = grid(10, 10)
for edge in bm.edges:
    if {int(v.co.x) for v in edge.verts} == {4, 5} and edge.verts[0].co.y < 8:
        edge.hide_set(True)
a, b = bm.verts[21], bm.verts[28]
route = find_edge_path(bm, a, b, Matrix.Identity(4))
assert route and not any(e.hide for e in route)
assert walk(a, route)[-1] == b
assert turns(walk(a, route), 10) == 2
bm.free()

# Geometric fallback on a triangle mesh must also prefer continuous runs.
bm = grid(9, 9)
bmesh.ops.triangulate(bm, faces=list(bm.faces))
a, b = bm.verts[0], bm.verts[44]
route = find_edge_path(bm, a, b, Matrix.Identity(4))
vertices = walk(a, route)
assert vertices[-1] == b
directions = [(v.co - u.co).normalized() for u, v in zip(vertices, vertices[1:])]
assert sum(a.dot(b) < 0.95 for a, b in zip(directions, directions[1:])) <= 2
bm.free()

# Integration: mark/selection, preservation of topology and existing seams,
# unsuccessful requests, and disconnected islands in the same object.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new("EdgePathGrid")
bm = grid(8, 8)
bm.verts.new((20, 20, 0))
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("EdgePathGrid", mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="VERT")
bm = bmesh.from_edit_mesh(mesh)
bm.verts.ensure_lookup_table()
before = (len(bm.verts), len(bm.edges), len(bm.faces))
coordinates = [tuple(v.co) for v in bm.verts]
existing = bm.edges.get((bm.verts[0], bm.verts[1]))
existing.seam = True
a, b = bm.verts[9], bm.verts[54]
select_vertices([(obj, bm)], [(obj, a), (obj, b)])
assert bpy.ops.mesh.polygroups_edge_seam_path() == {"FINISHED"}
path = [e for e in bm.edges if e.select]
assert len(path) == 10 and all(e.seam for e in path)
assert existing.seam and not existing.select
assert not any(face.select for face in bm.faces)
assert tuple(bpy.context.tool_settings.mesh_select_mode) == (False, True, False)
assert before == (len(bm.verts), len(bm.edges), len(bm.faces))
assert coordinates == [tuple(v.co) for v in bm.verts]

for endpoints in ([a], [a, bm.verts[64]]):
    bpy.ops.mesh.select_mode(type="VERT")
    select_vertices([(obj, bm)], [(obj, v) for v in endpoints])
    flags = [(e.seam, e.select) for e in bm.edges]
    assert bpy.ops.mesh.polygroups_edge_seam_path() == {"CANCELLED"}
    assert flags == [(e.seam, e.select) for e in bm.edges]
    assert set(v for v in bm.verts if v.select) == set(endpoints)

bpy.ops.object.mode_set(mode="OBJECT")
addon_utils.disable(ROOT.name, default_set=True)
print("EDGE_SEAM_PATH_TESTS_PASSED")
