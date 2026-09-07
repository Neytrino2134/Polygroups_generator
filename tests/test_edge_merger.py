"""Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy


root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)

bpy.ops.mesh.primitive_plane_add(size=2.0)
obj = bpy.context.active_object
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="DESELECT")

bm = bmesh.from_edit_mesh(obj.data)
bm.edges.ensure_lookup_table()
edge = bm.edges[0]
midpoint = (edge.verts[0].co + edge.verts[1].co) * 0.5
edge.select_set(True)
bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

result = bpy.ops.mesh.polygroups_edge_merger_click()
assert result == {"FINISHED"}, result

bm = bmesh.from_edit_mesh(obj.data)
assert len(bm.verts) == 3, len(bm.verts)
assert any((vert.co - midpoint).length < 1.0e-6 for vert in bm.verts)
assert tuple(bpy.context.tool_settings.mesh_select_mode) == (False, True, False)

print("EDGE MERGER TEST PASSED")
