"""Blender regression: seam sides, hidden faces and UV selection visibility."""
import sys
from pathlib import Path
import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.uv_seam_overlay import seam_uv_segments
from polygroups_generator.operators.uv_seam_path import _uv_island

bm = bmesh.new()
verts = [bm.verts.new((x, y, 0)) for x in range(3) for y in range(2)]
a = bm.faces.new((verts[0], verts[2], verts[3], verts[1]))
b = bm.faces.new((verts[2], verts[4], verts[5], verts[3]))
uv = bm.loops.layers.uv.new()
for face in bm.faces:
    face.select_set(True)
    for loop in face.loops:
        loop[uv].uv = loop.vert.co.xy
shared = next(e for e in bm.edges if len(e.link_faces) == 2)
shared.seam = True
assert _uv_island(a, uv) == {a}
assert len(seam_uv_segments(bm, uv, False)) == 1
shared.seam = False
assert _uv_island(a, uv) == {a, b}
shared.seam = True
for loop in b.loops:
    loop[uv].uv.x += 0.2
assert len(seam_uv_segments(bm, uv, False)) == 2
b.select_set(False)
assert len(seam_uv_segments(bm, uv, False)) == 1
assert len(seam_uv_segments(bm, uv, True)) == 2
b.hide_set(True)
assert len(seam_uv_segments(bm, uv, True)) == 1
shared.seam = False
assert not seam_uv_segments(bm, uv, True)
bm.free()
addon_utils.disable(ROOT.name, default_set=False)
print("UV_SEAM_OVERLAY_OK")
