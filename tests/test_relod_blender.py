"""ReLOD scene discovery, preservation, replacement, rollback and nested UI."""
import sys
from pathlib import Path
from unittest.mock import patch
import bpy,bmesh,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.relod import scene_sources,ReLODPlan
from polygroups_generator.operators.smart_lods import LOD_SOURCE,LOD_INDEX
from polygroups_generator.operators import sequential_jobs
from polygroups_generator.custom_ui.schema import capture
c=bpy.context;p=c.scene.polygroups_model_preparation_settings;s=c.scene.polygroups_mesh_finalization_settings
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s.smart_lods_count=2;s.smart_lods_target_1=50;s.smart_lods_target_2=20;s.smart_lods_create_text=True
s.smart_lods_auto_arrange=True;s.smart_lods_decimate_method='SMART_DECIMATE'
assert p.phase2_relod_method=='UV_PRESERVE'

def source(name):
 bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=2,radius=1)
 uv=bm.loops.layers.uv.new('UVMap')
 for f in bm.faces:
  for l in f.loops:l[uv].uv=(l.vert.co.x*.25+.5,l.vert.co.y*.25+.5)
 mesh=bpy.data.meshes.new(name);bm.to_mesh(mesh);bm.free();obj=bpy.data.objects.new(name,mesh);c.collection.objects.link(obj);return obj
mid=source('SM_Box_01_01_MID');high=source('SM_Box_01_01_HIGH');other=source('Other_HIGH')
assert scene_sources(c)==[other,mid]
mid.hide_viewport=True;mid.hide_set(True)
other.select_set(True);c.view_layer.objects.active=other
snapshot={o:(o.matrix_world.copy(),tuple(tuple(v.co) for v in o.data.vertices),tuple(tuple(l.uv) for l in o.data.uv_layers.active.data)) for o in (mid,high,other)}
assert bpy.ops.object.polygroups_relod()=={'FINISHED'}
assert p.phase2_relod_done==p.phase2_relod_total==2 and p.phase2_relod_progress==100
assert mid.hide_viewport and mid.hide_get() and c.active_object==other
assert s.smart_lods_decimate_method=='SMART_DECIMATE' and s.smart_lods_auto_arrange
for o,(matrix,positions,uvs) in snapshot.items():
 assert o.matrix_world==matrix and tuple(tuple(v.co) for v in o.data.vertices)==positions
 assert tuple(tuple(l.uv) for l in o.data.uv_layers.active.data)==uvs
for base in ('SM_Box_01_01','Other'):
 for i in range(2):
  obj=bpy.data.objects[base+'_LOD'+str(i)];assert obj.get(LOD_INDEX)==i and len(obj.data.polygons)>0
  src=mid if base.startswith('SM_') else other
  allowed={tuple(l.uv) for l in src.data.uv_layers.active.data}
  assert all(tuple(l.uv) in allowed for l in obj.data.uv_layers.active.data)
old={o.name:o.as_pointer() for o in c.scene.objects if '_LOD' in o.name}
try:bpy.ops.object.polygroups_relod()
except RuntimeError:pass
assert all(bpy.data.objects[name].as_pointer()==ptr for name,ptr in old.items())
p.phase2_relod_delete_current_lods=True
assert bpy.ops.object.polygroups_relod()=={'FINISHED'}
assert all(bpy.data.objects[name].as_pointer()!=ptr for name,ptr in old.items())
assert not any('.001' in o.name for o in c.scene.objects)
# Selected Only: a selected LOD resolves to its source; other packs stay untouched.
box={o.name:o.as_pointer() for o in c.scene.objects if o.name.startswith('SM_Box_01_01_LOD')}
others={o.name:o.as_pointer() for o in c.scene.objects if o.name.startswith('Other_LOD')}
bpy.ops.object.select_all(action='DESELECT');bpy.data.objects['Other_LOD0'].select_set(True)
assert bpy.ops.object.polygroups_relod(selected_only=True)=={'FINISHED'}
assert p.phase2_relod_total==1
assert all(bpy.data.objects[name].as_pointer()==ptr for name,ptr in box.items())
assert all(bpy.data.objects[name].as_pointer()!=ptr for name,ptr in others.items())
bpy.ops.object.select_all(action='DESELECT')
try:bpy.ops.object.polygroups_relod(selected_only=True)
except RuntimeError:pass
assert 'select a _MID' in p.phase2_relod_status
other.select_set(True);c.view_layer.objects.active=other
# Interrupted per-asset generation restores old meshes and labels, settings and hidden source.
plan=ReLODPlan(c,mid,True);old={o.name:o.as_pointer() for o in plan.old}
it=plan.steps(c,lambda *_:None);assert next(it)==1;it.close()
assert all(bpy.data.objects[name].as_pointer()==ptr for name,ptr in old.items())
assert mid.hide_viewport and mid.hide_get() and s.smart_lods_decimate_method=='SMART_DECIMATE'
# A generator failure must restore the old pack and clear all busy state.
from polygroups_generator.operators import smart_lods
old={o.name:o.as_pointer() for o in c.scene.objects if '_LOD' in o.name}
original_fit=smart_lods._fit_uv_preserve
calls=[]
def failing_fit(*args):
 calls.append(1)
 if len(calls)==2:raise RuntimeError('injected ReLOD failure')
 return original_fit(*args)
