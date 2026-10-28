"""Read-only real-asset regression; open Containers_01_01.blend before this script."""
import bpy,bmesh,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds
expected={'MID':23,'LOD0':10,'LOD1':6,'LOD2':4,'LOD3':1,'LOD4':1}
for suffix,removed in expected.items():
 obj=bpy.data.objects['SM_Containers_01_01_'+suffix]
 bm=bmesh.new();bm.from_mesh(obj.data)
 original={f.index for f in obj.data.polygons if f.select}
 positions={v:tuple(v.co) for v in bm.verts}
 layers=list(bm.loops.layers.uv.values())
 uv_snapshot={f:tuple(tuple(tuple(l[u].uv) for l in f.loops) for u in layers) for f in bm.faces}
 invalid_before=sum(not e.is_manifold for e in bm.edges)
 result=repair_local_folds(bm,fix_folds=False,fix_degenerate=False,fix_dangling=True)
 assert result['dangling_faces']==removed,(suffix,result)
 assert original<=result['affected'],(suffix,original-result['affected'])
 assert result['dangling_filled']==(suffix=='MID')
 assert all(tuple(v.co)==positions[v] for v in bm.verts)
 assert all(tuple(tuple(tuple(l[u].uv) for l in f.loops) for u in layers)==uvs
            for f,uvs in uv_snapshot.items() if f.is_valid)
 assert sum(not e.is_manifold for e in bm.edges)==(invalid_before if suffix=='MID' else 0)
 assert not any(not e.link_faces for e in bm.edges)
 assert not any(not v.link_edges for v in bm.verts)
 again=repair_local_folds(bm,fix_folds=False,fix_degenerate=False,fix_dangling=True)
 assert all(again[k]==0 for k in ('dangling_faces','dangling_edges','dangling_verts','dangling_filled'))
 print('CONTAINERS_DANGLING_OK',suffix,result,flush=True)
 bm.free()
print('CONTAINERS_ALL_SIX_MESHES_OK',flush=True)
