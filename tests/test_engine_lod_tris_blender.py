"""ReBake Create LODs and ReLOD take LOD triangle budgets from the Start Phase 2 pipeline switch."""
from pathlib import Path
import sys
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.rebake_lods import FinalRebakeLODs
from polygroups_generator.operators.relod import ReLODPlan
from polygroups_generator.settings.preparation import ENGINE_LOD_TRIS
ctx=bpy.context
p=ctx.scene.polygroups_model_preparation_settings
s=ctx.scene.polygroups_mesh_finalization_settings
bpy.ops.mesh.primitive_plane_add()
target=ctx.object;target.name='SM_Engine_Tris_01_01_MID'
for engine in ('FAB','UNITY'):
    p.phase2_run_engine=engine
    # Manual Smart LODs edits do not leak into ReBake / ReLOD.
    for index in range(1,6):setattr(s,f'smart_lods_target_{index}',7)
    expected=list(ENGINE_LOD_TRIS[engine])
    rebake=FinalRebakeLODs(ctx,target).options
    assert [rebake[f'smart_lods_target_{i}'] for i in range(1,6)]==expected,(engine,rebake)
    relod=ReLODPlan(ctx,target,True,False).options
    assert [relod[f'smart_lods_target_{i}'] for i in range(1,6)]==expected,(engine,relod)
print('ENGINE_LOD_TRIS_REBAKE_RELOD_OK')
