import sys
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import turnaround_animation as ta
bpy.ops.mesh.primitive_cube_add()
source=bpy.context.object
source.scale=(3, 0.5, 1)
source['unity_prepared']=True
bpy.ops.object.camera_add()
scene=bpy.context.scene
scene.camera=bpy.context.object
bpy.ops.object.select_all(action='DESELECT')
source.select_set(True)
bpy.context.view_layer.objects.active=source
rs=scene.polygroups_render_settings
rs.animation_frame_count=8
rs.freestyle_edges=True
scene.render.use_freestyle=True
original=(rs.resolution_x,rs.resolution_y,rs.output_directory,scene.camera.matrix_world.copy())
calls=[]
original_resolution=(scene.render.resolution_x,scene.render.resolution_y)
def check_square(size):
    assert (rs.resolution_x,rs.resolution_y,rs.resolution_scale)==(size,size,100)
    assert (scene.render.resolution_x,scene.render.resolution_y)==(size,size)
    assert not rs.freestyle_edges and not scene.render.use_freestyle
def views(self,context):
    check_square(2048)
    assert bpy.data.objects.get(rs.animation_object_name)
    calls.append('PNG')
    return {'FINISHED'}
def video(self,context):
    check_square(1024)
    assert rs.animation_media_type=='VIDEO' and rs.animation_container=='MPEG4'
    calls.append('MP4')
    return {'FINISHED'}
with patch.object(ta.OBJECT_OT_polygroups_render_turnaround_views,'execute',views), patch.object(ta.OBJECT_OT_polygroups_render_turnaround_animation,'execute',video):
    assert bpy.ops.object.polygroups_render_unity_turnaround()=={'FINISHED'}
assert calls==['PNG','MP4']
assert rs.freestyle_edges and scene.render.use_freestyle
assert (scene.render.resolution_x,scene.render.resolution_y)==original_resolution
assert (rs.resolution_x,rs.resolution_y,rs.output_directory,scene.camera.matrix_world)==original
assert bpy.context.active_object==source
assert not rs.animation_collection_name
assert not any(c.get(ta.TURNAROUND_COLLECTION_PROP) for c in bpy.data.collections)
print('UNITY_TURNAROUND_TEST_PASSED')
