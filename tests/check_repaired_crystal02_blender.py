import bpy,bmesh,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import inspect_triangle_quality,repair_local_folds
obj=bpy.data.objects['SM_Crystals_Pack_02_02_MID']
if obj.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
bm=bmesh.new();bm.from_mesh(obj.data)
assert (len(bm.verts),len(bm.edges),len(bm.faces))==(3149,6338,3191)
assert inspect_triangle_quality(bm)[1]['uv_triangles']==0
assert repair_local_folds(bm,selected_only=True)['folds']==0
print('REOPEN_REPAIRED_CRYSTAL02_OK')
bm.free()
