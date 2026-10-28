"""Real current-scene MID variants: core and public Find/Repair/Quality, read-only input.
Open the diagnostic library snapshot containing both MID objects before running.
"""
import sys
from pathlib import Path
import addon_utils,bpy,bmesh
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core.mesh_fold_repair import repair_local_folds
c=bpy.context

def signature(bm):
 for seq in (bm.verts,bm.edges,bm.faces):seq.index_update()
 layers=list(bm.loops.layers.uv.values())
 return (tuple(tuple(v.co) for v in bm.verts),
  tuple((tuple(v.index for v in e.verts),e.seam,e.smooth) for e in bm.edges),
  tuple((tuple(v.index for v in f.verts),f.material_index,tuple(tuple(tuple(l[layer].uv) for l in f.loops) for layer in layers)) for f in bm.faces))

final_geometry=[]
for name in ('SM_Containers_01_01_MID','SM_Containers_01_01_MID.001'):
 original=bpy.data.objects.get(name);assert original is not None,'Current-scene snapshot must include '+name
 bm=bmesh.new();bm.from_mesh(original.data)
 for seq in (bm.faces,bm.edges,bm.verts):seq.index_update()
 selected={f.index for f in bm.faces if f.select}
 positions={v:tuple(v.co) for v in bm.verts};layers=list(bm.loops.layers.uv.values())
 uvs={f:tuple(tuple(tuple(l[layer].uv) for l in f.loops) for layer in layers) for f in bm.faces}
 result=repair_local_folds(bm,fix_dangling=True,fix_stretched_triangles=True,selected_only=True)
 assert result['dangling_faces']==(23 if name.endswith('_MID') else 22),(name,result)
 assert selected<=result['affected'],(name,selected-result['affected'])
 assert result['dangling_filled']==1
 assert sum(not e.is_manifold for e in bm.edges)==4
 assert all(tuple(v.co)==positions[v] for v in bm.verts)
 assert all(tuple(tuple(tuple(l[layer].uv) for l in f.loops) for layer in layers)==values for f,values in uvs.items() if f.is_valid)
 final_geometry.append((sorted(tuple(v.co) for v in bm.verts),sorted(tuple(sorted(tuple(v.co) for v in f.verts)) for f in bm.faces)))
 expected=result['affected'];bm.free()
 # Test operators on disposable copies; original objects/datablocks are untouched.
 obj=bpy.data.objects.new('Repair regression',original.data.copy());c.scene.collection.objects.link(obj)
 c.view_layer.update();bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);c.view_layer.objects.active=obj
 bm=bmesh.new();bm.from_mesh(obj.data);before=signature(bm);bm.free()
 assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT')=={'FINISHED'}
 edit=bmesh.from_edit_mesh(obj.data);assert signature(edit)==before
 assert {f.index for f in edit.faces if f.select}==expected,(name,expected,{f.index for f in edit.faces if f.select})
 assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR',selected_only=True)=={'FINISHED'}
 edit=bmesh.from_edit_mesh(obj.data);after=signature(edit)
 assert len(edit.faces)==6276 and len(edit.verts)==6267,(name,len(edit.faces),len(edit.verts))
 assert sum(not e.is_manifold for e in edit.edges)==4
 assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR')=={'FINISHED'}
 assert signature(bmesh.from_edit_mesh(obj.data))==after
 assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT')=={'FINISHED'}
 assert not any(f.select for f in bmesh.from_edit_mesh(obj.data).faces)
 assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT_QUALITY')=={'FINISHED'}
 assert signature(bmesh.from_edit_mesh(obj.data))==after
 bpy.ops.object.mode_set(mode='OBJECT');mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
 for route in ('PHASE1','PHASE2'):
  obj=bpy.data.objects.new('Retopo_02_Highpoly_Generated.999',original.data.copy());c.scene.collection.objects.link(obj)
  c.view_layer.update();bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);c.view_layer.objects.active=obj
  p=c.scene.polygroups_model_preparation_settings
  if route=='PHASE1':
   from polygroups_generator.operators.import_queue import ImportQueue
   q=ImportQueue.__new__(ImportQueue);q.settings=p;q.batch_stages=True;q.pass_method='QUAD';q.pass_number=2;q.owned_meshes=set()
   p.batch_first_geometry_repair=True;q.repair_completed_pass_geometry(c,[obj])
  else:
   from polygroups_generator.operators.phase2_processing import Phase2Queue
   q=Phase2Queue(c,[],False,False,lambda *_:None);q.collection=c.scene.collection
   p.phase2_mesh_auto_repair=True;q.repair_mesh(c,low=obj,repack=False)
  assert len(obj.data.polygons)==6276 and len(obj.data.vertices)==6267,(name,route)
  mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
 print('LIVE_CONTAINER_FIND_REPAIR_QUALITY_AND_PHASES_OK',name,flush=True)
assert final_geometry[0]==final_geometry[1],'Both variants must produce the same retained surface'
print('BOTH_LIVE_CONTAINER_VARIANTS_IDENTICAL_REPAIRED_SURFACE_OK',flush=True)
