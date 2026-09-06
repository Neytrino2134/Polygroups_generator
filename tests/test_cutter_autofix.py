"""Blender background regression for the cutter Autofix scope."""
import sys
from pathlib import Path
from unittest.mock import patch

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators import object_seam_cutter as cutter

bpy.ops.mesh.primitive_cube_add()
target = bpy.context.active_object
target.name = "Cutter Autofix Target"

bm = bmesh.new()
bm.from_mesh(target.data)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY")
loose_a = bm.verts.new((5.0, 0.0, 0.0))
loose_b = bm.verts.new((6.0, 0.0, 0.0))
bm.edges.new((loose_a, loose_b))
bm.to_mesh(target.data)
bm.free()

before_vertices = len(target.data.vertices)
before_edges = len(target.data.edges)
before_faces = len(target.data.polygons)

# Autofix must not run mesh analysis or any of the old cleanup stages.
with patch.object(cutter, "analyze_mesh", side_effect=AssertionError("full mesh check ran")):
    result = bpy.ops.object.polygroups_auto_fix_after_cutter(target_name=target.name)
assert result == {"FINISHED"}

bm = bmesh.new()
bm.from_mesh(target.data)
assert len(bm.verts) == before_vertices
assert len(bm.edges) == before_edges
assert len(bm.faces) == before_faces + 1
assert not any(len(edge.link_faces) == 1 for edge in bm.edges)
assert sum(not edge.link_faces for edge in bm.edges) == 1
bm.free()

# Enabling the Fin option also removes wire edges and their loose endpoints.
settings = bpy.context.scene.polygroups_object_seam_cutter_settings
settings.cutter_auto_fix_fin_faces = True
with patch.object(cutter, "analyze_mesh", side_effect=AssertionError("full mesh check ran")):
    result = bpy.ops.object.polygroups_auto_fix_after_cutter(target_name=target.name)
assert result == {"FINISHED"}
bm = bmesh.new()
bm.from_mesh(target.data)
assert not any(not edge.link_faces for edge in bm.edges)
assert not any(not vert.link_edges for vert in bm.verts)
bm.free()
settings.cutter_auto_fix_fin_faces = False

# Closed n-gons are triangulated without treating the mesh as a hole.
bpy.ops.mesh.primitive_cylinder_add(vertices=5)
ngon_target = bpy.context.active_object
assert sum(len(face.vertices) > 4 for face in ngon_target.data.polygons) == 2
assert cutter._triangulate_ngons_for_autofix(ngon_target) == 2
assert not any(len(face.vertices) > 4 for face in ngon_target.data.polygons)

# The optional pass removes a weakly attached/open fin without a full analysis.
bpy.ops.mesh.primitive_plane_add()
fin_target = bpy.context.active_object
assert len(fin_target.data.polygons) == 1
with patch.object(cutter, "analyze_mesh", side_effect=AssertionError("full mesh check ran")):
    assert cutter._remove_fin_faces_for_autofix(bpy.context, fin_target) == 1
assert len(fin_target.data.polygons) == 0

# Apply Cutter Seams invokes the same narrow fill immediately before and after
# cutter processing, even when cutter processing itself does not open a hole.
bpy.ops.object.select_all(action="DESELECT")
target.select_set(True)
bpy.context.view_layer.objects.active = target
cutter_mesh = bpy.data.meshes.new("Autofix Cutter Mesh")
cutter_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
cutter_object = bpy.data.objects.new("Autofix Cutter", cutter_mesh)
bpy.context.scene.collection.objects.link(cutter_object)
cutter_object[cutter.CUTTER_PROP] = True
cutter_object.select_set(True)
settings = bpy.context.scene.polygroups_object_seam_cutter_settings
settings.cutter_auto_fix_mesh = True
settings.cutter_auto_fix_fin_faces = True
settings.cutter_auto_fix_seam_check = True
settings.hide_cutters_after_apply = False
settings.delete_cutters_after_apply = False
with (
    patch.object(cutter, "_remove_fin_faces_for_autofix",
                 side_effect=[1, 2]) as remove_fins,
    patch.object(cutter, "_delete_loose_geometry_for_autofix",
                 side_effect=[3, 4]) as remove_loose,
    patch.object(cutter, "_fill_open_nonmanifold_boundaries",
                 side_effect=[2, 1]) as fill,
    patch.object(cutter, "_triangulate_ngons_for_autofix",
                 side_effect=[3, 2]) as triangulate,
    patch.object(cutter, "_apply_cutters_to_mesh", return_value=4),
    patch.object(cutter, "play_operation_done_sound"),
):
    result = bpy.ops.object.polygroups_apply_cutter_seams()
assert result == {"FINISHED"}
assert remove_fins.call_count == 2
assert [call.args[1] for call in remove_fins.call_args_list] == [target, target]
assert remove_loose.call_count == 2
assert [call.args[1] for call in remove_loose.call_args_list] == [target, target]
assert fill.call_count == 2
assert [call.args[0] for call in fill.call_args_list] == [target, target]
assert triangulate.call_count == 2
assert [call.args[0] for call in triangulate.call_args_list] == [target, target]
assert bpy.context.scene.polygroups_seam_preparation_settings.seam_gap_status == "No seam gaps found"

addon_utils.disable(ROOT.name, default_set=True)
print("CUTTER_AUTOFIX_TESTS_PASSED")
