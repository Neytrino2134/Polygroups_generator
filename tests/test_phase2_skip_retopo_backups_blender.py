"""Phase 2 may omit imported Backup_Retopo objects without deleting old data."""
import sys,tempfile
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.phase2_processing import restore_collection,LOW,HIGH
ctx=bpy.context;p=ctx.scene.polygroups_model_preparation_settings
assert not p.phase2_skip_retopo_backups
data=bpy.data.meshes.new('Shared source geometry')
data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
col=bpy.data.collections.new('Generated.007')
child=bpy.data.collections.new('Backup Child');col.children.link(child)
for name,owner in (('Highpoly_Generated.007',col),('Retopo_12_Highpoly_Generated.007',col),
                   ('Backup_Retopo_12_Highpoly_Generated.007',col),('Backup_Retopo_01_Highpoly_Generated.007',child)):
 owner.objects.link(bpy.data.objects.new(name,data))
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_skip_backups_') as folder:
 source=str(Path(folder)/'Source.blend');bpy.data.libraries.write(source,{col})
 for obj in list(col.all_objects):bpy.data.objects.remove(obj,do_unlink=True)
 bpy.data.collections.remove(child);bpy.data.collections.remove(col)
 # An existing, identically named backup must survive subsequent restores.
 existing=bpy.data.objects.new('Backup_Retopo_12_Highpoly_Generated.007',data)
 ctx.scene.collection.objects.link(existing)
 retained=restore_collection(source,'Generated.007',ctx.scene)
 old_backups={obj for obj in retained.all_objects if obj.name.startswith('Backup_Retopo_')}
 assert len(old_backups)==2
 before=set(bpy.data.objects)
 p.phase2_skip_retopo_backups=True
 imported=restore_collection(source,'Generated.007',ctx.scene)
 assert not any(obj.name.lower().startswith('backup_retopo_') for obj in imported.all_objects)
 assert len([o for o in imported.all_objects if LOW.fullmatch(o.name) or HIGH.fullmatch(o.name)])==2
 assert existing in set(bpy.data.objects) and old_backups<=set(bpy.data.objects)
 assert existing.data==data
 assert not any(obj.name.startswith('Backup_Retopo_') for obj in set(bpy.data.objects)-before)
 assert all(obj.data in set(bpy.data.meshes) for obj in imported.all_objects if obj.type=='MESH')
 from polygroups_generator.custom_ui.schema import capture
 assert not capture(ctx,1).errors
print('PHASE2_SKIP_IMPORTED_RETOPO_BACKUPS_PASSED')
