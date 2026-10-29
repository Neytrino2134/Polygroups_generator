"""Secondary Retopo_01 stages: ordering, forced repack and deferred cleanup."""
import sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_processing as phase2
from polygroups_generator.operators.resculpting import MULTIRES_MODIFIER_NAME
ctx=bpy.context;p=ctx.scene.polygroups_model_preparation_settings;bake=ctx.scene.polygroups_baking_settings
assert not p.phase2_resculpt_retopo01 and not p.phase2_autobake_retopo01
assert all(getattr(p, key) for key in ("phase2_scan_subfolders", "phase2_skip_retopo_backups", "phase2_mid_remesh", "phase2_delete_high_after_bake", "phase2_delete_lower_retopo"))
assert not p.phase2_keep_retopo01 and not p.phase2_high_remesh_before_resculpting
p.phase2_keep_retopo01=True
p.phase2_mid_remesh=False
real=bpy
p.batch_stage_4_topology_guard=False
p.phase2_mesh_auto_repair=True;p.phase2_repack_after_repair=True
p.phase2_delete_high_after_bake=True;p.phase2_delete_lower_retopo=True;p.phase2_blend_export_generated=False
ctx.scene.polygroups_resculpting_settings.multires_levels=1
def fixture():
 for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
 for col in list(bpy.data.collections):bpy.data.collections.remove(col)
 col=bpy.data.collections.new('Generated.001');ctx.scene.collection.children.link(col)
 result=[]
 for name in ('Highpoly_Generated.001',*[f'Retopo_{i:02d}_Highpoly_Generated.001' for i in (1,2,3)]):
  bpy.ops.mesh.primitive_cube_add();obj=ctx.object;obj.name=name
  for old in list(obj.users_collection):old.objects.unlink(obj)
  col.objects.link(obj);result.append(obj)
 return col,result
