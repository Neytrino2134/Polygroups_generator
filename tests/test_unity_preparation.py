"""Run with Blender --background --factory-startup --python-exit-code 1 --python."""
import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy

ARP_CALLS = []


class TEST_OT_arp_export(bpy.types.Operator):
    bl_idname = "arp.arp_export_fbx_panel"
    bl_label = "Test ARP Export"
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        selected = tuple(context.selected_objects)
        assert len(selected) == 2
        assert {obj.type for obj in selected} == {'MESH', 'ARMATURE'}
        assert context.active_object.type == 'ARMATURE'
        Path(self.filepath).parent.mkdir(parents=True, exist_ok=True)
        Path(self.filepath).write_bytes(b'TEST ARP FBX')
        ARP_CALLS.append((self.filepath, tuple(obj.name for obj in selected)))
        return {'FINISHED'}


bpy.utils.register_class(TEST_OT_arp_export)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
context = bpy.context
settings = context.scene.polygroups_mesh_finalization_settings
obj = context.active_object
material = bpy.data.materials.new("SharedSource")
material.use_nodes = True
obj.data.materials.clear()
obj.data.materials.append(material)
other = obj.copy()
other.data = obj.data
context.collection.objects.link(other)
other.select_set(False)
image = bpy.data.images.new("Albedo", 4, 4)
node = material.node_tree.nodes.new("ShaderNodeTexImage")
node.image = image
material.node_tree.links.new(node.outputs['Color'], material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
with tempfile.TemporaryDirectory(prefix="unity_export_test_") as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / "test.blend"))
    settings.unity_asset_name = "Konduktor"
    settings.unity_export_directory = str(Path(directory) / "Unity")
    assert bpy.ops.object.polygroups_prepare_unity(lod="LOD1") == {'FINISHED'}
    assert obj.name == 'Konduktor_01.LOD1'
    assert obj.active_material.name == 'Konduktor_01'
    assert other.data != obj.data and other.active_material == material
    assert image.name == 'Albedo'
    texture = Path(directory) / 'Textures' / ('Konduktor_01.png')
    assert texture.is_file(), texture
    assert settings.unity_asset_index == '02'
    assert bpy.ops.object.polygroups_export_unity() == {'FINISHED'}
    folder = Path(settings.unity_export_directory) / 'Konduktor_01'
    assert (folder / (obj.name + '.fbx')).stat().st_size > 0
    assert (folder / ('Konduktor_01.png')).is_file()
    from polygroups_generator.operators.unity_preparation import texture_nodes
    assert Path(next(texture_nodes(obj.active_material.node_tree)).image.filepath_raw) == texture
    assert context.active_object == obj and obj.select_get()
    # Import the produced FBX to check its material name and relative texture reference.
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.import_scene.fbx(filepath=str(folder / (obj.name + '.fbx')))
    imported = context.selected_objects[0]
    assert imported.active_material.name.startswith('Konduktor_01')
    imported_images = [node.image for node in texture_nodes(imported.active_material.node_tree)]
    assert imported_images and all(Path(bpy.path.abspath(img.filepath)).is_file() for img in imported_images)
    bpy.ops.object.select_all(action='DESELECT')
    batch = []
    for count in range(1, 7):
        mesh = bpy.data.meshes.new(f'TestMesh{count}')
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)] * count)
        item = bpy.data.objects.new(f'Test{count}', mesh)
        context.collection.objects.link(item)
        item.data.materials.append(material)
        item.select_set(True)
        batch.append(item)
    context.view_layer.objects.active = batch[0]
    settings.unity_asset_name = 'Batch'
    assert bpy.ops.object.polygroups_prepare_unity(auto_lods=True) == {'FINISHED'}
    assert settings.unity_asset_index == '03'
    for lod, item in enumerate(reversed(batch)):
        assert item.name == ('Batch_02' if lod == 0 else f'Batch_02.LOD{lod}')
        assert len(item.users_collection) == 1
        assert item.users_collection[0].name == f'Batch_02_LOD{lod}_Collection'
        assert item.active_material == batch[-1].active_material
    assert batch[0].active_material.name == 'Batch_02'
    assert (Path(directory) / 'Textures' / 'Batch_02.png').is_file()
    # Repeating preparation reuses the common material and preserves exact names.
    settings.unity_asset_index = '02'
    assert bpy.ops.object.polygroups_prepare_unity(auto_lods=True) == {'FINISHED'}
    assert batch[-1].name == 'Batch_02'
    assert batch[-1].active_material.name == 'Batch_02'
    settings.unity_export_overwrite = False
    armature_data = bpy.data.armatures.new('RigData')
    rig = bpy.data.objects.new('Rig', armature_data)
    context.collection.objects.link(rig)
    rig.select_set(True)
    settings.unity_use_auto_rig_pro = True
    assert bpy.ops.object.polygroups_export_unity() == {'FINISHED'}
    batch_folder = Path(settings.unity_export_directory) / 'Batch_02'
    assert sorted(path.name for path in batch_folder.glob('*.fbx')) == [
        'Batch_02.LOD1.fbx', 'Batch_02.LOD2.fbx',
        'Batch_02.LOD3.fbx', 'Batch_02.LOD4.fbx', 'Batch_02.LOD5.fbx',
        'Batch_02.fbx',
    ]
    assert sorted(path.name for path in batch_folder.glob('*.png')) == ['Batch_02.png']
    assert len(ARP_CALLS) == 1
    assert Path(ARP_CALLS[0][0]).name == 'Batch_02.fbx'
    assert set(ARP_CALLS[0][1]) == {'Batch_02', 'Rig'}
    print('UNITY PREPARATION AND FBX EXPORT PASSED')
