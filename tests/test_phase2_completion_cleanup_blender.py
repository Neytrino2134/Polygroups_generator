"""Phase 2 successful-bake cleanup, failure preservation, backup object cleanup."""
import sys
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.operators import phase2_processing as phase
context=bpy.context;s=context.scene.polygroups_model_preparation_settings
s.phase2_delete_high_after_bake=s.phase2_delete_lower_retopo=True

def fixture(index):
 col=bpy.data.collections.new(f'Generated.{index:03d}');context.scene.collection.children.link(col)
 objects=[]
 for name in (f'Highpoly_Generated.{index:03d}',f'Retopo_02_Highpoly_Generated.{index:03d}',f'Retopo_12_Highpoly_Generated.{index:03d}'):
  data=bpy.data.meshes.new(name);data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
  obj=bpy.data.objects.new(name,data);col.objects.link(obj);objects.append(obj)
 context.view_layer.update()
 q=phase.Phase2Queue(context,[('fixture',col.name)],True,False,lambda *a:None)
 q.begin();q.collection=col;q.stage='BAKE_WAIT';q.baked_pair=(objects[0],objects[2])
 return q,col,objects
q,col,objs=fixture(401);names=[o.name for o in objs];q.complete()
assert names[0] not in bpy.data.objects and names[1] not in bpy.data.objects
assert names[2] in bpy.data.objects
assert not col.hide_render and not col.hide_viewport
layer=next(c for c in context.view_layer.layer_collection.children if c.collection==col)
assert not layer.exclude
q,col,objs=fixture(402);names=[o.name for o in objs];q.complete('injected bake failure')
assert all(n in bpy.data.objects for n in names)
assert not col.hide_render and not col.hide_viewport
q,col,objs=fixture(403);names=[o.name for o in objs];q.stage='RESTORE';q.baked_pair=None;q.complete()
assert all(n in bpy.data.objects for n in names) # no bake: do not delete
# Shared external object is unlinked only from completed collection.
q,col,objs=fixture(404);source=objs[0];context.scene.collection.objects.link(source);name=source.name;q.complete()
assert name in bpy.data.objects and source.name not in col.objects
q.finish()
context.view_layer.update()
shared=bpy.data.meshes.new('Backup shared');keep=bpy.data.objects.new('Keep_Retopo',shared);context.scene.collection.objects.link(keep)
for name in ('Backup_Retopo_A','Backup_Retopo_12_Highpoly_Generated.001'):
 obj=bpy.data.objects.new(name,shared);context.scene.collection.objects.link(obj)
assert bpy.ops.object.polygroups_phase2_clear_backups()=={'FINISHED'}
assert not any(o.name.startswith('Backup_Retopo_') for o in bpy.data.objects)
assert keep.name in bpy.data.objects and shared.users==1
# Manual cleanup works in disabled collections and keeps each asset's max stage.
s.phase2_delete_high_after_bake=s.phase2_delete_lower_retopo=False
q,col,objs=fixture(405);names405=[o.name for o in objs];q.complete();q.finish()
q,col,objs=fixture(406);names406=[o.name for o in objs];q.complete();q.finish()
assert bpy.ops.object.polygroups_phase2_clear_lower_retopo()=={'FINISHED'}
for names in (names405,names406):
 assert names[1] not in bpy.data.objects and names[2] in bpy.data.objects
 assert names[0] in bpy.data.objects
assert bpy.ops.object.polygroups_phase2_clear_highpoly()=={'FINISHED'}
assert not any(phase.HIGH.fullmatch(o.name) for o in bpy.data.objects if o.type=='MESH')
assert all(names[2] in bpy.data.objects for names in (names405,names406))
assert keep.name in bpy.data.objects
assert not s.phase2_keep_retopo01
for manual in (False,True):
 for keep in (True,False):
  s.phase2_keep_retopo01=keep
  s.phase2_delete_lower_retopo=True
  q,col,objs=fixture(500+int(manual)*10+int(keep))
  objs[1].name=objs[1].name.replace('Retopo_02_','Retopo_01_')
  first=objs[1].name;highest=objs[2].name
  if manual:
   q.finish()
   assert bpy.ops.object.polygroups_phase2_clear_lower_retopo()=={'FINISHED'}
  else:
   q.complete();q.finish()
  assert (first in bpy.data.objects)==keep
  assert highest in bpy.data.objects
s.phase2_keep_retopo01=True
s.phase2_show_manual_cleanup=True
from polygroups_generator.custom_ui.schema import capture
assert not capture(context,1).errors
print('PHASE2_COMPLETION_CLEANUP_PASSED')
