"""Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
from pathlib import Path
import bpy
import bmesh
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
obj = bpy.context.active_object
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='FACE')
bpy.ops.mesh.select_all(action='SELECT')
bm = bmesh.from_edit_mesh(obj.data)
layer = bm.loops.layers.uv.verify()
for face in bm.faces:
    for loop in face.loops:
        loop[layer].uv = (loop.vert.co.x * .123 + .7, loop.vert.co.y * .321 + .2)
before = [tuple(loop[layer].uv) for face in bm.faces for loop in face.loops]
assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
layer = bm.loops.layers.uv.active
after = [tuple(loop[layer].uv) for face in bm.faces for loop in face.loops]
assert before == after, 'Existing UV coordinates changed'
assert sum(edge.seam for edge in bm.edges) > 0

# A seed selection expands through faces until it reaches existing seams.
bpy.ops.mesh.mark_seam(clear=True)
bpy.ops.mesh.select_all(action='DESELECT')
bm.faces.ensure_lookup_table()
seed_face = bm.faces[0]
for edge in seed_face.edges:
    edge.seam = True
seed_face.select_set(True)
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
assert {face for face in bm.faces if face.select} == {seed_face}
assert all(edge.seam for edge in seed_face.edges)
print('SMART ANGLE SEAMS AND UV PRESERVATION PASSED')

# Any active mesh selection mode can seed a complete seam-bounded island.
from importlib import import_module
select_linked = import_module(
    ROOT.name + '.operators.smart_angle_seams').select_linked_faces_by_seam
linked_bm = bmesh.new()
bmesh.ops.create_grid(linked_bm, x_segments=5, y_segments=5, size=2.0)
linked_bm.faces.ensure_lookup_table()
island = {face for face in linked_bm.faces
          if abs(face.calc_center_median().x) < 1.0
          and abs(face.calc_center_median().y) < 1.0}
for edge in linked_bm.edges:
    membership = [face in island for face in edge.link_faces]
    edge.seam = len(membership) == 2 and membership[0] != membership[1]
center_vert = min(linked_bm.verts, key=lambda vert: vert.co.length_squared)
center_edge = next(edge for edge in center_vert.link_edges
                   if all(face in island for face in edge.link_faces))
center_face = next(iter(island))
for mode, element in (
        ((True, False, False), center_vert),
        ((False, True, False), center_edge),
        ((False, False, True), center_face)):
    for sequence in (linked_bm.faces, linked_bm.edges, linked_bm.verts):
        for item in sequence:
            item.select = False
    element.select_set(True)
    assert select_linked(linked_bm, mode) == island, mode
linked_bm.free()
print('VERTEX / EDGE / FACE LINKED-BY-SEAM SELECTION PASSED')

# Dense rock-like cube: small-scale geometric noise must not fragment its sides.
from math import radians
import random
segment = import_module(ROOT.name + '.core.smart_seams').segment_surfaces
mesh = bmesh.new()
bmesh.ops.create_cube(mesh, size=2.0)
bmesh.ops.subdivide_edges(mesh, edges=list(mesh.edges), cuts=15, use_grid_fill=True)
rng = random.Random(14)
for vertex in mesh.verts:
    for axis in range(3):
        vertex.co[axis] += rng.uniform(-0.022, 0.022)
mesh.normal_update()
mesh.faces.index_update()
labels = segment(mesh, set(mesh.faces), radians(45))
regions = set(labels.values())
assert len(regions) == 6, f'Noisy cube fragmented into {len(regions)} regions'
# Each label must remain a connected island.
for region in regions:
    remaining = {f for f in labels if labels[f] == region}
    stack = [remaining.pop()]
    while stack:
        for edge in stack.pop().edges:
            for face in edge.link_faces:
                if face in remaining:
                    remaining.remove(face)
                    stack.append(face)
    assert not remaining, 'Disconnected surface label'
assert labels == segment(mesh, set(mesh.faces), radians(45)), 'Non-deterministic segmentation'
mesh.free()
print('NOISY SURFACE SEGMENTATION PASSED')

# Regeneration must remove obsolete interior seams, without creating a UV map.
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=2)
obj = bpy.context.active_object
for uv in list(obj.data.uv_layers):
    obj.data.uv_layers.remove(uv)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bm = bmesh.from_edit_mesh(obj.data)
for edge in bm.edges:
    edge.seam = True
settings = bpy.context.scene.polygroups_seam_preparation_settings
settings.smart_seam_replace = False
assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {'FINISHED'}
assert all(e.seam for e in bm.edges)
settings.smart_seam_replace = True
assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {'FINISHED'}
assert all(not e.seam for e in bm.edges if e.is_manifold)
assert len(obj.data.uv_layers) == 0
print('REPLACE / KEEP SEAMS AND NO-UV PRESERVATION PASSED')
