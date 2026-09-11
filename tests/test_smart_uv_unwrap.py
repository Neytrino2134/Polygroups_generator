"""Blender smoke test for Generate Smart Seams + Angle Based + Auto Pack."""

from pathlib import Path
import sys

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.active_object
seams = bpy.context.scene.polygroups_seam_preparation_settings
finalization = bpy.context.scene.polygroups_seam_finalization_settings
seams.smart_seam_auto_relax = False
seams.smart_seam_create_edges = False
finalization.smart_uv_unwrap_auto_pack = True

assert bpy.ops.object.polygroups_smart_uv_unwrap() == {"FINISHED"}
assert obj.mode == "OBJECT"
assert obj.data.uv_layers.active is not None
assert any(edge.use_seam for edge in obj.data.edges)

# Island Selector exposes this Object operator while the mesh is in Edit Mode.
bpy.ops.object.mode_set(mode="EDIT")
assert bpy.ops.object.polygroups_smart_uv_unwrap() == {"FINISHED"}
assert obj.mode == "EDIT"
bpy.ops.object.mode_set(mode="OBJECT")

addon_utils.disable(ROOT.name, default_set=True)
print("SMART_UV_UNWRAP_OK", flush=True)
