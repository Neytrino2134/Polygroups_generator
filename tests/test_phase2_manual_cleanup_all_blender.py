"""Manual Cleanup: Resculpting prefix and safe Generated.N tree removal."""
import sys
from pathlib import Path
import addon_utils
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
context=bpy.context;p=context.scene.polygroups_model_preparation_settings


def collection(name,parent=None):
    result=bpy.data.collections.new(name)
    (parent or context.scene.collection).children.link(result)
    return result


def mesh(name,owner,data=None):
    if data is None:
        data=bpy.data.meshes.new(name);data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
    obj=bpy.data.objects.new(name,data);owner.objects.link(obj);return obj


outside=collection('Keep asset')
hidden=collection('Hidden resculpt')
first=mesh('Resculpting_01_Highpoly_Generated.701',hidden)
second=mesh('Resculpting_Another',hidden)
shared_data=first.data
retained=mesh('SM_Keep_00_01_MID',outside,shared_data)
backup=mesh('Backup_Resculpting_01',outside)
suffix=mesh('Rock_Resculpting',outside)
empty=bpy.data.objects.new('Resculpting_Empty',None);outside.objects.link(empty)
hidden.hide_viewport=hidden.hide_render=True
names=[first.name,second.name]
assert bpy.ops.object.polygroups_phase2_clear_resculpting()=={'FINISHED'}
assert all(name not in bpy.data.objects for name in names)
assert retained.data==shared_data and shared_data.users==1
assert all(obj.name in bpy.data.objects for obj in (retained,backup,suffix,empty))

root=collection('Generated.701')
nested=collection('Owned nested',root)
double=collection('Generated.702.001')
plain=collection('Generated')
similar=collection('Generated.Other')
shared_child=collection('Shared nested',root);outside.children.link(shared_child)
owned=mesh('Owned Generated mesh',nested)
another=mesh('Owned double suffix',double)
linked=mesh('Keep external object',root);outside.objects.link(linked)
keep_shared=mesh('Shared child object',shared_child)
keep_plain=mesh('Keep unnumbered',plain)
keep_similar=mesh('Keep nonnumeric',similar)
root.hide_viewport=root.hide_render=True
context.view_layer.update()

# Reject a shared collection before touching any of the other Generated trees.
other_scene=bpy.data.scenes.new('Other scene');other_scene.collection.children.link(double)
try:result=bpy.ops.object.polygroups_phase2_clear_generated()
except RuntimeError:result={'CANCELLED'}
assert result=={'CANCELLED'} and owned.name in bpy.data.objects and root.name in bpy.data.collections
other_scene.collection.children.unlink(double);bpy.data.scenes.remove(other_scene)
doomed_objects=[owned.name,another.name];doomed_collections=[root.name,nested.name,double.name]
assert bpy.ops.object.polygroups_phase2_clear_generated()=={'FINISHED'}
assert all(name not in bpy.data.objects for name in doomed_objects)
assert all(name not in bpy.data.collections for name in doomed_collections)
assert linked.name in outside.objects and keep_shared.name in shared_child.objects
assert all(obj.name in bpy.data.objects for obj in (retained,backup,suffix,empty,keep_plain,keep_similar))
assert bpy.ops.object.polygroups_phase2_clear_generated()=={'FINISHED'}

for name in ('phase2_pipeline_running','phase2_rebake_queue_running','phase2_auto_render_running'):
    setattr(p,name,True)
    assert not bpy.ops.object.polygroups_phase2_clear_generated.poll()
    assert not bpy.ops.object.polygroups_phase2_clear_resculpting.poll()
    setattr(p,name,False)
p.phase2_show_manual_cleanup=True
from polygroups_generator.custom_ui.schema import capture
panel=capture(context,1);assert not panel.errors,panel.errors
operators={binding[1] for binding in panel.bindings.values() if binding[0]=='operator'}
assert {'object.polygroups_phase2_clear_generated','object.polygroups_phase2_clear_resculpting'}<=operators
print('PHASE2_MANUAL_RESCULPT_AND_GENERATED_CLEANUP_OK',flush=True)
