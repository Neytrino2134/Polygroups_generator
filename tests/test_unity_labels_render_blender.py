import sys
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import unity_preparation as up, render_selected
s=bpy.context.scene.polygroups_mesh_finalization_settings
assert s.unity_render_image_format=='WEBP'
s.unity_render_image_format='PNG'
s.unity_asset_index='A_09'
assert bpy.ops.object.polygroups_unity_index_step(delta=1)=={'FINISHED'}
assert s.unity_asset_index=='A_10'
assert bpy.ops.object.polygroups_unity_index_step(delta=-1)=={'FINISHED'}
assert s.unity_asset_index=='A_09'
s.unity_asset_index='01'
s.unity_asset_name='TestUnity'
s.unity_copy_textures=False
s.unity_generate_text_labels=True
bpy.ops.mesh.primitive_cube_add()
source=bpy.context.object
assert bpy.ops.object.polygroups_prepare_unity(lod='LOD0')=={'FINISHED'}
assert source.name=='TestUnity_00_01'
labels=[o for o in bpy.data.objects if o.get(up.UNITY_LABEL)]
assert len(labels)==1 and 'LOD 0' in labels[0].data.body and '12 tris' in labels[0].data.body
bpy.ops.object.camera_add()
bpy.context.scene.camera=bpy.context.object
bpy.ops.object.select_all(action='DESELECT')
source.select_set(True)
bpy.context.view_layer.objects.active=source
rs=bpy.context.scene.polygroups_render_settings
before=(rs.resolution_x,rs.resolution_y,rs.freestyle_edges,rs.freestyle_as_render_pass)
checked=[]
def fake(self,context):
    assert set(context.selected_objects)=={source,labels[0]}
    assert rs.resolution_x==4096 and rs.resolution_y==4096
    assert rs.freestyle_edges and not rs.freestyle_as_render_pass
    assert Path(self.output_path).parent.name=='Render Unity Assets'
    assert Path(self.output_path).name=='TestUnity_00_01_All.png'
    checked.append(True)
    return {'FINISHED'}
assert not s.unity_render_mesh_info
with patch.object(render_selected.OBJECT_OT_render_selected_auto,'execute',fake), patch.object(up,'_write_export_mesh_info') as writer:
    assert bpy.ops.object.polygroups_render_unity_assets()=={'FINISHED'}
    writer.assert_not_called()
assert checked
assert before==(rs.resolution_x,rs.resolution_y,rs.freestyle_edges,rs.freestyle_as_render_pass)
assert bpy.context.active_object==source
s.unity_render_separate=True
s.unity_render_mesh_info=True
source.scale=(3, .5, 1)
lod=source.copy()
lod.data=source.data.copy()
lod.name=source.name+'.LOD1'
bpy.context.scene.collection.objects.link(lod)
lod.scale=(.5, .5, 3)
lod.location.x += 5
paths=[]
resolutions=[]
camera_frames=[]
camera=bpy.context.scene.camera
original_camera=(camera.matrix_world.copy(),camera.data.ortho_scale,camera.data.lens)
from polygroups_generator.operators import render_queue
# Simulate an older file: existing root with lost pointer and an unparented, locked light.
from mathutils import Vector
light_collection=bpy.data.collections.new('Light_Test')
bpy.context.scene.collection.children.link(light_collection)
light_root=bpy.data.objects.new('Light Position',None)
light_collection.objects.link(light_root)
light_data=bpy.data.lights.new('Test Key','AREA')
light=bpy.data.objects.new('Test Key',light_data)
light_collection.objects.link(light)
light.location=(1,-2,3)
bpy.context.view_layer.update()
light_initial=light.matrix_world.copy()
light_collection.hide_select=True
light.hide_select=True
rs.studio_light_position=None
light_frames=[]

def fake_separate(context,settings,job):
    assert light.parent == light_root
    assert not light.hide_select and not light_collection.hide_select
    light_frames.append(light.matrix_world.copy())
    assert light.matrix_world.translation.x > light_initial.translation.x - 1e-5
    paths.append(Path(job['output_path']).name)
    resolutions.append((context.scene.render.resolution_x,context.scene.render.resolution_y))
    camera_frames.append((camera.matrix_world.copy(),camera.data.ortho_scale,camera.data.lens))
    assert resolutions[-1]==(rs.resolution_x,rs.resolution_y)
    assert max(resolutions[-1])==2048
with TemporaryDirectory() as output:
    with patch.object(render_queue,'_current_state_render_path',return_value=str(Path(output)/'Render.png')), patch.object(
            render_queue,'_render_current_job',fake_separate), patch.object(
            render_selected,'fit_render_aspect',wraps=render_selected.fit_render_aspect) as aspect:
        assert bpy.ops.object.polygroups_render_unity_assets()=={'FINISHED'}
        assert aspect.call_count==1
    info=json.loads((Path(output)/'Render Unity Assets'/'MeshInfo.json').read_text(encoding='utf-8'))
    assert set(info)=={'meshes','totals'}
    assert info['totals']=={'meshes':2,'vertices':16,'triangles':24}
    assert info['meshes']==[
        {'lod':'LOD0','name':source.name,'file':source.name+'.LOD0.png','vertices':8,'triangles':12},
        {'lod':'LOD1','name':lod.name,'file':lod.name+'.png','vertices':8,'triangles':12},
    ]
assert len(light_frames)==2
assert abs((light_frames[1].translation.x-light_frames[0].translation.x) -
           (camera_frames[1][0].translation.x-camera_frames[0][0].translation.x))<1e-5
assert max(abs(light.matrix_world[i][j]-light_initial[i][j]) for i in range(4) for j in range(4))<1e-5
assert rs.studio_light_position==light_root
assert len(resolutions)==2 and resolutions[0]==resolutions[1]
assert abs(camera_frames[1][0].translation.x-camera_frames[0][0].translation.x-5)<.01
assert abs(camera_frames[1][0].translation.y-camera_frames[0][0].translation.y)<1e-5
assert abs(camera_frames[1][0].translation.z-camera_frames[0][0].translation.z)<1e-5
assert camera_frames[0][0].to_quaternion().rotation_difference(camera_frames[1][0].to_quaternion()).angle<1e-5
assert camera_frames[0][1:]==camera_frames[1][1:]
assert (camera.matrix_world,camera.data.ortho_scale,camera.data.lens)==original_camera
assert resolutions[0][0]!=resolutions[0][1]
assert paths==['TestUnity_00_01.LOD0.png','TestUnity_00_01.LOD1.png']
assert source.name=='TestUnity_00_01'
assert before==(rs.resolution_x,rs.resolution_y,rs.freestyle_edges,rs.freestyle_as_render_pass)
s.unity_render_image_format='WEBP'
paths.clear()
with TemporaryDirectory() as output:
    with patch.object(render_queue,'_current_state_render_path',return_value=str(Path(output)/'Render.png')), patch.object(
            render_queue,'_render_current_job',fake_separate):
        assert bpy.ops.object.polygroups_render_unity_assets()=={'FINISHED'}
    info=json.loads((Path(output)/'Render Unity Assets'/'MeshInfo.json').read_text(encoding='utf-8'))
    assert all(entry['file'].endswith('.webp') for entry in info['meshes'])
assert paths==['TestUnity_00_01.LOD0.webp','TestUnity_00_01.LOD1.webp']
assert rs.image_format=='PNG'
print('UNITY_LABELS_RENDER_TEST_PASSED')
