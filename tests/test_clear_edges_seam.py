"""Blender --background --factory-startup --python-exit-code 1 --python tests/test_clear_edges_seam.py"""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)


def grid(name):
    mesh = bpy.data.meshes.new(name)
    verts = [(x, y, 0) for y in range(4) for x in range(4)]
    faces = [(y * 4 + x, y * 4 + x + 1, (y + 1) * 4 + x + 1, (y + 1) * 4 + x)
             for y in range(3) for x in range(3)]
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    return obj


objects = [grid("A"), grid("B")]
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="FACE")
bpy.ops.mesh.select_all(action="DESELECT")


def selection(bm):
    return tuple(tuple(item.select for item in items) for items in (bm.verts, bm.edges, bm.faces))


# A connected patch with one interior edge; all outside seams stay untouched.
snapshots = []
for obj in objects:
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for edge in bm.edges:
        edge.seam = True
    for index in (0, 1):
        bm.faces[index].select_set(True)
    bm.select_flush_mode()
    interior = (set(bm.faces[0].edges) & set(bm.faces[1].edges)).pop()
    boundary = (set(bm.faces[0].edges) | set(bm.faces[1].edges)) - {interior}
    for edge in boundary:
        edge.seam = False
    snapshots.append((bm, interior, selection(bm)))
assert bpy.ops.mesh.polygroups_clear_inside_edges_seam() == {"FINISHED"}
for bm, interior, selected_before in snapshots:
    assert not interior.seam
    assert all(edge.seam for edge in bm.edges if edge != interior)
    assert selection(bm) == selected_before

# Ring selection: open outer boundary and the unselected central hole remain seams.
bpy.ops.mesh.select_all(action="DESELECT")
for obj in objects:
    bm = bmesh.from_edit_mesh(obj.data)
    for index, face in enumerate(bm.faces):
        face.select_set(index != 4)
    bm.select_flush_mode()
    for edge in bm.edges:
        edge.seam = True
assert bpy.ops.mesh.polygroups_clear_inside_edges_seam() == {"FINISHED"}
for obj in objects:
    bm = bmesh.from_edit_mesh(obj.data)
    hole_edges = set(bm.faces[4].edges)
    for edge in bm.edges:
        assert edge.seam == (edge.is_boundary or edge in hole_edges)

# Selected-edge clear must leave unselected seams and selection unchanged.
bpy.ops.mesh.select_mode(type="EDGE")
bpy.ops.mesh.select_all(action="DESELECT")
snapshots = []
for obj in objects:
    bm = bmesh.from_edit_mesh(obj.data)
    for edge in bm.edges:
        edge.seam = True
    next(iter(bm.edges)).select_set(True)
    snapshots.append((bm, selection(bm)))
assert bpy.ops.mesh.polygroups_clear_selected_edges_seam() == {"FINISHED"}
for bm, selected_before in snapshots:
    assert all(edge.seam == (not edge.select) for edge in bm.edges)
    assert selection(bm) == selected_before

# No faces selected: do not infer a region from an isolated selected edge.
before = [tuple(edge.seam for edge in bm.edges) for bm, _ in snapshots]
assert bpy.ops.mesh.polygroups_clear_inside_edges_seam() == {"CANCELLED"}
assert before == [tuple(edge.seam for edge in bm.edges) for bm, _ in snapshots]
bpy.ops.mesh.select_all(action="DESELECT")
assert bpy.ops.mesh.polygroups_clear_selected_edges_seam() == {"CANCELLED"}
bpy.ops.object.mode_set(mode="OBJECT")
assert not bpy.ops.mesh.polygroups_clear_selected_edges_seam.poll()
assert not bpy.ops.mesh.polygroups_clear_inside_edges_seam.poll()
addon_utils.disable(ROOT.name, default_set=True)
print("CLEAR_EDGES_SEAM_TESTS_PASSED")
