"""Exact evaluated geometry fits tighter than rotated bounding-box corners."""
import sys, math
from pathlib import Path
import bpy, addon_utils
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.auto_render import silhouette_points
from polygroups_generator.operators.render_selected import fit_camera, selected_bounds
ctx=bpy.context;scene=ctx.scene
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
objects=[]
for x,angle in ((0,-30),(-2,150),(2,60)):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,location=(x,0,0))
 obj=ctx.object;obj.scale=(1,.5,.4);obj.rotation_euler.z=math.radians(angle)
 modifier=obj.modifiers.new('Evaluated subdivision','SUBSURF');modifier.levels=1;modifier.render_levels=1
 objects.append(obj)
bpy.ops.object.camera_add();camera=ctx.object;camera.data.lens=85;scene.camera=camera
scene.render.resolution_x=2048;scene.render.resolution_y=1152;scene.render.resolution_percentage=100
ctx.view_layer.update()
points=silhouette_points(ctx,objects)
assert len(points)>sum(len(obj.data.vertices) for obj in objects)
originals=[obj.matrix_world.copy() for obj in objects]
def margins():
 projected=[world_to_camera_view(scene,camera,p) for p in points]
 assert all(.0749<=p.x<=.9251 and .0749<=p.y<=.9251 for p in projected)
 return min(p.x for p in projected),1-max(p.x for p in projected)
box,center,size=selected_bounds(ctx,objects)
fit_camera(ctx,camera,box,center,size)
old=margins()
minimum=Vector(tuple(min(p[i] for p in points) for i in range(3)))
maximum=Vector(tuple(max(p[i] for p in points) for i in range(3)))
fit_camera(ctx,camera,points,(minimum+maximum)*.5,maximum-minimum,margin=.075)
new=margins()
assert all(.05<=value<=.10 for value in new),(old,new)
assert sum(new)<sum(old)-.02,(old,new)
assert [obj.matrix_world for obj in objects]==originals
assert camera.data.clip_end/camera.data.clip_start<10000
for height in (.5, 1.25):
 camera.location = (.2, -3.5, height)
 ctx.view_layer.update()
 fit_camera(ctx,camera,points,(minimum+maximum)*.5,maximum-minimum,margin=.075,only_y=True)
 assert abs(camera.matrix_world.translation.x-.2)<1e-6
 assert abs(camera.matrix_world.translation.z-height)<1e-6
 margins()
print('SILHOUETTE_CAMERA_MARGINS_PASSED',old,new)