def run(resculpt,rebake,failure='',stop_when=''):
 col,objects=fixture();high,low01,low02,highest=objects
 names=[o.name for o in objects];events=[]
 primary_multires=highest.modifiers.new('Primary Multires unchanged','MULTIRES')
 p.phase2_resculpt_retopo01=resculpt;p.phase2_autobake_retopo01=rebake
 original=(bake.bake_artifact_mask,bake.bake_artifact_autofill,bake.auto_save_textures_after_bake)
 def repair(*args,**kwargs):events.append(('repair',ctx.active_object.name));return {'FINISHED'}
 def pack(*args,**kwargs):
  assert ctx.active_object in (low01,objects[3])
  events.append(('pack',ctx.active_object.name));return {'CANCELLED'} if failure=='pack' and ctx.active_object==low01 else {'FINISHED'}
 def sculpt(*args,**kwargs):
  assert ctx.active_object==low01 and high.name in bpy.data.objects
  events.append(('sculpt',low01.name))
  return real.ops.object.polygroups_setup_resculpting(*args,**kwargs)
 def start_bake(*args,**kwargs):
  target=ctx.active_object
  assert target in (highest,low01) and high.name in bpy.data.objects
  assert set(ctx.selected_objects)=={high,target}
  assert bake.bake_artifact_mask and bake.bake_artifact_autofill
  assert bake.auto_save_textures_after_bake
  assert primary_multires.show_viewport and primary_multires.show_render
  if target==low01 and resculpt:
   modifier=low01.modifiers[MULTIRES_MODIFIER_NAME]
   assert not modifier.show_viewport and not modifier.show_render
  events.append(('bake',target.name))
  bake.bake_task_is_running=False
  bake.bake_task_stage='FAILED' if target==low01 and failure=='bake' else 'DONE'
  return {'FINISHED'}
 def fake_guard(context,obj,*args,**kwargs):
  assert obj==low01 and not low01.modifiers.get(MULTIRES_MODIFIER_NAME) and kwargs['unwrap']
  events.append(('guard',obj.name));return SimpleNamespace(timed_out=False,knots=0),0,3
 proxy=SimpleNamespace(data=real.data,ops=SimpleNamespace(
  mesh=SimpleNamespace(polygroups_repair_mesh_folds=repair),
  object=SimpleNamespace(polygroups_uvpackmaster_pack=pack,mode_set=lambda **kw:None,
   polygroups_setup_resculpting=sculpt,polygroups_checked_prepare_and_bake=start_bake)))
 q=phase2.Phase2Queue(ctx,[('mock-source.blend',col.name)],True,True,lambda *args:None);q.begin()
 with patch.object(phase2,'restore_collection',return_value=col),patch.object(phase2,'bpy',proxy),\
   patch.object(phase2,'apply_topology_guard',fake_guard):
  for _ in range(25):
   if q.stage==stop_when:q.stop_requested=True
   q.step(ctx)
   if q.finished:break
 assert q.finished and not p.phase2_is_running
 assert original==(bake.bake_artifact_mask,bake.bake_artifact_autofill,bake.auto_save_textures_after_bake)
 assert events[0:3]==[('repair',names[3]),('pack',names[3]),('bake',names[3])]
 if stop_when:
  assert p.phase2_status.startswith('Stopped') and names[0] in bpy.data.objects
  assert p.phase2_done_count==0 and p.phase2_failed_count==0
  return events
 if resculpt:
  assert ('sculpt',names[1]) in events
  assert low01.modifiers.get(MULTIRES_MODIFIER_NAME) is not None
  assert low01.modifiers[MULTIRES_MODIFIER_NAME].show_viewport == bool(failure)
  assert low01.modifiers[MULTIRES_MODIFIER_NAME].show_render == bool(failure)
 processed_name=names[1].replace('Retopo_','Resculpting_',1) if resculpt else names[1]
 if rebake:
  assert ('repair',processed_name) in events and ('pack',processed_name) in events
  if failure!='pack':assert ('bake',processed_name) in events
 if failure:
  assert p.phase2_failed_count==1 and names[0] in bpy.data.objects and names[2] in bpy.data.objects
 else:
  assert p.phase2_done_count==1 and names[0] not in bpy.data.objects and names[2] not in bpy.data.objects
  assert processed_name in bpy.data.objects and names[3] in bpy.data.objects
  assert not col.hide_render and not col.hide_viewport
  if resculpt:assert low01.hide_viewport and low01.hide_render and low01.hide_get()
 return events
for resculpt,rebake in ((True,True),(True,False),(False,True)):
 events=run(resculpt,rebake)
 if resculpt and rebake:
  assert [kind for kind,name in events]==['repair','pack','bake','sculpt','repair','pack','bake']
# Topology Guard fixes Retopo_01 UV before its Multires and bake, then the UV is repacked.
p.batch_stage_4_topology_guard=True
events=run(True,True)
assert [kind for kind,name in events]==['repair','pack','bake','guard','pack','sculpt','repair','pack','bake'],events
events=run(False,True)
assert [kind for kind,name in events]==['repair','pack','bake','guard','pack','repair','pack','bake'],events
p.batch_stage_4_topology_guard=False
run(True,True,'bake');run(False,True,'pack')
run(True,True,stop_when='RETOPO01_RESCULPT')
# An in-flight secondary bake keeps Multires disabled until it actually ends.
col,objects=fixture();high,low01,low02,highest=objects
modifier=low01.modifiers.new('Visibility restore test','MULTIRES')
modifier.show_viewport=True;modifier.show_render=False
def async_bake(*args,**kwargs):
 bake.bake_task_is_running=True
 return {'RUNNING_MODAL'}
proxy=SimpleNamespace(data=real.data,ops=SimpleNamespace(object=SimpleNamespace(polygroups_checked_prepare_and_bake=async_bake)))
q=phase2.Phase2Queue(ctx,[('mock',col.name)],True,True,lambda *args:None)
q.begin();q.collection=col;q.retopo01=low01
with patch.object(phase2,'bpy',proxy):
 q.start_bake(ctx,target=low01);q.stage='RETOPO01_BAKE_WAIT';q.stop_requested=True
 q.step(ctx)
 assert not q.finished and not modifier.show_viewport and not modifier.show_render
 bake.bake_task_is_running=False;bake.bake_task_stage='DONE'
 q.step(ctx);q.step(ctx)
