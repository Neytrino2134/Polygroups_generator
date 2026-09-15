"""Blender background regression for relative loose-part cleanup."""

import sys
from pathlib import Path

import addon_utils
import bpy
import bmesh
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.small_loose_parts import (
    analyze_loose_parts,
    remove_small_loose_parts,
    small_part_candidates,
)


def build_test_mesh():
    mesh = bpy.data.meshes.new("LoosePartTestMesh")
    bm = bmesh.new()
    # Scores are proportional to 2^3, 1^3 and 0.5^3. At 8%, only the
    # smallest cube and the isolated vertex should be candidates.
    for size, x in ((2.0, 0.0), (1.0, 5.0), (0.5, 8.0)):
        result = bmesh.ops.create_cube(bm, size=size)
        bmesh.ops.transform(
            bm,
            matrix=Matrix.Translation(Vector((x, 0.0, 0.0))),
            verts=result["verts"],
        )
    bm.verts.new((12.0, 0.0, 0.0))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("LoosePartTest", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


obj = build_test_mesh()
settings = bpy.context.scene.polygroups_model_preparation_settings
assert settings.small_loose_part_metric == "BOUNDING_BOX"
assert settings.small_loose_part_threshold_percent == 8.0

parts = analyze_loose_parts(obj, "BOUNDING_BOX")
assert len(parts) == 4
candidates = small_part_candidates(parts, 8.0)
assert sorted(part["vertex_count"] for part in candidates) == [1, 8]
assert max(part["ratio_percent"] for part in candidates) < 8.0

volume_parts = analyze_loose_parts(obj, "VOLUME")
assert sum(part["metric"] == "VOLUME" for part in volume_parts) == 3
volume_candidates = small_part_candidates(volume_parts, 8.0)
assert sorted(part["vertex_count"] for part in volume_candidates) == [1, 8]

result = bpy.ops.object.polygroups_small_loose_parts(delete=False)
assert result == {"FINISHED"}
assert obj.mode == "EDIT"
bm = bmesh.from_edit_mesh(obj.data)
assert sum(vertex.select for vertex in bm.verts) == 9

result = bpy.ops.object.polygroups_small_loose_parts(delete=True)
assert result == {"FINISHED"}
assert obj.mode == "OBJECT"
assert len(obj.data.vertices) == 16
remaining = analyze_loose_parts(obj, "BOUNDING_BOX")
assert len(remaining) == 2
assert sorted(part["vertex_count"] for part in remaining) == [8, 8]

# A threshold of zero must never remove a part, and the largest component is
# protected even when all component scores are zero.
assert small_part_candidates(remaining, 0.0) == []
zero_parts = [
    {"score": 0.0, "vertices": [0]},
    {"score": 0.0, "vertices": [1]},
]
assert len(small_part_candidates(zero_parts, 8.0)) == 1

batch_obj = build_test_mesh()
removed = remove_small_loose_parts(batch_obj, "BOUNDING_BOX", 8.0)
assert removed["part_count"] == 2
assert removed["vertex_count"] == 9
assert removed["face_count"] == 6
assert len(analyze_loose_parts(batch_obj, "BOUNDING_BOX")) == 2

print("SMALL_LOOSE_PARTS_OK")
