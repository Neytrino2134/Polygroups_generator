"""Collection-boundary autosave counts successes, saves cleanup and stops on failure."""
import sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_processing as phase
ctx=bpy.context;p=ctx.scene.polygroups_model_preparation_settings
assert not p.phase2_autosave and p.phase2_autosave_every==1
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
for col in list(bpy.data.collections):bpy.data.collections.remove(col)
def collection(index):
 col=bpy.data.collections.new(f'Generated.{index:03d}');ctx.scene.collection.children.link(col)
 objects=[]
 for name in (f'Highpoly_Generated.{index:03d}',f'Retopo_12_Highpoly_Generated.{index:03d}'):
  data=bpy.data.meshes.new(name);data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
  obj=bpy.data.objects.new(name,data);col.objects.link(obj);objects.append(obj)
 return col,objects
real=bpy
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_phase2_autosave_') as folder:
 path=Path(folder)/'Working.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
 p.phase2_autosave=True;p.phase2_autosave_every=2;p.phase2_delete_high_after_bake=True
 errors=[False,True,False,False,True,False,False]
 q=phase.Phase2Queue(ctx,[('source',f'Generated.{i:03d}') for i in range(1,8)],True,False,lambda *args:None)
 q.begin();saves=[];current=[]
 def save(**kwargs):
  assert q.collection is None and q.stage=='RESTORE'
  assert current[0].hide_render and current[0].hide_viewport and current[0].color_tag=='COLOR_02'
  assert not any(phase.HIGH.fullmatch(o.name) for o in current[0].objects)
  saves.append(p.phase2_done_count)
  ctx.scene['checkpoint_collection_index']=q.index
  return real.ops.wm.save_as_mainfile(**kwargs)
 proxy=SimpleNamespace(data=real.data,ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=save)))
 with patch.object(phase,'bpy',proxy):
  for index,error in enumerate(errors,1):
   col,objects=collection(index);current[:]=[col]
   q.collection=col;q.stage='BAKE_WAIT';q.baked_pair=tuple(objects)
   q.complete('Injected processing failure' if error else '')
 q.finish()
 assert saves==[2,4],saves
 assert p.phase2_done_count==5 and p.phase2_failed_count==2
 assert p.phase2_autosave_status=='Autosaved after 4 successful collections'
 # Read the real checkpoint and verify that cleanup/exclusion preceded saving.
 bpy.ops.wm.open_mainfile(filepath=str(path))
 p=ctx.scene.polygroups_model_preparation_settings
 assert ctx.scene['checkpoint_collection_index']==6
 assert 'Generated.006' in bpy.data.collections and 'Generated.007' not in bpy.data.collections
 assert bpy.data.collections['Generated.006'].hide_viewport
 assert 'Highpoly_Generated.006' not in bpy.data.objects
 # Save failure must not turn a successful collection into a second completion.
 p.phase2_autosave=True;p.phase2_autosave_every=1
 q=phase.Phase2Queue(ctx,[('source','Generated.010'),('source','Generated.011')],False,False,lambda *args:None)
 q.begin();q.collection=collection(10)[0]
 proxy=SimpleNamespace(data=real.data,ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=lambda **kwargs:{'CANCELLED'})))
 with patch.object(phase,'bpy',proxy):q.complete()
 assert q.index==1 and p.phase2_done_count==1 and p.phase2_failed_count==0 and q.stop_requested
 q.step(ctx)
 assert q.finished and 'Autosave failed' in p.phase2_status
 assert 'Generated.011' not in bpy.data.collections
 from polygroups_generator.custom_ui.schema import capture
 assert not capture(ctx,1).errors
print('PHASE2_PERIODIC_COLLECTION_AUTOSAVE_PASSED')
