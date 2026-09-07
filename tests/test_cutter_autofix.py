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

settings = bpy.context.scene.polygroups_object_seam_cutter_settings
settings.cutter_auto_fix_fin_faces = False

bpy.ops.mesh.primitive_cube_add()
target = bpy.context.active_object
target.name = "Cutter Autofix Target"

with patch.object(cutter, "relax_seams", return_value=(2, 1)) as relax:
    assert cutter._smart_relax_seams_for_autofix(bpy.context, target) == 2
assert relax.call_args.args[1:] == ("SMART", 1, cutter.radians(90.0), 1)
assert relax.call_args.kwargs == {
    "use_corner_angle": False,
    "select_result": False,
    "selected_area_only": False,
}
assert bpy.context.mode == "OBJECT"

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
settings.cutter_auto_fix_small_islands = True
settings.cutter_auto_fix_small_islands_threshold = 0.5
settings.cutter_auto_fix_weld = True
settings.cutter_auto_fix_weld_distance = 0.005
settings.cutter_auto_fix_smart_relax_seams = True
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
                 return_value=3) as triangulate,
    patch.object(cutter, "_apply_cutters_to_mesh", return_value=4),
    patch.object(cutter, "_dissolve_degenerate_seam_geometry", return_value=0) as repair,
    patch.object(cutter, "_prepare_seam_band_autoweld", return_value=None) as weld,
    patch.object(cutter, "apply_weld_to_objects", return_value=1) as apply_weld,
    patch.object(cutter, "_sync_autoweld_vertex_group") as sync_weld_group,
    patch.object(cutter, "_smart_relax_seams_for_autofix", return_value=5) as smart_relax,
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
assert triangulate.call_count == 1
assert triangulate.call_args.args[0] == target
assert weld.call_count == 1
assert weld.call_args.args[0] == target
assert abs(weld.call_args.args[1] - 0.005) < 1e-7
assert apply_weld.call_count == 1
assert apply_weld.call_args.args[1] == [target]
assert abs(apply_weld.call_args.args[2] - 0.005) < 1e-7
assert repair.call_count == 2
assert sync_weld_group.call_count == 1
assert smart_relax.call_count == 1
assert smart_relax.call_args.args == (bpy.context, target)
assert bpy.context.scene.polygroups_seam_preparation_settings.seam_gap_status == "No seam gaps found"
assert bpy.context.scene.polygroups_generator_settings.small_island_status

# A disabled Weld stage must not create a modifier/group or apply Weld.
settings.cutter_auto_fix_weld = False
session = cutter.CutterApplySession(bpy.context, target, [], lambda *_args: None)
session.status.cutter_apply_stage = "WELDING"
with (
    patch.object(cutter, "_dissolve_degenerate_seam_geometry") as repair_disabled,
    patch.object(cutter, "_prepare_seam_band_autoweld") as prepare_disabled,
    patch.object(cutter, "apply_weld_to_objects") as apply_disabled,
    patch.object(cutter, "_sync_autoweld_vertex_group") as sync_disabled,
):
    session.step(bpy.context)
assert prepare_disabled.call_count == 0
assert apply_disabled.call_count == 0
assert repair_disabled.call_count == 0
assert sync_disabled.call_count == 0
session.finish(bpy.context, "CANCELLED")
settings.cutter_auto_fix_weld = True

# AutoWeld is prepared last, restricted to seam vertices, then applied.
modifier = cutter._prepare_seam_band_autoweld(target, 0.005)
assert modifier == target.modifiers[-1]
assert abs(modifier.merge_threshold - 0.005) < 1e-7
assert modifier.vertex_group == cutter.AUTOWELD_VERTEX_GROUP_NAME
group = target.vertex_groups[modifier.vertex_group]
grouped = {vertex.index for vertex in target.data.vertices
           if any(item.group == group.index for item in vertex.groups)}
seam = {index for edge in target.data.edges if edge.use_seam for index in edge.vertices}
assert grouped == seam
settings.cutter_auto_fix_weld_distance = 0.006
assert abs(modifier.merge_threshold - 0.006) < 1e-7
assert cutter.apply_weld_to_objects(bpy.context, [target], 0.006) == 1
assert target.modifiers.get(cutter.AUTOWELD_MODIFIER_NAME) is None
assert target.vertex_groups.get(cutter.AUTOWELD_VERTEX_GROUP_NAME) is not None

# A collinear seam triangle is removed before Weld, while a normal triangle stays.
degenerate_mesh = bpy.data.meshes.new("Degenerate Seam Triangle")
degenerate_mesh.from_pydata(
    [(0, 0, 0), (2, 0, 0), (1, 0, 0), (0, 1, 0)],
    [],
    [(0, 1, 2), (0, 1, 3)],
)
degenerate_target = bpy.data.objects.new("Degenerate Seam Triangle", degenerate_mesh)
bpy.context.collection.objects.link(degenerate_target)
degenerate_mesh.edges[0].use_seam = True
assert cutter._dissolve_degenerate_seam_geometry(degenerate_target, 0.005) >= 1
assert all(polygon.area > 1e-10 for polygon in degenerate_mesh.polygons)
assert len(degenerate_mesh.polygons) == 1

# A concave seam quad caused by a vertex crossing its valid area is repaired
# into an unambiguous triangle fill before Weld.
folded_mesh = bpy.data.meshes.new("Folded Seam Quad")
folded_mesh.from_pydata(
    [(0, 0, 0), (2, 0, 0), (0.4, 0.4, 0), (0, 2, 0)],
    [],
    [(0, 1, 2, 3)],
)
folded_target = bpy.data.objects.new("Folded Seam Quad", folded_mesh)
bpy.context.collection.objects.link(folded_target)
next(edge for edge in folded_mesh.edges if set(edge.vertices) == {0, 1}).use_seam = True
assert cutter._dissolve_degenerate_seam_geometry(folded_target, 0.005) >= 1
assert folded_mesh.polygons
assert all(len(polygon.vertices) == 3 and polygon.area > 1e-10
           for polygon in folded_mesh.polygons)

addon_utils.disable(ROOT.name, default_set=True)
print("CUTTER_AUTOFIX_TESTS_PASSED")
