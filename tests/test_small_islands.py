"""Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import importlib.util
from pathlib import Path
import bmesh

spec = importlib.util.spec_from_file_location('small_islands', Path(__file__).resolve().parents[1] / 'operators/small_islands.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def strip(widths):
    bm = bmesh.new()
    x = 0
    columns = []
    for width in [0] + widths:
        x += width
        columns.append([bm.verts.new((x, y, 0)) for y in (0, 1)])
    for a, b in zip(columns, columns[1:]):
        bm.faces.new((a[0], b[0], b[1], a[1]))
    for edge in bm.edges:
        edge.seam = edge.is_manifold
        edge.smooth = True
    return bm


for widths, expected in [([10, .1, 10], 1), ([10, .1, .1, .1, 10], 3), ([10, .1], 1), ([10, 10], 0)]:
    bm = strip(widths)
    removed, total, small, merged = module.plan_merge(bm, 3)
    assert merged == expected, (widths, merged)
    for index in removed:
        bm.edges[index].seam = False
    _, remaining, _, _ = module.plan_merge(bm, 3)
    assert remaining == total - expected
    if widths[-1] == 10 and len(widths) > 1:
        assert remaining == 2, 'Large islands merged through a small island chain'
    bm.free()

bm = strip([10, .1])
for edge in bm.edges:
    if edge.seam:
        edge.smooth = False
assert not module.plan_merge(bm, 3, True)[0]
assert module.plan_merge(bm, 3, False)[0]
bm.faces.ensure_lookup_table()
bm.faces[1].material_index = 1
assert not module.plan_merge(bm, 3, False, True)[0]
bm.free()
print('SMALL ISLAND GRAPH TESTS PASSED')

import sys
import bpy
import addon_utils
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)
obj = bpy.context.active_object
settings = bpy.context.scene.polygroups_generator_settings
cutter_settings = bpy.context.scene.polygroups_object_seam_cutter_settings
assert cutter_settings.cutter_auto_fix_mesh
assert cutter_settings.cutter_auto_fix_fin_faces
assert cutter_settings.cutter_auto_fix_seam_check
assert cutter_settings.cutter_auto_fix_small_islands
assert cutter_settings.cutter_auto_fix_weld
assert cutter_settings.cutter_auto_fix_smart_relax_seams
assert cutter_settings.cutter_auto_fix_triangulate_ngons
assert abs(cutter_settings.cutter_auto_fix_small_islands_threshold - 0.5) < 1e-7
assert abs(cutter_settings.cutter_auto_fix_weld_distance - 0.001) < 1e-7
weld_distance_property = cutter_settings.bl_rna.properties["cutter_auto_fix_weld_distance"]
assert abs(weld_distance_property.hard_min - 0.0001) < 1e-7
assert abs(weld_distance_property.hard_max - 0.05) < 1e-7
settings.small_island_threshold = 0.1
bm = strip([10, .04, 10])
bm.to_mesh(obj.data)
bm.free()
before = sum(edge.use_seam for edge in obj.data.edges)
assert bpy.ops.mesh.polygroups_merge_small_islands(
    preview=True, threshold_override=0.5,
) == {'FINISHED'}
assert obj.mode == 'EDIT'
live = bmesh.from_edit_mesh(obj.data)
assert sum(edge.select for edge in live.edges) == 1
assert sum(edge.seam for edge in live.edges) == before
assert bpy.ops.mesh.polygroups_merge_small_islands(
    preview=False, threshold_override=0.5,
) == {'FINISHED'}
assert sum(edge.seam for edge in live.edges) == before - 1
bpy.ops.object.mode_set(mode='OBJECT')
print('SMALL ISLAND PREVIEW AND APPLY PASSED')

# Combined Analyze and Merge respects Selected Area: an equivalent small
# island outside the selected faces must keep its seam borders.
bm = strip([10, .04, 10, .04, 10])
bm.faces.ensure_lookup_table()
for face in bm.faces:
    face.select = face.index in {0, 1}
bm.to_mesh(obj.data)
bm.free()
before = sum(edge.use_seam for edge in obj.data.edges)
settings.small_island_threshold = 0.5
settings.small_island_selected_area = True
bpy.ops.object.mode_set(mode='EDIT')
live = bmesh.from_edit_mesh(obj.data)
live.faces.ensure_lookup_table()
for face in live.faces:
    face.select_set(face.index in {0, 1})
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_analyze_and_merge_seams() == {'FINISHED'}
live = bmesh.from_edit_mesh(obj.data)
assert sum(edge.seam for edge in live.edges) == before - 1
bpy.ops.object.mode_set(mode='OBJECT')
print('ANALYZE AND MERGE SELECTED AREA PASSED')
