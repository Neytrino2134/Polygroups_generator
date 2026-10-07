import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy
import addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import render_queue as rq
from polygroups_generator.operators.render_textures import texture_planes, PLANE_TAG, TEMP_TAG
scene=bpy.context.scene
s=scene.polygroups_render_settings
s.render_low=True
s.render_mid=False
s.render_engine='EEVEE'
s.resolution_x=s.resolution_y=32
s.resolution_scale=100
s.multiview_render=True
s.freestyle_edges=True
s.transparent_background=True
coll=bpy.data.collections.new('Test_Collection')
scene.collection.children.link(coll)
bpy.ops.mesh.primitive_cube_add()
source=bpy.context.object
source.name='SM_Test_LOW'
for old in list(source.users_collection): old.objects.unlink(source)
coll.objects.link(source)
mat=bpy.data.materials.new('M_Test')
mat.use_nodes=True
source.data.materials.append(mat)
tree=mat.node_tree
shader=next(n for n in tree.nodes if n.type=='BSDF_PRINCIPLED')
base=tree.nodes.new('ShaderNodeTexImage')
base.image=bpy.data.images.new('Base',width=4,height=4)
base.image.generated_color=(.2,.4,.7,1)
normal=tree.nodes.new('ShaderNodeTexImage')
normal.image=bpy.data.images.new('Normal',width=4,height=4)
normal.image.colorspace_settings.name='Non-Color'
normal.image.generated_color=(.5,.5,1,1)
nmap=tree.nodes.new('ShaderNodeNormalMap')
tree.links.new(base.outputs['Color'],shader.inputs['Base Color'])
tree.links.new(normal.outputs['Color'],nmap.inputs['Color'])
tree.links.new(nmap.outputs['Normal'],shader.inputs['Normal'])
original=(len(tree.nodes),len(tree.links),normal.image.colorspace_settings.name)
assert bpy.ops.object.polygroups_prepare_render_textures()=={'FINISHED'}
planes=texture_planes(coll)
assert len(planes)==2
assert sorted(round(p.location.x,1) for p in planes)==[-.7,.7]
assert all(abs(p.location.z-.5)<1e-6 for p in planes)
assert all(abs(p.dimensions.x-1)<1e-6 for p in planes)
assert bpy.ops.object.polygroups_prepare_render_textures()=={'FINISHED'}
assert len(texture_planes(coll))==2
assert (len(tree.nodes),len(tree.links),normal.image.colorspace_settings.name)==original
assert not mat.get(TEMP_TAG)
assert bpy.ops.object.polygroups_texture_plane_visibility(kind='Normal',show=False)=={'FINISHED'}
assert all(p.hide_render for p in texture_planes(coll) if p[PLANE_TAG]=='Normal')
with TemporaryDirectory() as tmp:
    s.output_directory=tmp
    queue,count=rq._scan_render_queue(s)
    assert count==1 and len(queue)==4
    tex=[j for j in queue if j.get('texture_kind')]
    assert {Path(j['output_path']).name for j in tex}=={'Image_Texture_01_BaseColor.png','Image_Texture_01_Normal.png'}
    assert all(not p.get(PLANE_TAG) for p in rq._queue_objects(queue))
    assert rq._prepare_scene_for_job(queue[0])
    assert all(p.hide_render for p in texture_planes())
    bpy.ops.object.camera_add(location=(0,-4,.5))
    camera=bpy.context.object
    from mathutils import Vector
    camera.rotation_euler=(Vector((0,0,.5))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera=camera
    for job in tex:
        assert rq._prepare_scene_for_job(job)
        view_before=(scene.view_settings.view_transform,scene.view_settings.look)
        rq._render_current_job(bpy.context,s,job)
        assert Path(job['output_path']).is_file()
        assert (scene.view_settings.view_transform,scene.view_settings.look)==view_before
    assert not any('freestyle' in p.name for p in Path(tmp).iterdir())
    s.texture_render_mode='COMBINED'
    combined=rq._scan_render_queue(s)[0]
    jobs=[j for j in combined if j.get('texture_kind')]
    assert len(jobs)==1 and jobs[0]['texture_kind']=='Combined'
    assert Path(jobs[0]['output_path']).name=='Image_Texture_01_BaseColor_Normal.png'
    assert rq._prepare_scene_for_job(jobs[0])
    assert all(not p.hide_render for p in texture_planes(coll))
    images_before=len(bpy.data.images)
    completed=[]
    def on_render_complete(*args):
        completed.append(True)
    bpy.app.handlers.render_complete.append(on_render_complete)
    try:
        rq._render_current_job(bpy.context,s,jobs[0])
        assert len(completed)==1
    finally:
        bpy.app.handlers.render_complete.remove(on_render_complete)
    assert Path(jobs[0]['output_path']).is_file()
    assert len(bpy.data.images)==images_before
    assert normal.image.colorspace_settings.name=='Non-Color'
    s.texture_render_mode='BOTH'
    assert len([j for j in rq._scan_render_queue(s)[0] if j.get('texture_kind')])==3
assert bpy.ops.object.polygroups_clear_render_textures()=={'FINISHED'}
assert not texture_planes()
assert not any(m.get(TEMP_TAG) for m in bpy.data.materials)
assert not any(m.get(TEMP_TAG) for m in bpy.data.meshes)
assert (len(tree.nodes),len(tree.links),normal.image.colorspace_settings.name)==original
print('RENDER_TEXTURES_TEST_PASSED')
