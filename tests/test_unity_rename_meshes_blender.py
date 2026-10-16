import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.unity_preparation import ensure_unity_label
with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'Test.blend'))
    settings = bpy.context.scene.polygroups_mesh_finalization_settings
    settings.unity_asset_name = 'Tree'
    settings.unity_asset_index = '02'
    material = bpy.data.materials.new('Tree_01')
    material.use_nodes = True
    node = material.node_tree.nodes.new('ShaderNodeTexImage')
    image = bpy.data.images.new('Tree_01.001', 2, 2)
    node.image = image
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    material.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    conflict = bpy.data.images.new('Tree_00_02', 2, 2)
    meshes = []
    for index in (0, 2, 5):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        obj.name = 'Tree_01' if index == 0 else f'Tree_01.LOD{index}'
        obj.data.materials.append(material)
        ensure_unity_label(bpy.context, obj, index)
        meshes.append(obj)
    counts = [len(obj.data.polygons) for obj in meshes]
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    assert bpy.ops.object.polygroups_rename_unity_meshes() == {'FINISHED'}
    assert [obj.name for obj in meshes] == ['Tree_00_02', 'Tree_00_02.LOD2', 'Tree_00_02.LOD5']
    assert counts == [len(obj.data.polygons) for obj in meshes]
    assert all(list(obj.data.materials) == [material] for obj in meshes)
    assert image.name == 'Tree_00_02' and conflict.name == 'Tree_00_02__Duplicate'
    assert Path(image.filepath).is_file()
    assert Path(image.filepath).parent.name == 'Tree_00_02'
    assert 'Tree_00_02 | LOD 2' in meshes[1].children[0].data.body
    assert bpy.ops.object.polygroups_rename_unity_meshes() == {'FINISHED'}
    assert image.name == 'Tree_00_02'
    assert not any(Path(directory).rglob('*.001.png'))
    names = [obj.name for obj in meshes]
    image.name = 'WrongTexture.001'
    assert bpy.ops.object.polygroups_fix_unity_textures() == {'FINISHED'}
    assert image.name == 'Tree_00_02'
    assert Path(image.filepath).is_file()
    assert [obj.name for obj in meshes] == names
    assert bpy.ops.object.polygroups_fix_unity_textures() == {'FINISHED'}
    assert image.name == 'Tree_00_02'

print('UNITY_RENAME_MESHES_PASSED')
