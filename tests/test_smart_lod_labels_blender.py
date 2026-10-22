import sys
from pathlib import Path
import bpy,addon_utils
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import smart_lods, render_selected
bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6)
source=bpy.context.object
source.name='LabelTest'
s=bpy.context.scene.polygroups_mesh_finalization_settings
s.smart_lods_count=2
s.smart_lods_target_1=80
s.smart_lods_target_2=40
s.smart_lods_create_text=True
assert bpy.ops.object.polygroups_generate_smart_lods()=={'FINISHED'}
lods=[bpy.data.objects[f'LabelTest.LOD{i-1}'] for i in (1,2)]
labels=[o for o in bpy.data.objects if o.get(smart_lods.LOD_LABEL)]
assert len(labels)==2
for i,lod in enumerate(lods,1):
    label=next(o for o in labels if o.parent==lod)
    tris=smart_lods._triangle_count(lod,bpy.context.evaluated_depsgraph_get())
    assert label.data.body==f'LabelTest | LOD {i-1}\n{tris:,} tris'
    assert label.matrix_world.translation.z>max((lod.matrix_world@smart_lods.Vector(c)).z for c in lod.bound_box)
bpy.ops.object.camera_add()
bpy.context.scene.camera=bpy.context.object
bpy.ops.object.select_all(action='DESELECT')
source.select_set(True)
bpy.context.view_layer.objects.active=source
rs=bpy.context.scene.polygroups_render_settings
rs.freestyle_edges=False
rs.freestyle_as_render_pass=True
checked=[]
def fake_execute(self,context):
    assert set(context.selected_objects)==set(lods+labels)
    assert rs.freestyle_edges and not rs.freestyle_as_render_pass
    assert rs.resolution_x==4096 and rs.resolution_y==4096 and rs.resolution_scale==100
    assert Path(self.output_path).parent.name=='Render LODS'
    checked.append(True)
    return {'FINISHED'}
with patch.object(render_selected.OBJECT_OT_render_selected_auto,'execute',fake_execute):
    assert bpy.ops.object.polygroups_render_smart_lods()=={'FINISHED'}
assert checked
assert not rs.freestyle_edges and rs.freestyle_as_render_pass
assert bpy.context.active_object==source and bpy.context.selected_objects==[source]
assert len([o for o in bpy.data.objects if o.get(smart_lods.LOD_LABEL)])==2
s.smart_lods_render_mode='INDIVIDUAL'
individual=[]
def fake_individual(self,context):
    selected=context.selected_objects
    assert len(selected)==2
    mesh=next(obj for obj in selected if obj.type=='MESH')
    label=next(obj for obj in selected if obj.type=='FONT')
    assert label.parent==mesh
    individual.append(self.output_path)
    return {'FINISHED'}
with patch.object(render_selected.OBJECT_OT_render_selected_auto,'execute',fake_individual):
    assert bpy.ops.object.polygroups_render_smart_lods()=={'FINISHED'}
assert len(individual)==2 and len(set(individual))==2
assert bpy.context.active_object==source
print('SMART_LOD_LABELS_TEST_PASSED')
