"""Run with Blender --background --factory-startup --python-exit-code 1 --python."""
import importlib.util
from pathlib import Path
import bmesh

spec = importlib.util.spec_from_file_location('gap', Path(__file__).resolve().parents[1] / 'operators/seam_gap_detection.py')
gap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gap)

for corner in (False, True):
    bm = bmesh.new()
    a = bm.verts.new((-.2, 0, 0))
    b = bm.verts.new((0, 0, 0))
    c = bm.verts.new((.05, 0, 0))
    d = bm.verts.new((.05, .2, 0))
    e = bm.verts.new((.25, 0, 0) if corner else (.05, -.2, 0))
    for start, end in ((a, b), (c, d), (c, e)):
        bm.edges.new((start, end)).seam = True
    bridge = bm.edges.new((b, c))
    assert not gap._find_gap_paths(bm, 1, .1, False)
    paths = gap._find_gap_paths(bm, 1, .1, True)
    assert len(paths) == 1 and paths[0]['edges'] == [bridge]
    assert not gap._find_gap_paths(bm, 1, .01, True)
    c.co.x = -.05
    assert not gap._find_gap_paths(bm, 1, .1, True), 'Must not connect backwards'
    bm.free()
print('SEAM GAP CORNER AND T-JUNCTION TESTS PASSED')
