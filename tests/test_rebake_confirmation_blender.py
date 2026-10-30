"""Confirmation reviews the same dispatch that launches, without starting work."""
import sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy, addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import rebake_final as final, baking, rebake_queue
Operator=final.OBJECT_OT_polygroups_rebake_final_mesh
assert {'title','confirm_text'} <= set(bpy.types.WindowManager.bl_rna.functions['invoke_props_dialog'].parameters.keys())
c=bpy.context;s=c.scene.polygroups_baking_settings;p=c.scene.polygroups_model_preparation_settings
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s.bake_base_color=True;s.bake_normal=False
calls=[];reports=[];labels=[]
class Layout:
    def label(self,**kwargs):labels.append(kwargs['text'])
    def box(self):return self
    def row(self):return self
    def panel(self,idname,default_closed=False):
        # The source list is a collapsible section, closed by default.
        assert default_closed;panels.append(idname);return self,self
panels=[]
def operator():
    return SimpleNamespace(use_queue=True,create_lods=False,export_selected=False,
        repair_mesh=False,delete_current_lods=False,clear_materials=False,layout=Layout(),
        report=lambda level,message:reports.append(message))
def dialog(op,**kwargs):
    calls.append(('dialog',kwargs));return {'RUNNING_MODAL'}
def fake_context():
    return SimpleNamespace(scene=c.scene,active_object=c.active_object,
        selected_objects=list(c.selected_objects),window_manager=SimpleNamespace(invoke_props_dialog=dialog))
def invoke_bake(task,context,event):
    calls.append(('bake',context.active_object.name));return {'FINISHED'}
def invoke_queue(task,context):
    calls.append(('queue',len(p.phase2_rebake_queue)));return {'FINISHED'}

with tempfile.TemporaryDirectory() as directory:
    targets=[];sources=[]
    for index in (1,2):
        bpy.ops.mesh.primitive_plane_add();target=c.object;target.name=f'SM_Review_01_{index:02d}_MID'
        material=bpy.data.materials.new('Final');material.use_nodes=True;target.data.materials.append(material)
        image=bpy.data.images.new(f'T_Review_01_{index:02d}_BaseColor',width=16,height=16)
        image.filepath_raw=str(Path(directory)/(image.name+'.png'));image.file_format='PNG';image.save()
        material.node_tree.nodes.new('ShaderNodeTexImage').image=image
        collection=bpy.data.collections.new(f'Generated.{index:03d}');c.scene.collection.children.link(collection)
        high=bpy.data.objects.new(f'Highpoly_Generated.{index:03d}',target.data.copy());collection.objects.link(high)
        targets.append(target);sources.append(high)
    bpy.ops.object.select_all(action='DESELECT');targets[0].select_set(True);c.view_layer.objects.active=targets[0]
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'invoke',invoke_bake), \
            patch.object(rebake_queue.OBJECT_OT_polygroups_rebake_queue_run,'execute',invoke_queue):
        op=operator();before=set(bpy.data.objects)
        assert Operator.invoke(op,fake_context(),None)=={'RUNNING_MODAL'}
        assert set(bpy.data.objects)==before and [item[0] for item in calls]==['dialog']
        assert calls[-1][1]['confirm_text']=='Запустить'
        Operator.draw(op,c)
        assert panels==['polygroups_rebake_review_sources']
        assert any(targets[0].name in text for text in labels)
        assert any(sources[0].name in text for text in labels)
        assert Operator.execute(op,c)=={'FINISHED'} and calls[-1][0]=='bake'
        # Populated queue shows every entry; confirmation itself never runs it.
        for target in targets:p.phase2_rebake_queue.add().target=target
        op=operator();count=len(calls)
        assert Operator.invoke(op,fake_context(),None)=={'RUNNING_MODAL'}
        assert len(calls)==count+1 and op._rebake_review['queued']
        assert [row['target'] for row in op._rebake_review['rows']]==[t.name for t in targets]
        assert Operator.execute(op,c)=={'FINISHED'} and calls[-1]==('queue',2)
        # Explicit source + active target is reviewed and launched instead of queue.
        sources[0].select_set(True);sources[0].name='Chosen sculpt'
        op=operator();Operator.invoke(op,fake_context(),None)
        assert not op._rebake_review['queued'] and op._rebake_review['rows'][0]['source']=='Chosen sculpt'
        assert Operator.execute(op,c)=={'FINISHED'} and calls[-1][0]=='bake'
        # Selection changes after review cannot launch a different workload.
        sources[0].name='Highpoly_Generated.001'
        sources[0].select_set(False)
        count=len(calls)
        assert Operator.execute(op,c)=={'CANCELLED'} and len(calls)==count
        assert reports and 'changed' in reports[-1]
        # Missing queue targets appear in the review and block launch.
        p.phase2_rebake_queue.add()
        op=operator();Operator.invoke(op,fake_context(),None)
        assert op._rebake_review['rows'][-1]['error']
        count=len(calls)
        assert Operator.execute(op,c)=={'CANCELLED'} and len(calls)==count
print('REBAKE_CONFIRMATION_REVIEW_NO_SIDE_EFFECTS_AND_LAUNCH_OK',flush=True)
