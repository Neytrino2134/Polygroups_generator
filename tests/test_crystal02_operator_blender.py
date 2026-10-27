"""Exercise Find and Repair on the reported crystal02 through the public operator."""
from pathlib import Path
import sys
import bpy,bmesh
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.operators.repair_mesh_folds import MESH_OT_polygroups_repair_mesh_folds
from polygroups_generator.core.mesh_fold_repair import inspect_triangle_quality
bpy.utils.register_class(MESH_OT_polygroups_repair_mesh_folds)
obj=bpy.data.objects['SM_Crystals_Pack_02_02_MID']
if obj.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
for other in bpy.context.selected_objects:other.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active=obj
positions=[tuple(v.co) for v in obj.data.vertices]
for f in obj.data.polygons:f.select=f.index==3167
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT',selected_only=True)=={'FINISHED'}
bm=bmesh.from_edit_mesh(obj.data);bm.faces.index_update()
assert [tuple(v.co) for v in bm.verts]==positions
assert (len(bm.verts),len(bm.edges),len(bm.faces))==(3150,6340,3192)
assert {f.index for f in bm.faces if f.select}=={3142,3167}
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR',selected_only=True)=={'FINISHED'}
bm=bmesh.from_edit_mesh(obj.data)
assert (len(bm.verts),len(bm.edges),len(bm.faces))==(3149,6338,3191)
assert inspect_triangle_quality(bm)[1]['uv_triangles']==0
assert all(e.is_manifold for e in bm.edges)
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR',selected_only=True)=={'FINISHED'}
assert len(bmesh.from_edit_mesh(obj.data).faces)==3191
bpy.ops.object.mode_set(mode='OBJECT')
bpy.utils.unregister_class(MESH_OT_polygroups_repair_mesh_folds)
print('CRYSTAL02_FIND_REPAIR_OPERATOR_OK')
