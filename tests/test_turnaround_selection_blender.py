"""Run in Blender background: selected meshes share one turnaround root."""
import sys
from pathlib import Path
import bpy
import addon_utils
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.turnaround_animation import remove_turnaround_collection
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
meshes=[]
for location in ((3,2,1), (6,4,2), (-2,0,3)):
 bpy.ops.mesh.primitive_cube_add(location=location)
 meshes.append(bpy.context.object)
meshes[1].parent=meshes[0]
bpy.context.view_layer.update()
originals={obj:obj.matrix_world.copy() for obj in meshes}
bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active=meshes[0]
assert bpy.ops.object.polygroups_prepare_turnaround_animation()=={'FINISHED'}
s=bpy.context.scene.polygroups_render_settings
collection=bpy.data.collections[s.animation_collection_name]
clones=[obj for obj in collection.objects if obj.type=='MESH']
assert len(clones)==3
root=bpy.data.objects[s.animation_object_name].parent
assert all(obj.parent==root for obj in clones)
for source in meshes:
 clone=next(obj for obj in clones if obj.name==source.name+'_Turnaround')
 expected=originals[source].translation-originals[meshes[0]].translation
 assert (clone.matrix_world.translation-expected).length<1e-5
 assert clone.data!=source.data
 assert (source.matrix_world.translation-originals[source].translation).length<1e-5
remove_turnaround_collection(bpy.context,collection.name)
assert all(obj.name in bpy.data.objects for obj in meshes)
print('MULTI_SELECTION_TURNAROUND_OK')
