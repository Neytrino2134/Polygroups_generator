"""Actual installed MID remesher: seams/pins reset, next stage and queue handoff."""
import sys,time,math
from pathlib import Path
from unittest.mock import patch
import bpy,bmesh,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable('quad_remesher',default_set=False)
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_processing as phase2
from polygroups_generator.pin_edges import pin_layer
ctx=bpy.context;p=ctx.scene.polygroups_model_preparation_settings
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
col=bpy.data.collections.new('Generated.074');ctx.scene.collection.children.link(col)
for name in ('Highpoly_Generated.074','Retopo_01_Highpoly_Generated.074','Retopo_12_Highpoly_Generated.074'):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12)
 obj=ctx.object;obj.name=name
 for old in list(obj.users_collection):old.objects.unlink(obj)
 col.objects.link(obj)
source=ctx.object
bpy.ops.object.mode_set(mode='EDIT');bm=bmesh.from_edit_mesh(source.data);pins=pin_layer(bm,True)
for edge in bm.edges:edge.seam=True;edge[pins]=1
for face in bm.faces:
 for loop in face.loops:loop[bm.loops.layers.uv.active].pin_uv=True
bmesh.update_edit_mesh(source.data);bpy.ops.object.mode_set(mode='OBJECT')
seams=ctx.scene.polygroups_seam_preparation_settings
seams.smart_seam_angle_limit=math.radians(47);seams.smart_seam_pin_generated=False
qsettings=ctx.scene.qremesher;qsettings.target_count=789
p.phase2_mesh_auto_repair=False;p.phase2_mid_remesh=True;p.phase2_repack_after_repair=True
p.remesh_pregenerate_polygroups=False
# Topology Guard always ends with a UVPackmaster PACK, which is not installed here.
p.phase2_topology_guard_highest=False
queue=phase2.Phase2Queue(ctx,[('test',col.name)],False,False,print)
packed=[]
def pack(context,low=None):
 result=phase2.bake_pair(col)[1];packed.append(result.name)
 assert result.name=='Retopo_13_Highpoly_Generated.074'
 assert result.data.uv_layers.active is not None
queue.begin()
with patch.object(phase2,'restore_collection',return_value=col),patch.object(queue,'repack_mesh',side_effect=pack):
 deadline=time.monotonic()+90
 while not queue.finished and time.monotonic()<deadline:
  queue.step(ctx);time.sleep(.1)
 if not queue.finished:queue.finish(stopped=True);raise AssertionError('Remesh timed out')
assert p.phase2_done_count==1 and p.phase2_failed_count==0,queue.results
assert packed==['Retopo_13_Highpoly_Generated.074'],packed
assert qsettings.target_count==789
assert abs(seams.smart_seam_angle_limit-math.radians(47))<1e-6
assert not any(item.value for item in source.data.attributes['polygroups_pin_edge'].data)
assert not any(loop.pin_uv for loop in source.data.uv_layers.active.data)
assert not all(edge.use_seam for edge in source.data.edges)
# Cancellation and engine failures must abort the pending job before packing/baking.
from polygroups_generator.operators import phase2_mid_remesh as adapter
for fail in (False,True):
 class Pending:
  aborted=False
  def __init__(self,*args):pass
  def start(self,context):pass
  def poll(self):raise RuntimeError('test engine failure')
  def abort(self):self.aborted=True
 job=Pending()
 queue=phase2.Phase2Queue(ctx,[('test',col.name)],True,False,lambda *args:None)
 queue.begin()
 with patch.object(phase2,'restore_collection',return_value=col),patch.object(adapter,'Phase2MidRemesh',return_value=job),patch.object(queue,'repack_mesh') as pack_call:
  queue.step(ctx);assert queue.stage=='MID_REMESH_WAIT'
  if not fail:queue.stop_requested=True
  queue.step(ctx);queue.step(ctx)
  assert queue.finished and job.aborted
  assert not pack_call.called
  assert p.phase2_failed_count==int(fail)
print('PHASE2_NATIVE_MID_REMESH_PASSED')
