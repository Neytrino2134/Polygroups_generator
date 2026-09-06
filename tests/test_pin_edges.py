"""Blender smoke test for persistent pinned seam operators."""
import sys
from pathlib import Path

import bpy
import bmesh

ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
import polygroups_generator as addon
from polygroups_generator.pin_edges import pin_layer

addon.register()
bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="EDGE")
bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
bm.edges.ensure_lookup_table()
for edge in bm.edges:
    edge.select_set(False)
    edge.seam = False
edge = bm.edges[0]
edge.select_set(True)
edge.seam = True
bmesh.update_edit_mesh(bpy.context.active_object.data)

assert bpy.ops.mesh.polygroups_pin_selected_seams() == {"FINISHED"}
bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
bm.edges.ensure_lookup_table()
layer = pin_layer(bm)
assert layer is not None and bm.edges[0][layer]

settings = bpy.context.scene.polygroups_seam_preparation_settings
settings.seam_eraser_clear_mode = "PINNED"
assert bpy.ops.mesh.polygroups_unpin_selected_edges() == {"FINISHED"}
assert not bm.edges[0][layer] and bm.edges[0].seam

addon.unregister()
print("PIN EDGES REGISTRATION AND OPERATORS PASSED")
