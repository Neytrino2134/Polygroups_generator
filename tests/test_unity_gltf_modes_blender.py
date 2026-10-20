"""Real exports: one embedded asset versus separate LODs sharing external images."""
import base64
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote
import bpy
import addon_utils

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
settings=bpy.context.scene.polygroups_mesh_finalization_settings
settings.unity_export_autosave=False  # This test validates GLTF, not autosave.
settings.unity_export_all_renders=False  # Rendering has separate dedicated regression tests.
settings.unity_export_fbx=False
settings.unity_export_gltf=True
settings.unity_export_info_format='JSON'
assert settings.unity_gltf_mode=='COMBINED'
source=bpy.context.active_object
source.name='ModeTest'
material=bpy.data.materials.new('SharedMaterial')
material.use_nodes=True
image=bpy.data.images.new('SharedAlbedo',width=4,height=4)
node=material.node_tree.nodes.new('ShaderNodeTexImage')
node.image=image
material.node_tree.links.new(node.outputs['Color'],material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
source.data.materials.clear()
source.data.materials.append(material)
lods=[source]
for index in (1,2):
    obj=source.copy()
    obj.data=source.data.copy()
    obj.name=f'ModeTest.LOD{index}'
    bpy.context.scene.collection.objects.link(obj)
    lods.append(obj)
bpy.ops.object.select_all(action='DESELECT')
for index,obj in enumerate(lods):
    obj['unity_prepared']=True
    obj.location=(index*4+1,2,3)
    obj.select_set(True)
bpy.context.view_layer.objects.active=source
bpy.context.view_layer.update()
matrices=[obj.matrix_world.copy() for obj in lods]
with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'ModeTest.blend'))
    for mode in ('COMBINED','SHARED'):
        settings.unity_gltf_mode=mode
        settings.unity_export_directory=str(Path(directory)/mode)
        assert bpy.ops.object.polygroups_export_unity()=={'FINISHED'}
        folder=Path(settings.unity_export_directory)/'ModeTest'/'GLTF'
        paths=sorted(folder.glob('*.gltf'))
        if mode=='COMBINED':
            assert [p.name for p in paths]==['ModeTest.gltf']
            document=json.loads(paths[0].read_text())
            assert len(document['meshes'])==3
            assert len(document['materials'])==1 and len(document['images'])==1
            assert {node['name'] for node in document['nodes']}=={obj.name for obj in lods}
            assert all(node.get('translation',[0,0,0])==[0,0,0] for node in document['nodes'])
            for category in ('buffers','images'):
                for item in document[category]:
                    assert item['uri'].startswith('data:')
                    assert base64.b64decode(item['uri'].split(',',1)[1])
            assert not list(folder.glob('*.bin')) and not (folder/'Textures').exists()
        else:
            assert len(paths)==3 and len(list(folder.glob('*.bin')))==3
            references=[]
            for path in paths:
                document=json.loads(path.read_text())
                assert len(document['meshes'])==1 and len(document['images'])==1
                for item in document['buffers']+document['images']:
                    assert not item['uri'].startswith('data:')
                    assert (folder/unquote(item['uri'])).is_file()
                references.append(document['images'][0]['uri'])
            assert len(set(references))==1
            assert len(list((folder/'Textures').iterdir()))==1
        info=json.loads((folder/'MeshInfo.json').read_text())
        assert info['Engine'] == 'Unity'
        assert info['totals']['meshes']==3
        assert {entry['lod'] for entry in info['meshes']}=={'LOD0','LOD1','LOD2'}
        assert all((folder/entry['file']).is_file() for entry in info['meshes'])
        assert set(bpy.context.selected_objects)==set(lods) and bpy.context.active_object==source
        assert all(obj.matrix_world==matrix for obj,matrix in zip(lods,matrices))
print('UNITY_GLTF_MODES_TEST_PASSED')
