"""Blender background test for the combined seam-gap operator and defaults."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

settings = bpy.context.scene.polygroups_seam_preparation_settings
assert settings.seam_gap_max_edges == 6
assert abs(settings.seam_gap_max_distance - 0.2) < 1e-7

mesh = bpy.data.meshes.new("Seam Gap Mesh")
mesh.from_pydata(
    [(0, 0, 0), (0.05, 0, 0), (0.05, 0.05, 0), (0, 0.05, 0)],
    [],
    [(0, 1, 2, 3)],
)
obj = bpy.data.objects.new("Seam Gap Object", mesh)
bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
mesh.edges[0].use_seam = True

# The N-panel operator also works from Object Mode and restores that mode.
assert bpy.context.mode == "OBJECT"
assert bpy.ops.mesh.polygroups_check_and_close_seam_gaps() == {"FINISHED"}
assert bpy.context.mode == "OBJECT"
assert all(edge.use_seam for edge in mesh.edges)
assert settings.seam_gap_status.startswith("Closed 1 seam gap")

addon_utils.disable(ROOT.name, default_set=True)
print("SEAM_GAP_OPERATOR_TESTS_PASSED")
