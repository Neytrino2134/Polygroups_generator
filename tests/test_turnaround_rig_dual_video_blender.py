"""Blender background integration: rig hierarchy, selected marks, two real videos."""
import sys
from pathlib import Path
import tempfile
import bpy
import addon_utils
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import turnaround_animation as ta
from polygroups_generator.operators.render_queue import _freestyle_edge_attribute
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
bpy.ops.object.armature_add()
rig = bpy.context.object
rig.location = (2, 0, 0)
bpy.ops.object.empty_add(); intermediate = bpy.context.object; intermediate.parent = rig
meshes = []
for x in (-1, 1):
    bpy.ops.mesh.primitive_cube_add(size=.6, location=(x, 0, 0))
    obj = bpy.context.object; obj.parent = intermediate
    obj.modifiers.new('Rig', 'ARMATURE').object = rig
    meshes.append(obj)
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes: obj.select_set(True)
assert bpy.ops.object.polygroups_mark_freestyle_edges() == {'FINISHED'}
assert all(all(e.value for e in _freestyle_edge_attribute(obj.data).data) for obj in meshes)
bpy.context.view_layer.objects.active = rig
assert bpy.ops.object.polygroups_prepare_turnaround_animation() == {'FINISHED'}
s = bpy.context.scene.polygroups_render_settings
collection = bpy.data.collections[s.animation_collection_name]
clone = bpy.data.objects[s.animation_object_name]
children = [o for o in collection.objects if o.type == 'MESH']
assert len(children) == 2
assert all(o.parent.parent == clone for o in children)
assert all(o.modifiers['Rig'].object == clone for o in children)
assert all(o.parent == intermediate for o in meshes)
bpy.ops.object.camera_add(location=(4,-6,3))
camera = bpy.context.object
from mathutils import Vector
camera.rotation_euler = (Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler()
bpy.context.scene.camera = camera
bpy.ops.object.light_add(type='AREA', location=(1,-3,4)); bpy.context.object.data.energy=500
s.animation_frame_count=2; s.animation_fps=24
s.resolution_x=s.resolution_y=64; s.resolution_scale=100
s.render_engine='CYCLES';s.max_samples=1
s.animation_media_type='VIDEO'; s.animation_container='MPEG4'
s.freestyle_edges=True;s.freestyle_as_render_pass=True;s.animation_freestyle_dual_video=True
scene=bpy.context.scene
before=(scene.render.use_freestyle, bpy.context.view_layer.freestyle_settings.as_render_pass)
with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_turnaround_') as folder:
 s.output_directory=folder
 class RenderTask:
  report = lambda *args: None
 for name, value in vars(ta.OBJECT_OT_polygroups_render_turnaround_animation).items():
  if callable(value) and name.startswith('_') and not name.startswith('__'):
   setattr(RenderTask, name, value)
 task = RenderTask()
 assert task._begin(bpy.context)
 assert task._next_video_pass()
 assert task._finish() == {'CANCELLED'}
 assert not s.is_running and s.animation_collection_name
 assert before==(scene.render.use_freestyle,bpy.context.view_layer.freestyle_settings.as_render_pass)
 assert s.animation_delete_collection_after_render is True
 s.animation_delete_collection_after_render = False
 collection_name = s.animation_collection_name
 object_name = s.animation_object_name
 assert bpy.ops.object.polygroups_render_turnaround_animation() == {'FINISHED'}
 assert collection_name in bpy.data.collections
 assert s.animation_collection_name == collection_name
 assert s.animation_object_name == object_name
 outputs=list(Path(folder).rglob('*.mp4'))
 assert len(outputs)==2, outputs
 assert all(p.stat().st_size>100 for p in outputs)
 assert any('_Clean' in p.name for p in outputs)
 assert any('_Freestyle' in p.name for p in outputs)
 frames = []
 for path in sorted(outputs):
  image = bpy.data.images.load(str(path), check_existing=False)
  frames.append(tuple(image.pixels[:]))
  bpy.data.images.remove(image)
 assert frames[0] and frames[1], 'Video frames must decode'
 assert frames[0] != frames[1], 'Clean and Freestyle frames must differ'
 s.animation_delete_collection_after_render = True
 assert bpy.ops.object.polygroups_render_turnaround_animation() == {'FINISHED'}
 assert collection_name not in bpy.data.collections
 assert object_name not in bpy.data.objects
 assert not s.animation_collection_name and not s.animation_object_name
 assert not s.is_running
 assert before==(scene.render.use_freestyle,bpy.context.view_layer.freestyle_settings.as_render_pass)
print('TURNAROUND_RIG_DUAL_VIDEO_PASSED')

