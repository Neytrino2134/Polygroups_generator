"""Blender smoke test for persistent pinned seam operators."""
import sys
from pathlib import Path

import bpy
import bmesh

ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
import polygroups_generator as addon
from polygroups_generator.pin_edges import pin_layer
from polygroups_generator.operators.connect_vertex_seam import connect_pair
from polygroups_generator.operators.seam_eraser import erase_pair

addon.register()
# Regression: the first pinned Vertex Seam Path must create its custom layer
# before Blender's Connect Vertex Path returns new BMEdge wrappers.
bpy.ops.mesh.primitive_grid_add(x_subdivisions=2, y_subdivisions=2)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="VERT")
path_obj = bpy.context.active_object
bm = bmesh.from_edit_mesh(path_obj.data)
bm.verts.ensure_lookup_table()
bpy.ops.mesh.select_all(action="DESELECT")
bm.verts[0].select_set(True)
bm.verts[3].select_set(True)
bmesh.update_edit_mesh(path_obj.data)
settings = bpy.context.scene.polygroups_seam_preparation_settings
settings.seam_path_pin = True
assert pin_layer(bm) is None
assert connect_pair(bpy.context, path_obj, bm, bm.verts[0], bm.verts[3]) == 1
bm = bmesh.from_edit_mesh(path_obj.data)
layer = pin_layer(bm)
assert layer is not None and any(edge.seam and edge[layer] for edge in bm.edges)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.data.objects.remove(path_obj, do_unlink=True)

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
bmesh.update_edit_mesh(bpy.context.active_object.data)

# Normal seam commands share the same Mark As Pinned option and clear both marks.
settings.seam_path_pin = True
assert bpy.ops.mesh.polygroups_mark_selected_edges_seam() == {"FINISHED"}
bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
bm.edges.ensure_lookup_table()
layer = pin_layer(bm)
assert bm.edges[0].seam and bm.edges[0][layer]
assert bpy.ops.mesh.polygroups_clear_selected_edges_seam() == {"FINISHED"}
assert not bm.edges[0].seam and not bm.edges[0][layer]

bm.edges[0].seam = True
bmesh.update_edit_mesh(bpy.context.active_object.data)
assert bpy.ops.mesh.polygroups_pin_selected_seams() == {"FINISHED"}
bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
bm.edges.ensure_lookup_table()
layer = pin_layer(bm)
assert layer is not None and bm.edges[0][layer]

settings.seam_eraser_clear_mode = "PINNED"
# Pinned Only removes the custom mark but preserves the seam.
assert erase_pair(bpy.context, bpy.context.active_object, bm,
                  bm.edges[0].verts[0], bm.edges[0].verts[1]) == 1
assert not bm.edges[0][layer] and bm.edges[0].seam

# Clear Seams and Pinned removes both marks.
assert bpy.ops.mesh.polygroups_pin_selected_seams() == {"FINISHED"}
settings.seam_eraser_clear_mode = "SEAMS"
assert erase_pair(bpy.context, bpy.context.active_object, bm,
                  bm.edges[0].verts[0], bm.edges[0].verts[1]) == 1
assert not bm.edges[0][layer] and not bm.edges[0].seam

addon.unregister()
print("PIN EDGES REGISTRATION AND OPERATORS PASSED")
