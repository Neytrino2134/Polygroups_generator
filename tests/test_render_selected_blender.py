import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy,addon_utils
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.render_selected import selected_bounds, fit_camera
bpy.ops.object.select_all(action='DESELECT')
meshes=[]
for i in range(4):
    bpy.ops.mesh.primitive_cube_add(size=1.5,location=(4+i*1.5,0,.75))
    meshes.append(bpy.context.object)
bpy.ops.object.camera_add(location=(0,-8,.5))
cam=bpy.context.object
bpy.context.scene.camera=cam
bpy.ops.object.empty_add(location=(0,0,.5))
aim=bpy.context.object
constraint=cam.constraints.new('TRACK_TO')
constraint.target=aim
constraint.track_axis='TRACK_NEGATIVE_Z'
constraint.up_axis='UP_Y'
settings=bpy.context.scene.polygroups_render_settings
settings.studio_camera=cam
settings.studio_camera_aim=aim
settings.render_engine='EEVEE'
settings.resolution_x=96
settings.resolution_y=64
settings.freestyle_edges=True
settings.freestyle_as_render_pass=False
settings.transparent_background=False
bpy.ops.object.select_all(action='DESELECT')
for mesh in meshes: mesh.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
bpy.context.view_layer.update()
original_cam=cam.matrix_world.copy()
original_aim=aim.matrix_world.copy()
data=cam.data
original_res=(bpy.context.scene.render.resolution_x,bpy.context.scene.render.resolution_y)
original_meshes=[obj.data for obj in meshes]
from polygroups_generator.operators.render_studio import ensure_light_position
root=ensure_light_position(bpy.context)
root_original=root.matrix_world.copy()
checked=[]
def check_frame(*args):
    points,center,size=selected_bounds(bpy.context)
    assert abs(cam.matrix_world.translation.x-center.x)<1e-5
    assert aim.matrix_world.translation==center
    assert abs(root.matrix_world.translation.x-center.x)<1e-5
    for point in points:
        p=world_to_camera_view(bpy.context.scene,cam,point)
        assert .0999<=p.x<=.9001 and .0999<=p.y<=.9001
    assert bpy.context.scene.render.use_freestyle
    assert abs(bpy.context.scene.render.resolution_x/bpy.context.scene.render.resolution_y-4)<.1
    for obj in meshes:
        assert all(item.value for item in obj.data.attributes["freestyle_edge"].data)
    checked.append(True)
bpy.app.handlers.render_pre.append(check_frame)
with TemporaryDirectory() as tmp:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(tmp)/'Pack.blend'))
    assert bpy.ops.object.polygroups_render_selected_auto()=={'FINISHED'}
    assert Path(settings.last_output_path).is_file()
    assert checked
    assert root.matrix_world==root_original
    assert [obj.data for obj in meshes]==original_meshes
    assert (settings.resolution_x,settings.resolution_y)==(96,64)
    assert cam.matrix_world==original_cam and aim.matrix_world==original_aim
    assert cam.data==data and not constraint.mute
    assert (bpy.context.scene.render.resolution_x,bpy.context.scene.render.resolution_y)==original_res
    assert set(bpy.context.selected_objects)==set(meshes)
bpy.app.handlers.render_pre.remove(check_frame)
# Check orthographic fitting independently, including portrait aspect ratio.
cam.constraints.clear()
cam.data.type='ORTHO'
bpy.context.scene.render.resolution_x=64
bpy.context.scene.render.resolution_y=96
points,center,size=selected_bounds(bpy.context)
fit_camera(bpy.context,cam,points,center,size)
for point in points:
    p=world_to_camera_view(bpy.context.scene,cam,point)
    assert .0999<=p.x<=.9001 and .0999<=p.y<=.9001
print('AUTO_SELECTED_RENDER_TEST_PASSED')
