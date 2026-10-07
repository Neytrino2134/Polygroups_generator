import sys,json
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add()
mesh=bpy.context.object
mesh.name='SelectedMesh'
bpy.ops.object.empty_add()
empty=bpy.context.object
mesh.select_set(True)
selected=set(bpy.context.selected_objects)
with TemporaryDirectory() as tmp:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(tmp)/'Pack.blend'))
    settings=bpy.context.scene.polygroups_mesh_finalization_settings
    settings.gltf_export_info_format='JSON'
    mesh.location=(2,3,4)
    before=mesh.matrix_world.copy()
    bpy.context.view_layer.update()
    before=mesh.matrix_world.copy()
    assert bpy.ops.object.polygroups_export_selected_gltf()=={'FINISHED'}
    root=Path(tmp)/'!GLTF'
    path=root/'SelectedMesh.gltf'
    data=json.loads(path.read_text())
    assert {node['name'] for node in data['nodes']}=={'SelectedMesh'}
    assert (root/data['buffers'][0]['uri']).is_file()
    info=json.loads((root/'MeshInfo.json').read_text())
    assert info['totals']=={'meshes':1,'vertices':8,'triangles':12}
    assert info['meshes'][0]['file']=='SelectedMesh.gltf'
    assert set(bpy.context.selected_objects)==selected
    assert bpy.context.active_object==empty
    assert mesh.matrix_world==before
    settings.gltf_export_info_format='TXT'
    assert bpy.ops.object.polygroups_export_selected_gltf()=={'FINISHED'}
    assert 'triangles: 12' in (root/'MeshInfo.txt').read_text()
    settings.gltf_export_embedded=True
    material=bpy.data.materials.new('EmbeddedMaterial')
    material.use_nodes=True
    mesh.data.materials.append(material)
    image=bpy.data.images.new('EmbeddedTexture',width=4,height=4)
    node=material.node_tree.nodes.new('ShaderNodeTexImage')
    node.image=image
    shader=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    material.node_tree.links.new(node.outputs['Color'],shader.inputs['Base Color'])
    for item in root.iterdir():
        if item.is_file(): item.unlink()
        elif item.is_dir() and not any(item.iterdir()): item.rmdir()
    assert bpy.ops.object.polygroups_export_selected_gltf()=={'FINISHED'}
    data=json.loads(path.read_text())
    assert all(buffer['uri'].startswith('data:') for buffer in data['buffers'])
    assert data['images'] and all(image['uri'].startswith('data:') for image in data['images'])
    assert not list(root.glob('*.bin')) and not (root/'Textures').exists()
print('SELECTED_GLTF_EXPORT_TEST_PASSED')