with patch.object(smart_lods,'_fit_uv_preserve',failing_fit):
 try:bpy.ops.object.polygroups_relod()
 except RuntimeError:pass
assert 'injected ReLOD failure' in p.phase2_relod_status
assert not p.phase2_relod_running and sequential_jobs.ACTIVE_JOB is None
assert all(bpy.data.objects[name].as_pointer()==ptr for name,ptr in old.items())
# Whole-list preflight must reject a later naming collision before replacing an earlier asset.
collision=bpy.data.objects.new('SM_Box_01_01_LOD0',None)
# Existing mesh owns that name; rename the unrelated object into the next planned level instead.
collision.name='Other_LOD2';c.collection.objects.link(collision);s.smart_lods_count=3
before={o.name:o.as_pointer() for o in c.scene.objects}
try:bpy.ops.object.polygroups_relod()
except RuntimeError:pass
assert before=={o.name:o.as_pointer() for o in c.scene.objects}
bpy.data.objects.remove(collision,do_unlink=True);s.smart_lods_count=2
# Swapped pack (MID named _LOD0, its LOD0 named _MID) is refused before any deletion.
real=source('SM_Swap_01_01_LOD0');fake=source('SM_Swap_01_01_MID')
bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=1,radius=1);bm.to_mesh(fake.data);bm.free()
for variant in ('tagged','untagged'):
 if variant=='tagged':fake[LOD_SOURCE]=real.name;fake[LOD_INDEX]=0
 else:del fake[LOD_SOURCE];del fake[LOD_INDEX]
 before={o.name:o.as_pointer() for o in c.scene.objects}
 try:bpy.ops.object.polygroups_relod()
 except RuntimeError:pass
 assert ('generated LOD0' if variant=='tagged' else 'looks like the real source') in p.phase2_relod_status,p.phase2_relod_status
 assert before=={o.name:o.as_pointer() for o in c.scene.objects}
for o in (real,fake):bpy.data.objects.remove(o,do_unlink=True)
# UI capture: all bars and statuses disappear when nested Status is collapsed.
p.phase2_pipeline_state='DONE';p.phase2_show_start=True;p.phase2_show_status=True;p.phase2_show_relod=True
panel=capture(c,1);assert not panel.errors,panel.errors
props={b[2] for b in panel.bindings.values() if b[0]=='property'}
assert {'phase2_show_status','phase2_show_relod','phase2_relod_method','phase2_relod_delete_current_lods'}<=props
assert any(b[0]=='operator' and b[1]=='object.polygroups_relod' for b in panel.bindings.values())
def walk(node):
 yield node
 for child in node.get('children',[]):yield from walk(child)
groups={n.get('text'):n for n in walk(panel.node) if n['kind']=='group'}
start=groups['Start Phase 2'];status=groups['Status and Statistics'];relod=groups['ReLOD']
assert status in start['children'] and relod in start['children']
assert start['children'].index(relod)<start['children'].index(status)
assert any(n['kind']=='progress' for n in walk(status))
assert not any(n['kind']=='progress' for n in start['children'] if n is not status)
print('RELOD_GENERATION_REPLACEMENT_ROLLBACK_AND_UI_OK',flush=True)
