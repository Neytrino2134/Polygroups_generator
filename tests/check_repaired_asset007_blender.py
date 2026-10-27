"""Reopen the repaired real asset and verify geometry/UV/idempotence."""
import sys
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds,inspect_triangle_quality

obj=bpy.data.objects['SM_Asset_00_07_MID']
if obj.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
bm=bmesh.new();bm.from_mesh(obj.data)
assert (len(bm.verts),len(bm.edges),len(bm.faces))==(3924,7909,3987)
assert all(e.is_manifold for e in bm.edges)
assert inspect_triangle_quality(bm)[1]['uv_triangles']==0
result=repair_local_folds(bm,fix_zero_area=True,fix_stretched_triangles=True)
assert result['folds']==result['collapsed']==result['stretched']==0,result
bm.free()
print('REOPEN_REPAIRED_ASSET007_OK',flush=True)