assert q.finished and p.phase2_status.startswith('Stopped')
assert modifier.show_viewport and not modifier.show_render
assert not q.saved_multires_visibility
# Real CPU Cycles normal + artifact-mask/Autofill bakes on both targets.
from polygroups_generator.operators import baking
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
for col in list(bpy.data.collections):bpy.data.collections.remove(col)
col=bpy.data.collections.new('Generated.009')
for name,z in (('Highpoly_Generated.009',.05),('Retopo_01_Highpoly_Generated.009',0),('Retopo_12_Highpoly_Generated.009',0)):
 data=bpy.data.meshes.new(name)
 data.from_pydata([(-1,-1,z),(1,-1,z),(1,1,z),(-1,1,z)],[],[(0,1,2,3)])
 uv=data.uv_layers.new()
 for loop,xy in zip(uv.data,((0,0),(1,0),(1,1),(0,1))):loop.uv=xy
 col.objects.link(bpy.data.objects.new(name,data))
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_native_retopo01_') as folder:
 path=Path(folder);source=path/'Source.blend'
 bpy.data.libraries.write(str(source),{col})
 for obj in list(col.objects):bpy.data.objects.remove(obj,do_unlink=True)
 bpy.data.collections.remove(col)
 bpy.ops.wm.save_as_mainfile(filepath=str(path/'Working.blend'))
 p.phase2_resculpt_retopo01=p.phase2_autobake_retopo01=True
 p.phase2_mesh_auto_repair=p.phase2_repack_after_repair=False
 bake.bake_resolution=32;bake.bake_normal=True;bake.bake_base_color=False
 bake.auto_pack_uv_before_bake=False
 bake.use_smart_cage=bake.autogenerate_smart_cage=False;bake.use_auto_cage=True
 ctx.scene.render.engine='CYCLES';ctx.scene.cycles.device='CPU';ctx.scene.cycles.samples=1
 p.phase2_autosave=True;p.phase2_autosave_every=1
 q=phase2.Phase2Queue(ctx,[(str(source),'Generated.009')],True,True,lambda *args:None);q.begin()
 with patch.object(q,'autosave_completed',wraps=q.autosave_completed) as save_boundary:
  for _ in range(30):
   q.step(ctx)
   if q.finished:break
  assert save_boundary.call_count==1
 assert q.finished and p.phase2_done_count==1 and p.phase2_failed_count==0,q.results
 assert p.phase2_autosave_status=='Autosaved after 1 successful collections'
 targets=[o for o in bpy.data.objects if phase2.LOW.fullmatch(o.name)]
 assert len(targets)==2 and any(o.name.startswith('Resculpting_01_') for o in targets)
 assert all(o.get(baking.BAKE_NORMAL_IMAGE_PROP) for o in targets)
 resculpted=next(o for o in targets if o.name.startswith('Resculpting_01_'))
 assert resculpted.hide_viewport and resculpted.hide_render and resculpted.hide_get()
 assert all(not m.show_viewport and not m.show_render for m in resculpted.modifiers if m.type=='MULTIRES')
 from polygroups_generator.core.bake_projection import current_mask
 assert all(current_mask(o,bpy.data.images[o[baking.BAKE_NORMAL_IMAGE_PROP]]) is not None for o in targets)
 assert not any(phase2.HIGH.fullmatch(o.name) for o in bpy.data.objects)
 assert len(list(path.rglob('*_Normal.png')))==2
from polygroups_generator.custom_ui.schema import capture
assert not capture(ctx,1).errors
print('PHASE2_RETOPO01_RESCULPT_REBAKE_REPACK_CLEANUP_PASSED')
