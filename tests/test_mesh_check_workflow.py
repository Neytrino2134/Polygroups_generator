"""Blender --background --factory-startup --python-exit-code 1 --python tests/test_mesh_check_workflow.py"""

from pathlib import Path
import sys

import addon_utils
import bpy
import bmesh


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)


def make_problem_mesh(name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [
            (0, 0, 0),
            (1, 0, 0),
            (1.5, 1, 0),
            (0.5, 1.5, 0),
            (-0.5, 1, 0),
            (3, 0, 0),
            (4, 0, 0),
            (5, 0, 0),
        ],
        [(5, 6)],
        [(0, 1, 2, 3, 4)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


obj = make_problem_mesh("MeshCheckProblems")
from polygroups_generator.operators.mesh_checks import analyze_mesh_stage
settings = bpy.context.scene.polygroups_mesh_finalization_settings

assert analyze_mesh_stage(obj, "FIN_FACES")["thin_protrusions"] == 1
assert analyze_mesh_stage(obj, "LOOSE_EDGES")["loose_edges"] == 1
assert analyze_mesh_stage(obj, "ISOLATED_VERTICES")["loose_vertices"] == 1
assert analyze_mesh_stage(obj, "NGONS")["ngons"] == 1
assert analyze_mesh_stage(obj, "OPEN_BOUNDARIES")["boundary_loops"] == 1

assert bpy.ops.object.polygroups_start_mesh_check() == {"FINISHED"}
assert settings.mesh_check_active_stage == "FIN_FACES"
assert bpy.ops.object.polygroups_next_mesh_check_stage() == {"FINISHED"}
assert settings.mesh_check_active_stage == "LOOSE_EDGES"

scan = bpy.ops.object.polygroups_scan_mesh_stage
assert scan(stage="LOOSE_EDGES") == {"FINISHED"}
assert settings.mesh_check_active_stage == "LOOSE_EDGES"
assert settings.mesh_check_loose_edges == 1
assert settings.mesh_check_stage_state == "ISSUES"

assert bpy.ops.object.polygroups_fix_mesh_stage(stage="NGONS") == {"FINISHED"}
assert analyze_mesh_stage(obj, "NGONS")["ngons"] == 0
assert settings.mesh_check_can_undo
assert bpy.ops.object.polygroups_undo_mesh_check_fix() == {"FINISHED"}
assert analyze_mesh_stage(obj, "NGONS")["ngons"] == 1
assert not settings.mesh_check_can_undo

# Exercise the full ordered repair on a fresh copy of the original problem mesh.
bpy.data.objects.remove(obj, do_unlink=True)
obj = make_problem_mesh("MeshCheckAll")
assert bpy.ops.object.polygroups_scan_and_fix_all() == {"FINISHED"}
for stage in ("FIN_FACES", "LOOSE_EDGES", "ISOLATED_VERTICES", "NGONS", "OPEN_BOUNDARIES", "NORMALS"):
    result = analyze_mesh_stage(obj, stage)
    count_key = {
        "FIN_FACES": "thin_protrusions",
        "LOOSE_EDGES": "loose_edges",
        "ISOLATED_VERTICES": "loose_vertices",
        "NGONS": "ngons",
        "OPEN_BOUNDARIES": "boundary_loops",
        "NORMALS": "normal_issues",
    }[stage]
    assert result[count_key] == 0, (stage, result)

assert settings.mesh_check_stage_state == "COMPLETE"
assert settings.mesh_check_scanned_stages.count(",") == 5

# A regular open cube is a boundary problem, not a fin, and must be capped.
bpy.data.objects.remove(obj, do_unlink=True)
mesh = bpy.data.meshes.new("OpenCube")
mesh.from_pydata(
    [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
     (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
    [],
    [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
)
obj = bpy.data.objects.new("OpenCube", mesh)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
assert analyze_mesh_stage(obj, "FIN_FACES")["thin_protrusions"] == 0
assert analyze_mesh_stage(obj, "OPEN_BOUNDARIES")["boundary_loops"] == 1
assert bpy.ops.object.polygroups_fix_mesh_stage(stage="OPEN_BOUNDARIES") == {"FINISHED"}
assert analyze_mesh_stage(obj, "OPEN_BOUNDARIES")["boundary_loops"] == 0

# Flip one face of a closed cube and verify the normals stage repairs it.
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(obj.data)
bm.faces.ensure_lookup_table()
bmesh.ops.reverse_faces(bm, faces=[bm.faces[0]])
bm.to_mesh(obj.data)
bm.free()
assert analyze_mesh_stage(obj, "NORMALS")["normal_issues"] > 0
assert bpy.ops.object.polygroups_fix_mesh_stage(stage="NORMALS") == {"FINISHED"}
assert analyze_mesh_stage(obj, "NORMALS")["normal_issues"] == 0
print("MESH CHECK WORKFLOW TEST PASSED")
