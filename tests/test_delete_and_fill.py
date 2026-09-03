"""Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)


def grid(name):
    mesh = bpy.data.meshes.new(name)
    verts = [(x, y, 0) for y in range(6) for x in range(6)]
    faces = [(y*6+x, y*6+x+1, (y+1)*6+x+1, (y+1)*6+x)
             for y in range(5) for x in range(5)]
    if name == 'B':
        faces.append(faces[6])  # Overlapping face creates non-manifold patch edges.
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    return obj


# Multi-object edit: replace an interior 2x2 patch, preserving a separate hole.
objects = [grid('A'), grid('B')]
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='FACE')
bpy.ops.mesh.select_all(action='DESELECT')
expected = []
for obj in objects:
    bm = bmesh.from_edit_mesh(obj.data)
    # A raised interior vertex makes the selected grid visibly uneven.
    next(v for v in bm.verts if tuple(v.co[:2]) == (2.0, 2.0)).co.z = .4
    bm.faces.ensure_lookup_table()
    unrelated_hole = bm.faces[0]
    bmesh.ops.delete(bm, geom=[unrelated_hole], context='FACES_ONLY')
    selected = [f for f in bm.faces if 1 < f.calc_center_median().x < 3 and 1 < f.calc_center_median().y < 3]
    for face in selected:
        face.select_set(True)
        face.material_index = 2
        face.smooth = True
    # Damaged topology can include reversed faces inside the region to repair.
    selected[0].normal_flip()
    old_faces = set(bm.faces) - set(selected)
    old_boundary = {e for e in bm.edges if e.is_boundary}
    for edge in old_boundary:
        edge.seam = True
    expected.append((bm, old_faces, old_boundary, len(bm.verts)))
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_delete_and_fill() == {'FINISHED'}
for bm, old_faces, old_boundary, old_verts in expected:
    assert all(f.is_valid for f in old_faces)
    new_faces = set(bm.faces) - old_faces
    assert len(new_faces) == 6
    assert all(len(f.verts) == 3 and f.select and f.smooth and f.material_index == 2 for f in new_faces)
    assert all(f.normal.z > .99 for f in new_faces)
    assert all(e.is_valid and e.seam and e.is_boundary for e in old_boundary)
    assert len(bm.verts) == old_verts - 1
    assert all(abs(v.co.z) < 1e-6 for f in new_faces for v in f.verts)
    assert all(len(e.link_faces) == 2 for f in new_faces for e in f.edges)

# Ring selection must retain the unselected central island without overlapping it.
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
obj = grid('Ring')
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='FACE')
bpy.ops.mesh.select_all(action='DESELECT')
bm = bmesh.from_edit_mesh(obj.data)
for face in bm.faces:
    center = face.calc_center_median()
    if 1 < center.x < 4 and 1 < center.y < 4 and not (2 < center.x < 3 and 2 < center.y < 3):
        face.select_set(True)
old_faces = {f for f in bm.faces if not f.select}
bm.select_flush_mode()
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_delete_and_fill() == {'FINISHED'}
assert all(f.is_valid for f in old_faces)
new_faces = set(bm.faces) - old_faces
assert len(new_faces) == 16
assert abs(sum(f.calc_area() for f in new_faces) - 8) < 1e-5
assert all(len(f.verts) == 3 for f in new_faces)

# A border patch should preserve the silhouette and fill only the removed area.
bpy.ops.mesh.select_all(action='DESELECT')
face = next(f for f in bm.faces if len(f.verts) == 4 and f.calc_center_median().x < 1)
face.select_set(True)
before = len(bm.faces)
bm.select_flush_mode()
assert bpy.ops.mesh.polygroups_delete_and_fill() == {'FINISHED'}
assert len(bm.faces) == before + 1

# No boundary: cancellation must not delete any geometry.
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bm = bmesh.from_edit_mesh(cube.data)
assert bpy.ops.mesh.polygroups_delete_and_fill() == {'CANCELLED'}
assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (8,12,6)
assert all(f.select for f in bm.faces)
bpy.ops.mesh.select_all(action='DESELECT')
assert bpy.ops.mesh.polygroups_delete_and_fill() == {'CANCELLED'}
print('DELETE_AND_FILL_TESTS_PASSED', flush=True)
