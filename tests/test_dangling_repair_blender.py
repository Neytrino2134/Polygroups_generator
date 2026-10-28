"""Dangling sheets, folded tails, loose selection, protections and both queues."""
import sys
from pathlib import Path
import bpy,bmesh,addon_utils
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core.mesh_fold_repair import repair_local_folds
from polygroups_generator.operators.import_queue import ImportQueue
from polygroups_generator.operators.phase2_processing import Phase2Queue


def fixture(kind='sheet',scale=1):
 bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=2,radius=scale);bm.normal_update()
 face=max(bm.faces,key=lambda f:f.calc_center_median().z)
 a,b,c=list(face.verts)
 if kind=='tail':
  tip=bm.verts.new((a.co+b.co)/2+((a.co+b.co)/2-c.co)*4)
  bm.faces.remove(face)
  patch={bm.faces.new((a,b,tip)),bm.faces.new((a,tip,b,c))}
 elif kind=='cone':
  tip=bm.verts.new(face.calc_center_median()+face.normal*scale)
  bm.faces.remove(face)
  patch={bm.faces.new((a,b,tip)),bm.faces.new((b,c,tip)),bm.faces.new((c,a,tip))}
 else:
  tip=bm.verts.new((a.co+b.co)/2+face.normal*scale*.01)
  patch={bm.faces.new((a,b,tip))}
 for f in bm.faces:f.select_set(False)
 for f in patch:f.select_set(True)
 bm.normal_update()
 return bm,patch


def run(bm,**kw):
 return repair_local_folds(bm,fix_folds=False,fix_degenerate=False,fix_dangling=True,**kw)

for kind in ('sheet','tail'):
 for scale in (.001,1,1000):
  bm,patch=fixture(kind,scale)
  original={v:tuple(v.co) for v in bm.verts}
  result=run(bm)
  assert result['dangling_faces']==len(patch),(kind,result)
  assert result['dangling_filled']==(kind=='tail'),result
  assert all(e.is_manifold for e in bm.edges)
  assert all(tuple(v.co)==original[v] for v in bm.verts)
  assert run(bm)['dangling_faces']==0
  bm.free()
for kind in ('sheet','tail'):
 for protection in ('hidden','unselected','pin','uv_pin','disabled'):
  bm,patch=fixture(kind)
  if protection=='hidden':next(iter(patch)).hide_set(True)
  if protection=='unselected':
   for f in patch:f.select_set(False)
  if protection=='pin':
   pin=bm.edges.layers.int.new('polygroups_pin_edge');next(iter(patch)).edges[0][pin]=1
  if protection=='uv_pin':
   uv=bm.loops.layers.uv.new('UVMap');next(iter(patch)).loops[0][uv].pin_uv=True
  result=(repair_local_folds(bm,fix_folds=False,fix_degenerate=False) if protection=='disabled'
          else run(bm,selected_only=protection=='unselected'))
  assert not result.get('dangling_faces'),(kind,protection,result)
  bm.free()
bm,_=fixture('cone');assert run(bm)['dangling_faces']==0;bm.free()
# Standalone planar surfaces have no attachment to a solid; preserve them.
bm=bmesh.new();v=[bm.verts.new(p) for p in ((0,0,0),(1,0,0),(0,1,0))];bm.faces.new(v)
assert run(bm)['dangling_faces']==0;bm.free()

context=bpy.context;p=context.scene.polygroups_model_preparation_settings
assert p.fold_repair_dangling

def object_fixture():
 bm,_=fixture();mesh=bpy.data.meshes.new('Sheet');bm.to_mesh(mesh);bm.free()
 obj=bpy.data.objects.new('Retopo_02_Highpoly_Generated.998',mesh)
 col=bpy.data.collections.new('Sheet');context.scene.collection.children.link(col);col.objects.link(obj)
 context.view_layer.update();bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);context.view_layer.objects.active=obj
 return obj,col

for route in ('MANUAL','PHASE1','PHASE2'):
 for enabled in (False,True):
  obj,col=object_fixture();before=len(obj.data.polygons);p.fold_repair_dangling=enabled
  if route=='MANUAL':
   assert bpy.ops.mesh.polygroups_repair_mesh_folds(fix_folds=False,fix_degenerate=False,
    fix_stretched_triangles=False,fix_dangling=enabled)=={'FINISHED'}
  elif route=='PHASE1':
   q=ImportQueue.__new__(ImportQueue);q.settings=p;q.batch_stages=True;q.pass_method='QUAD';q.owned_meshes=set()
   for number in (2,3,4):
    q.pass_number=number;q.repair_completed_pass_geometry(context,[obj])
  else:
   q=Phase2Queue(context,[],False,False,lambda *_:None);q.collection=col
   p.phase2_mesh_auto_repair=True;q.repair_mesh(context,low=obj,repack=False)
  assert len(obj.data.polygons)==before-int(enabled),(route,enabled)
  bpy.data.objects.remove(obj,do_unlink=True)
p.fold_repair_dangling=True
# Find Problems must select wire-only debris without committing the working copy.
mesh=bpy.data.meshes.new('Wire');mesh.from_pydata([(0,0,0),(1,0,0),(3,0,0)],[(0,1)],[])
obj=bpy.data.objects.new('Wire',mesh);context.collection.objects.link(obj);context.view_layer.objects.active=obj;obj.select_set(True)
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT')=={'FINISHED'}
bm=bmesh.from_edit_mesh(mesh);assert all(v.select for v in bm.verts) and len(bm.verts)==3
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR')=={'FINISHED'}
assert len(bmesh.from_edit_mesh(mesh).verts)==0
bpy.ops.object.mode_set(mode='OBJECT')
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator import ui
context.scene.airetopo_panel_visibility_settings.topic_prepare_1=True
panel=capture(context,ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_model_preparation))
assert not panel.errors,panel.errors
assert 'fold_repair_dangling' in {b[2] for b in panel.bindings.values() if b[0]=='property'}
print('DANGLING_REPAIR_PROTECTIONS_AND_PIPELINES_OK',flush=True)
