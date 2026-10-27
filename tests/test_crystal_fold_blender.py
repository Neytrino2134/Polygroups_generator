"""Validate the reported crystal defect; optionally save a repaired copy (-- output.blend)."""
from pathlib import Path
import sys,json
import bpy,bmesh
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds,inspect_triangle_quality
obj=bpy.data.objects['SM_Crystals_Pack_02_18_MID']
edit=obj.mode=='EDIT'
if edit:bpy.ops.object.mode_set(mode='OBJECT')
bm=bmesh.new();bm.from_mesh(obj.data);bm.faces.ensure_lookup_table();bm.verts.ensure_lookup_table()
assert (len(bm.verts),len(bm.edges),len(bm.faces))==(3223,6496,3272)
layers=list(bm.loops.layers.uv.values())
tip=bm.verts[16];target=bm.verts[278];quad=bm.faces[70];triangle=bm.faces[3156]
coords={v:tuple(v.co) for v in bm.verts if v!=tip}
snapshot={f:tuple((l.vert,tuple(tuple(l[u].uv) for u in layers)) for l in f.loops)
          for f in bm.faces if f not in {triangle,quad}}
quad_uv={l.vert:tuple(tuple(l[u].uv) for u in layers) for l in quad.loops if l.vert!=tip}
invalid_before=sum(not e.is_manifold for e in bm.edges)
_,before=inspect_triangle_quality(bm)
for f in bm.faces:f.select_set(f==triangle)
result=repair_local_folds(bm,fix_degenerate=False,selected_only=True)
assert result['folds']==1 and result['affected']=={70,3156},result
assert not tip.is_valid and target.is_valid
assert all(v.is_valid and tuple(v.co)==co for v,co in coords.items())
for f,corners in snapshot.items():
    assert f.is_valid
    assert tuple((l.vert,tuple(tuple(l[u].uv) for u in layers)) for l in f.loops)==corners
assert quad.is_valid and len(quad.verts)==3
# The repaired triangle is unfolded locally; surrounding face UVs remain exact.
assert all(e.is_manifold for e in quad.edges)
assert sum(not e.is_manifold for e in bm.edges)==invalid_before
assert (len(bm.verts),len(bm.edges),len(bm.faces))==(3222,6494,3271)
_,after=inspect_triangle_quality(bm)
assert after['uv_triangles']==0,after
assert repair_local_folds(bm)['folds']==0
print('CRYSTAL_DIRECTED_MERGE_OK',json.dumps(dict(before=before,after=after,result={k:list(v) if isinstance(v,set) else v for k,v in result.items()},unchanged_other_faces=len(snapshot))))
if '--' in sys.argv:
    output=Path(sys.argv[sys.argv.index('--')+1])
    assert output.resolve()!=Path(bpy.data.filepath).resolve()
    assert not output.exists(),output
    bm.to_mesh(obj.data);obj.data.update()
    if edit:bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.wm.save_as_mainfile(filepath=str(output),check_existing=True)
    print('SAVED_REPAIRED_COPY',output)
bm.free()
