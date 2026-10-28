"""ReLOD real-asset check: open Containers_01_01.blend; never save it."""
import sys
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
p=bpy.context.scene.polygroups_model_preparation_settings
s=bpy.context.scene.polygroups_mesh_finalization_settings
p.phase2_relod_delete_current_lods=True
p.phase2_relod_method='UV_PRESERVE'
s.smart_lods_count=5
for i,value in enumerate((2900,1500,1000,500,150),1):setattr(s,'smart_lods_target_'+str(i),value)
source=bpy.data.objects['SM_Containers_01_01_MID']
positions=tuple(tuple(v.co) for v in source.data.vertices)
uvs=tuple(tuple(l.uv) for l in source.data.uv_layers.active.data)
assert bpy.ops.object.polygroups_relod()=={'FINISHED'}
assert tuple(tuple(v.co) for v in source.data.vertices)==positions
assert tuple(tuple(l.uv) for l in source.data.uv_layers.active.data)==uvs
for i in range(5):
 obj=bpy.data.objects['SM_Containers_01_01_LOD'+str(i)]
 obj.data.calc_loop_triangles();count=len(obj.data.loop_triangles)
 assert count<=getattr(s,'smart_lods_target_'+str(i+1)),(i,count)
 print('CONTAINERS_RELOD',obj.name,count,flush=True)
print('CONTAINERS_RELOD_ALL_FIVE_LEVELS_OK',flush=True)
