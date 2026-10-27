"""Blender background regression for directed, neighbor-preserving ear merges."""
from pathlib import Path
import sys
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds, _plan


def fixture(scale=1, depth=.001):
    bm=bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=scale)
    bm.normal_update()
    face=max(bm.faces,key=lambda f:f.calc_center_median().z)
    a,b,c=list(face.verts)
    normal=face.normal.copy()
    tip=bm.verts.new(a.co*.6+b.co*.5-c.co*.1+normal*scale*depth)
    bm.faces.remove(face)
    triangle=bm.faces.new((a,b,tip))
    quad=bm.faces.new((tip,b,c,a))
    for name in ('UVMap','SecondUV'):
        layer=bm.loops.layers.uv.new(name)
        for f in bm.faces:
            for loop in f.loops:
                loop[layer].uv=(loop.vert.co.x/scale,loop.vert.co.y/scale)
        for loop in triangle.loops:
            loop[layer].uv += __import__('mathutils').Vector((4,4))
    bm.normal_update()
    return bm,tip,triangle,quad

for scale in (.001,1,1000):
    bm,tip,triangle,quad=fixture(scale)
    layers=list(bm.loops.layers.uv.values())
    coords={v:tuple(v.co) for v in bm.verts if v!=tip}
    snapshot={f:{l.vert:tuple(tuple(l[u].uv) for u in layers)
                 for l in f.loops if l.vert!=tip} for f in bm.faces if f!=triangle}
    initial=(len(bm.verts),len(bm.edges),len(bm.faces))
    result=repair_local_folds(bm,fix_degenerate=False)
    assert result['folds']==1,result
    assert not tip.is_valid
    assert (len(bm.verts),len(bm.edges),len(bm.faces))==tuple(n-d for n,d in zip(initial,(1,2,1)))
    assert all(v.is_valid and tuple(v.co)==co for v,co in coords.items())
    for f,corners in snapshot.items():
        assert f.is_valid
        if f==quad:continue
        for l in f.loops:
            assert tuple(tuple(l[u].uv) for u in layers)==corners[l.vert]
    assert all(e.is_manifold for e in bm.edges)
    assert repair_local_folds(bm)['folds']==0
    bm.free()

for protection in ('hidden','uv_pin','seam','edge_pin','material','thick','unselected'):
    bm,tip,triangle,quad=fixture(depth=.2 if protection=='thick' else .001)
    internal=next(e for e in tip.link_edges)
    if protection=='hidden':triangle.hide_set(True)
    elif protection=='uv_pin':quad.loops[0][bm.loops.layers.uv.active].pin_uv=True
    elif protection=='seam':internal.seam=True
    elif protection=='edge_pin':
        pin=bm.edges.layers.int.new('polygroups_pin_edge')
        next(iter(tip.link_edges))[pin]=1
    elif protection=='material':triangle.material_index=1
    if protection=='unselected':
        for f in bm.faces:f.select_set(False)
    if protection=='thick':
        assert _plan({triangle,quad},list(bm.loops.layers.uv.values()),1e-7,backtracking_ear=True) is None
        bm.free()
        continue
    result=repair_local_folds(bm,selected_only=protection=='unselected')
    assert result['folds']==0,(protection,result)
    assert tip.is_valid
    bm.free()
print('BACKTRACKING_EAR_TESTS_OK')
