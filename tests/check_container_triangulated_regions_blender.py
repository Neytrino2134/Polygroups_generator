"""Read-only regression: Container regions survive a complete triangulation."""
import bpy,bmesh,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds
for name in ('SM_Containers_01_01_MID','SM_Containers_01_01_MID.001'):
 obj=bpy.data.objects.get(name);assert obj is not None,'Open current-scene diagnostic snapshot first'
 bm=bmesh.new();bm.from_mesh(obj.data)
 bmesh.ops.triangulate(bm,faces=list(bm.faces))
 bm.faces.index_update();selected={f.index for f in bm.faces if f.select}
 positions={v:tuple(v.co) for v in bm.verts};layers=list(bm.loops.layers.uv.values())
 uvs={f:(f.index,tuple(tuple(tuple(l[layer].uv) for l in f.loops) for layer in layers)) for f in bm.faces}
 result=repair_local_folds(bm,fix_dangling=True,fix_stretched_triangles=True)
 assert result['dangling_faces']>0 and selected<=result['affected'],(name,result)
 assert result['dangling_filled']==1
 assert all(tuple(v.co)==positions[v] for v in bm.verts)
 assert all(tuple(tuple(tuple(l[layer].uv) for l in f.loops) for layer in layers)==values
            for f,(index,values) in uvs.items() if f.is_valid and index not in result['affected'])
 assert (len(bm.verts),len(bm.faces))==(6267,12524),(name,len(bm.verts),len(bm.faces))
 assert sum(not e.is_manifold for e in bm.edges)==4
 assert repair_local_folds(bm,fix_dangling=True,fix_stretched_triangles=True)['dangling_faces']==0
 bm.free();print('TRIANGULATED_CONTAINER_REGION_OK',name,flush=True)
