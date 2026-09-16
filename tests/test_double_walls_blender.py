"""Blender background regression for double-wall detection and UV collapse."""
import sys
from pathlib import Path
import addon_utils
import bmesh

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=False)
from polygroups_generator.core.double_walls import double_wall_groups
from polygroups_generator.operators.uv_artifacts import find_uv_artifacts, apply_uv_artifacts
from polygroups_generator.operators.mesh_checks import _double_wall_indices
import bpy

bm = bmesh.new()
uv = bm.loops.layers.uv.new('UVMap')
coords = ((0, 0, 0), (1, 0, 0), (0, 1, 0))
front = bm.faces.new([bm.verts.new(co) for co in coords])
back = bm.faces.new([bm.verts.new(co) for co in reversed(coords)])
healthy = bm.faces.new([bm.verts.new(co) for co in ((3, 0, 0), (4, 0, 0), (3, 1, 0))])
for face in bm.faces:
    for loop in face.loops:
        loop[uv].uv = (loop.vert.co.x, loop.vert.co.y)
bm.faces.index_update()
assert double_wall_groups(bm) == [{front, back}]
mesh = bpy.data.meshes.new('DoubleWallTest')
bm.to_mesh(mesh)
assert _double_wall_indices(mesh) == {front.index, back.index}
bpy.data.meshes.remove(mesh)
artifacts = find_uv_artifacts(bm)
assert len(artifacts) == 1 and artifacts[0]['faces'] == {front, back}
assert artifacts[0]['reason'] == 'zero_thickness_double_wall'
apply_uv_artifacts(bm, artifacts, 'MERGE_CENTER')
assert healthy.is_valid and healthy.calc_area() > 0
assert double_wall_groups(bm) == []
bm.free()

# Parallel faces separated in space are a real wall, not a double-wall artifact.
bm = bmesh.new()
bm.faces.new([bm.verts.new(co) for co in coords])
bm.faces.new([bm.verts.new((x, y, .01)) for x, y, z in reversed(coords)])
assert double_wall_groups(bm) == []
bm.free()
print('DOUBLE_WALLS_TEST_PASSED')
