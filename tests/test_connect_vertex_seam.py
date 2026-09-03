"""Run in Blender background with --factory-startup --python-exit-code 1."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators.connect_vertex_seam import select_vertices

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new("Strip")
mesh.from_pydata([(x, y, 0) for y in (0, 1) for x in (0, 1, 2)], [],
                 [(0, 1, 4, 3), (1, 2, 5, 4)])
obj = bpy.data.objects.new("Strip", mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="VERT")
bm = bmesh.from_edit_mesh(mesh)
bm.verts.ensure_lookup_table()
a, b = bm.verts[0], bm.verts[5]
select_vertices([(obj, bm)], [(obj, a), (obj, b)])
assert bpy.ops.mesh.polygroups_connect_vertex_seam() == {"FINISHED"}
# A diagonal across two faces inserts an intermediate vertex and two path edges.
assert len(bm.verts) == 7 and len(bm.faces) == 4
seams = [edge for edge in bm.edges if edge.seam]
assert len(seams) == 2
for edge in seams:
    assert all(abs(v.co.y - v.co.x / 2) < 1e-6 for v in edge.verts)
assert sum(edge.seam for edge in bm.edges if edge.is_boundary) == 0

# An existing edge gets marked without generating duplicate geometry.
edge = next(edge for edge in bm.edges if edge.is_boundary)
before = (len(bm.verts), len(bm.edges), len(bm.faces))
select_vertices([(obj, bm)], [(obj, v) for v in edge.verts])
assert bpy.ops.mesh.polygroups_connect_vertex_seam() == {"FINISHED"}
assert edge.seam and before == (len(bm.verts), len(bm.edges), len(bm.faces))

# Invalid selection leaves geometry/seams untouched.
select_vertices([(obj, bm)], [(obj, a)])
seams_before = tuple(edge.seam for edge in bm.edges)
assert bpy.ops.mesh.polygroups_connect_vertex_seam() == {"CANCELLED"}
assert seams_before == tuple(edge.seam for edge in bm.edges)
bpy.ops.object.mode_set(mode="OBJECT")
addon_utils.disable(ROOT.name, default_set=True)
print("CONNECT_VERTEX_SEAM_TESTS_PASSED")
