"""Restore renamed Resculpting stages and apply shared lower-stage retention."""
import sys,tempfile
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_processing as phase,safety_checks
ctx=bpy.context;p=ctx.scene.polygroups_model_preparation_settings
col=bpy.data.collections.new('Generated.007')
for name in ('Highpoly_Generated.007','Resculpting_01_Highpoly_Generated.007',
             'Retopo_12_Highpoly_Generated.007','Backup_Resculpting_01_Highpoly_Generated.007'):
 data=bpy.data.meshes.new(name);data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
 col.objects.link(bpy.data.objects.new(name,data))
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_resculpt_names_') as folder:
 path=str(Path(folder)/'Source.blend');bpy.data.libraries.write(path,{col})
 p.phase2_skip_retopo_backups=True
 imported=phase.restore_collection(path,'Generated.007',ctx.scene)
 sculpt=next(o for o in imported.objects if o.name.startswith('Resculpting_01_'))
 high,low=phase.bake_pair(imported)
 assert low.name.startswith('Retopo_12_')
 assert safety_checks.is_lowpoly_name(sculpt.name)
 assert safety_checks.find_matching_highpoly(sculpt)[0]==high
 assert not any(o.name.startswith('Backup_') for o in imported.objects)
 p.phase2_keep_retopo01=True
 assert bpy.ops.object.polygroups_phase2_clear_lower_retopo()=={'FINISHED'}
 name=sculpt.name;assert name in bpy.data.objects
 p.phase2_keep_retopo01=False
 assert bpy.ops.object.polygroups_phase2_clear_lower_retopo()=={'FINISHED'}
 assert name not in bpy.data.objects and low.name in bpy.data.objects
data=bpy.data.meshes.new('Manual rename geometry')
objects=[]
for name in ('Retopo_01_Manual_A','Retopo_01_Manual_B','Retopo_010_Untouched','Retopo_02_Untouched','Resculpting_01_Manual_B'):
 obj=bpy.data.objects.new(name,data);ctx.scene.collection.objects.link(obj);objects.append(obj)
objects[0].hide_viewport=True
assert bpy.ops.object.polygroups_phase2_rename_retopo01()=={'CANCELLED'}
assert objects[0].name=='Retopo_01_Manual_A' and objects[1].name=='Retopo_01_Manual_B'
bpy.data.objects.remove(objects[-1],do_unlink=True)
assert bpy.ops.object.polygroups_phase2_rename_retopo01()=={'FINISHED'}
assert objects[0].name=='Resculpting_01_Manual_A' and objects[1].name=='Resculpting_01_Manual_B'
assert objects[0].hide_viewport and objects[0].data==data
assert objects[2].name=='Retopo_010_Untouched' and objects[3].name=='Retopo_02_Untouched'
assert bpy.ops.object.polygroups_phase2_rename_retopo01()=={'FINISHED'}
from polygroups_generator.custom_ui.schema import capture
p.phase2_show_manual_cleanup=True
assert not capture(ctx,1).errors
print('RESCULPTING_RESTORE_NAMES_AND_RETENTION_PASSED')
