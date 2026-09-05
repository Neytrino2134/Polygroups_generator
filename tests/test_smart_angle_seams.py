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

# A partial selection must be isolated from its unselected neighbor.
bpy.ops.mesh.mark_seam(clear=True)
bpy.ops.mesh.select_all(action='DESELECT')
bm.faces.ensure_lookup_table()
bm.faces[0].select_set(True)
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
assert all(edge.seam for edge in bm.faces[0].edges if edge.is_manifold)
print('SMART ANGLE SEAMS AND UV PRESERVATION PASSED')
