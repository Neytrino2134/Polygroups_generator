"""Degree-two tip: a triangle folded onto a quad that unwraps as a huge island.

Reference: Small_Lava_Rocks_01_14.blend, SM_Small_Lava_Rocks_01_14_MID face 3174
(tip vertex 3170 used only by that triangle and quad 3075). Skipped when absent.
"""
import math
import sys
from pathlib import Path
from statistics import median

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import mesh_fold_repair as repair

BLEND = Path(r"D:\Work\3D Stocks\3D Asset Packs\05. Small Lava Rocks\!Blend\Small_Lava_Rocks_01_14.blend")
NAME, TRIANGLE, QUAD, TIP = "SM_Small_Lava_Rocks_01_14_MID", 3174, 3075, 3170


def source():
    bm = bmesh.new()
    bm.from_mesh(bpy.data.objects[NAME].data)
    for seq in (bm.verts, bm.faces):
        seq.ensure_lookup_table()
    bm.normal_update()
    return bm


def assert_tip_removed(bm, counts):
    assert not [v for v in bm.verts if len(v.link_faces) == 2]
    assert all(e.is_manifold for e in bm.edges)
    assert (len(bm.verts), len(bm.faces)) == (counts[0] - 1, counts[1] - 1)


def move_tip(bm, variant):
    """lifted: still folded, but deeper than the flat-ear rule accepts.
    inside: reflected across the closing edge, the pair tiles it validly."""
    tip = bm.verts[TIP]
    a, b, c = (bm.verts[i].co for i in (3171, 3167, 2526))
    if variant == "lifted":
        normal = (b - a).cross(c - a).normalized()
        tip.co += normal * max((b - a).length, (c - a).length, (c - b).length) * .1
    else:
        axis = (b - a).normalized()
        foot = a + axis * (tip.co - a).dot(axis)
        tip.co = foot - (tip.co - foot)
    bm.normal_update()


if not BLEND.exists():
    print("DEGREE_TWO_TIP_SKIPPED_NO_REFERENCE", flush=True)
else:
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    addon_utils.enable(ROOT.name, default_set=False)
    for variant in ("original", "lifted", "inside"):
        bm = source()
        assert len(bm.verts[TIP].link_faces) == 2
        if variant != "original":
            move_tip(bm, variant)
            pair = {bm.faces[TRIANGLE], bm.faces[QUAD]}
            layers = list(bm.loops.layers.uv.values())
            assert repair._plan(pair, layers, 1e-7, backtracking_ear=True) is None, "fixture must defeat ear rules"
        counts = len(bm.verts), len(bm.faces)
        # "inside" keeps the stored huge UV island; only the fold route is under test.
        result = repair.repair_local_folds(bm, fix_folds=True, fix_degenerate=True, fix_zero_area=True,
                                           fix_dangling=True, fix_stretched_triangles=variant != "inside")
        if variant == "inside":
            assert result['folds'] == 0 and (len(bm.verts), len(bm.faces)) == counts, result
        else:
            assert result['folds'] == 1 and {TRIANGLE, QUAD} <= result['affected'], (variant, result)
            assert_tip_removed(bm, counts)
        bm.free()

    # UV route alone: after one unwrap the triangle is a ~38x texel outlier.
    obj = bpy.data.objects[NAME]
    bpy.context.view_layer.objects.active = obj
    if obj.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)
    bpy.ops.object.mode_set(mode='OBJECT')
    bm = source()
    counts = len(bm.verts), len(bm.faces)
    layers = list(bm.loops.layers.uv.values())
    assert repair._uv_outlier(bm.faces[TRIANGLE], layers, 1e-7, 10)
    assert not repair._uv_outlier(bm.faces[TRIANGLE], layers, 1e-7, 50), "50 misses it: keep default at 10"
    result = repair.repair_local_folds(bm, fix_folds=False, fix_degenerate=False, fix_stretched_triangles=True)
    assert result['stretched'] == 1, result
    assert_tip_removed(bm, counts)
    bm.to_mesh(obj.data)
    bm.free()

    # After repair a fresh unwrap has no texel-scale outlier left.
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)
    bpy.ops.object.mode_set(mode='OBJECT')
    bm = source()
    layer = bm.loops.layers.uv.active
    density = {f: repair._uv_face_area(f, layer) / max(f.calc_area(), 1e-30) for f in bm.faces}
    worst = max(math.sqrt(density[f] / median(density[o] for e in f.edges for o in e.link_faces if o != f))
                for f in bm.faces)
    assert worst < 5, worst
    bm.free()
    print("DEGREE_TWO_TIP_OK", flush=True)
