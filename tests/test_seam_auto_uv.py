"""Blender background regression for seam-operation Auto Unwrap."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)


mesh = bpy.data.meshes.new("Seam Auto UV Test Mesh")
mesh.from_pydata(
    [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)],
    [(0, 1), (1, 2), (2, 3), (3, 0)],
    [(0, 1, 2, 3)],
)
obj = bpy.data.objects.new("Seam Auto UV Test", mesh)
bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="EDGE")
bpy.ops.mesh.select_all(action="DESELECT")

bm = bmesh.from_edit_mesh(mesh)
bm.edges.ensure_lookup_table()
bm.edges[0].select_set(True)
bmesh.update_edit_mesh(mesh)

settings = bpy.context.scene.polygroups_seam_finalization_settings
settings.auto_unwrap_after_seam = False
settings.auto_average_islands_scale_after_unwrap = True
assert "FINISHED" in bpy.ops.mesh.polygroups_mark_selected_edges_seam()
assert len(mesh.uv_layers) == 0, "Average alone must not implicitly enable Auto Unwrap"

bm = bmesh.from_edit_mesh(mesh)
bm.edges[1].select_set(True)
bmesh.update_edit_mesh(mesh)
settings.auto_unwrap_after_seam = True
assert "FINISHED" in bpy.ops.mesh.polygroups_mark_selected_edges_seam()
assert len(mesh.uv_layers) == 1
bm = bmesh.from_edit_mesh(mesh)
uv_layer = bm.loops.layers.uv.active
uv_coordinates = [loop[uv_layer].uv.copy() for face in bm.faces for loop in face.loops]
assert max((uv - uv_coordinates[0]).length for uv in uv_coordinates[1:]) > 0.1, (
    "Auto Unwrap created a UV layer but did not unwrap the mesh"
)
assert bpy.context.mode == "EDIT_MESH"
assert tuple(bpy.context.tool_settings.mesh_select_mode) == (False, True, False)

print("SEAM_AUTO_UV_TEST_PASSED")
