"""Blender background integration tests for longitudinal seam modes."""
import math
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.pin_edges import is_pinned, pin_layer


def make_open_cylinder(columns=12, rows=7):
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("LongitudinalTest")
    obj = bpy.data.objects.new("LongitudinalTest", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bm = bmesh.new()
    verts = []
    for row in range(rows):
        z = row / (rows - 1) * 3.0
        verts.append([
            bm.verts.new((math.cos(2 * math.pi * col / columns),
                          math.sin(2 * math.pi * col / columns), z))
            for col in range(columns)
        ])
    for row in range(rows - 1):
        for col in range(columns):
            nxt = (col + 1) % columns
            bm.faces.new((verts[row][col], verts[row][nxt],
                          verts[row + 1][nxt], verts[row + 1][col]))
    bm.to_mesh(mesh)
    bm.free()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    return obj


obj = make_open_cylinder()
assert bpy.ops.mesh.polygroups_mark_longitudinal_seam(
    double_seam=False, prefer_backside=False, seam_offset=0,
    path_method="SIMPLE", create_new_edges=False) == {"FINISHED"}
bm = bmesh.from_edit_mesh(obj.data)
simple = {edge.index for edge in bm.edges if edge.seam}
assert len(simple) == 6, len(simple)

obj = make_open_cylinder()
assert bpy.ops.mesh.polygroups_mark_longitudinal_seam(
    double_seam=False, prefer_backside=False, seam_offset=2,
    path_method="SIMPLE", create_new_edges=False) == {"FINISHED"}
bm = bmesh.from_edit_mesh(obj.data)
offset = {edge.index for edge in bm.edges if edge.seam}
assert offset and offset != simple

obj = make_open_cylinder()
assert bpy.ops.mesh.polygroups_mark_longitudinal_seam(
    double_seam=False, prefer_backside=False, seam_offset=0,
    path_method="SMART", create_new_edges=True, mark_as_pinned=True) == {"FINISHED"}
bm = bmesh.from_edit_mesh(obj.data)
assert any(edge.seam for edge in bm.edges)
pins = pin_layer(bm, False)
assert pins is not None and all(is_pinned(edge, pins) for edge in bm.edges if edge.seam)
print("LONGITUDINAL SEAM MODES PASSED")
