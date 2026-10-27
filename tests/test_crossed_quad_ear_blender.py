"""Crossed quad normals can agree while one internal subtriangle reverses."""
import sys
from pathlib import Path
import bmesh
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds


def fixture(scale=1, ordinary=False, depth=.001):
    bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=2,radius=scale)
    bm.normal_update()
    face=max(bm.faces,key=lambda f:f.calc_center_median().z)
    a,b,c=list(face.verts)
    tip=bm.verts.new((a.co*.2+b.co*.4+c.co*.4 if ordinary else a.co*-.2+b.co*.7+c.co*.5)
                     + face.normal*scale*depth)
    bm.faces.remove(face)
    triangle=bm.faces.new((a,b,tip));quad=bm.faces.new((tip,b,c,a))
    layer=bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        for loop in f.loops:loop[layer].uv=(loop.vert.co.x/scale,loop.vert.co.y/scale)
    for loop in triangle.loops:loop[layer].uv+=Vector((4,4))
    bm.normal_update()
    return bm,tip,triangle,quad


for scale in (.001,1,1000):
    bm,tip,triangle,quad=fixture(scale)
    others={v:tuple(v.co) for v in bm.verts if v!=tip}
    result=repair_local_folds(bm,fix_degenerate=False)
    assert result['folds']==1,result
    assert not tip.is_valid and quad.is_valid and len(quad.verts)==3
    assert all(v.is_valid and tuple(v.co)==co for v,co in others.items())
    assert all(e.is_manifold for e in bm.edges)
    bm.free()

for protection in ('ordinary','thick','hidden','seam','material','pin'):
    bm,tip,triangle,quad=fixture(ordinary=protection=='ordinary',depth=.2 if protection=='thick' else .001)
    if protection=='hidden':triangle.hide_set(True)
    if protection=='seam':tip.link_edges[0].seam=True
    if protection=='material':triangle.material_index=1
    if protection=='pin':quad.loops[0][bm.loops.layers.uv.active].pin_uv=True
    result=repair_local_folds(bm,fix_degenerate=False)
    assert result['folds']==0,(protection,result)
    assert tip.is_valid
    bm.free()
print('CROSSED_QUAD_EAR_WELD_AND_PROTECTIONS_OK',flush=True)
