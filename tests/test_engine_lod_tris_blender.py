"""Smart LODs presets: Unreal / Unity defaults, add / save / remove, and the Phase 2 engine switch drives them."""
from pathlib import Path
import sys
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core import smart_lod_presets as presets
from polygroups_generator.operators.rebake_lods import FinalRebakeLODs
from polygroups_generator.operators.relod import ReLODPlan
ctx=bpy.context
p=ctx.scene.polygroups_model_preparation_settings
s=ctx.scene.polygroups_mesh_finalization_settings
presets.seed(s)
assert [x.name for x in s.smart_lods_presets]==['Unreal','Unity']
unreal,unity=s.smart_lods_presets['Unreal'],s.smart_lods_presets['Unity']
assert unreal.count==6 and list(unreal.targets)[:6]==[6000,3000,1500,750,350,200]
assert unity.count==5 and list(unity.targets)[:5]==[2900,1500,1000,500,150]

bpy.ops.mesh.primitive_plane_add()
target=ctx.object;target.name='SM_Engine_Tris_01_01_MID'
for engine,preset in (('FAB',unreal),('UNITY',unity)):
    p.phase2_run_engine=engine
    # The engine switch selects the preset and writes it into the live Smart LODs fields.
    assert s.smart_lods_preset_active==preset.name and s.smart_lods_count==preset.count
    assert [getattr(s,f'smart_lods_target_{i}') for i in range(1,11)]==list(preset.targets)
    # Manual Smart LODs edits do not leak into ReBake / ReLOD: they read the preset.
    s.smart_lods_count=3
    for index in range(1,11):setattr(s,f'smart_lods_target_{index}',7)
    for options in (FinalRebakeLODs(ctx,target).options,ReLODPlan(ctx,target,True,False).options):
        assert options['smart_lods_count']==preset.count,(engine,options['smart_lods_count'])
        assert [options[f'smart_lods_target_{i}'] for i in range(1,11)]==list(preset.targets),engine

# Add the current values as a preset, change them, save to the active one, then pick another and come back.
s.smart_lods_count=4
for index,value in enumerate((900,500,300,100),1):setattr(s,f'smart_lods_target_{index}',value)
assert bpy.ops.object.polygroups_smart_lods_preset(action='ADD',name='Mobile')=={'FINISHED'}
def refused(**kwargs):
    try:
        return bpy.ops.object.polygroups_smart_lods_preset(**kwargs)=={'CANCELLED'}
    except RuntimeError:
        return True
assert refused(action='ADD',name='mobile')
assert s.smart_lods_preset_active=='Mobile' and s.smart_lods_presets['Mobile'].count==4
s.smart_lods_target_1=1200
assert bpy.ops.object.polygroups_smart_lods_preset(action='SAVE')=={'FINISHED'}
assert s.smart_lods_presets['Mobile'].targets[0]==1200
s.smart_lods_preset_active='Unity'
assert s.smart_lods_count==5 and s.smart_lods_target_1==2900
s.smart_lods_preset_active='Mobile'
assert s.smart_lods_count==4 and s.smart_lods_target_1==1200
assert bpy.ops.object.polygroups_smart_lods_preset(action='REMOVE')=={'FINISHED'}
assert [x.name for x in s.smart_lods_presets]==['Unreal','Unity'] and s.smart_lods_preset_active==''
assert refused(action='SAVE')

# A deleted built-in falls back to its shipped values for the engine switch.
s.smart_lods_presets.remove(0)
p.phase2_run_engine='UNITY';p.phase2_run_engine='FAB'
assert s.smart_lods_count==6 and s.smart_lods_target_6==200
print('SMART_LODS_PRESETS_OK')
