"""Regression for the co-oriented crossed quad in Asset_00_07."""
import json
import sys
from pathlib import Path
import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds, inspect_triangle_quality

obj = bpy.data.objects['SM_Asset_00_07_MID']
if obj.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bm = bmesh.new()
bm.from_mesh(obj.data)
for seq in (bm.verts, bm.edges, bm.faces):
    seq.ensure_lookup_table()
    seq.index_update()
triangle, quad, tip = bm.faces[3899], bm.faces[392], bm.verts[121]
target = min((e.other_vert(tip) for e in tip.link_edges), key=lambda v:(v.co-tip.co).length_squared)
target_index = target.index
positions = {v:tuple(v.co) for v in bm.verts if v != tip}
layers = list(bm.loops.layers.uv.values())
snapshot = {f:tuple((loop.vert, tuple(tuple(loop[layer].uv) for layer in layers)) for loop in f.loops)
            for f in bm.faces if f not in {triangle, quad}}
for face in bm.faces:
    face.select_set(face == triangle)
before = inspect_triangle_quality(bm)[1]
full = bm.copy()
full_result = repair_local_folds(full,fix_zero_area=True,fix_stretched_triangles=True)
assert full_result['folds']==1 and full_result['stretched']==0,full_result
assert all(edge.is_manifold for edge in full.edges)
full.free()
result = repair_local_folds(bm, selected_only=True)
assert result['folds'] == 1 and result['affected'] == {392, 3899}, result
assert not tip.is_valid and target.is_valid
assert all(v.is_valid and tuple(v.co) == co for v,co in positions.items())
assert all(f.is_valid and tuple((loop.vert,tuple(tuple(loop[layer].uv) for layer in layers))
                               for loop in f.loops) == corners for f,corners in snapshot.items())
assert all(edge.is_manifold for edge in bm.edges)
assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (3924, 7909, 3987)
after = inspect_triangle_quality(bm)[1]
assert after['uv_triangles'] == 0, after
assert repair_local_folds(bm, selected_only=True)['folds'] == 0
print('ASSET007_DIRECTED_WELD_OK', json.dumps(dict(before=before,after=after,
      target=target_index,unchanged_faces=len(snapshot))),flush=True)
from polygroups_generator.operators.repair_mesh_folds import MESH_OT_polygroups_repair_mesh_folds
bpy.utils.register_class(MESH_OT_polygroups_repair_mesh_folds)
for other in bpy.context.selected_objects:other.select_set(False)
obj.select_set(True);bpy.context.view_layer.objects.active=obj
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT',fix_zero_area=True)=={'FINISHED'}
selected=bmesh.from_edit_mesh(obj.data);selected.faces.index_update()
assert {face.index for face in selected.faces if face.select}=={392,3899}
assert len(selected.verts)==3925
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR',fix_zero_area=True)=={'FINISHED'}
bpy.ops.object.mode_set(mode='OBJECT')
assert (len(obj.data.vertices),len(obj.data.edges),len(obj.data.polygons))==(3924,7909,3987)
bpy.utils.unregister_class(MESH_OT_polygroups_repair_mesh_folds)
print('ASSET007_PUBLIC_FIND_REPAIR_OK',flush=True)
if '--' in sys.argv:
    output = Path(sys.argv[sys.argv.index('--')+1])
    assert not output.exists() and output.resolve() != Path(bpy.data.filepath).resolve()
    bm.to_mesh(obj.data)
    obj.data.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    print('SAVED_REPAIRED_ASSET007', str(output),flush=True)
bm.free()
