"""Blender background regression for Relax Seams and Smart protection."""
import sys
from math import radians
from pathlib import Path

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.relax_seams import (
    _seam_adjacency,
    _smart_protected_vertices,
)

# A zigzag seam across a planar strip relaxes while its endpoints remain fixed.
verts = [(x, y, 0) for y in (0, 1, 2) for x in range(5)]
for index, y in enumerate((1, 1.3, 0.7, 1.3, 1)):
    verts[5 + index] = (index, y, 0)
faces = [(y * 5 + x, y * 5 + x + 1, (y + 1) * 5 + x + 1, (y + 1) * 5 + x)
         for y in range(2) for x in range(4)]
mesh = bpy.data.meshes.new("Relax Seam Strip")
mesh.from_pydata(verts, [], faces)
obj = bpy.data.objects.new("Relax Seam Strip", mesh)
bpy.context.collection.objects.link(obj)
for edge in mesh.edges:
    if set(edge.vertices).issubset(set(range(5, 10))):
        edge.use_seam = True
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
before = [vertex.co.copy() for vertex in bmesh.from_edit_mesh(mesh).verts]
settings = bpy.context.scene.polygroups_seam_preparation_settings
settings.seam_relax_mode = "RELAX"
settings.seam_relax_iterations = 2
assert bpy.ops.mesh.polygroups_relax_seams() == {"FINISHED"}
after = [vertex.co.copy() for vertex in bmesh.from_edit_mesh(mesh).verts]
assert after[5] == before[5] and after[9] == before[9]
assert any((after[index] - before[index]).length > 1e-5 for index in (6, 7, 8))
bpy.ops.object.mode_set(mode="OBJECT")

# Smart mode protects a junction and one seam-edge ring around it.
bm = bmesh.new()
center = bm.verts.new((0, 0, 0))
near = [bm.verts.new(co) for co in ((1, 0, 0), (-1, 0, 0), (0, 1, 0))]
far = [bm.verts.new(co) for co in ((2, 0, 0), (-2, 0, 0), (0, 2, 0))]
for a, b in zip(near, far):
    edge = bm.edges.new((center, a))
    edge.seam = True
    edge = bm.edges.new((a, b))
    edge.seam = True
adjacency, _edges = _seam_adjacency(bm)
protected = _smart_protected_vertices(adjacency, radians(90), 1)
assert center in protected and all(vertex in protected for vertex in near)
assert all(vertex not in protected for vertex in far)
bm.free()

# A degree-two corner sharper than the configured 90 degrees is protected.
bm = bmesh.new()
corner = bm.verts.new((0, 0, 0))
ends = [bm.verts.new((1, 0, 0)), bm.verts.new((0.5, 0.8660254, 0))]
for end in ends:
    edge = bm.edges.new((corner, end))
    edge.seam = True
adjacency, _edges = _seam_adjacency(bm)
protected = _smart_protected_vertices(adjacency, radians(90), 0)
assert protected == {corner}
bm.free()

print("RELAX_SEAMS_TEST_PASSED", flush=True)
addon_utils.disable(ROOT.name, default_set=True)
