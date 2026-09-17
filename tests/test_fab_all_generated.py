"""Blender regression: all-generated FAB sets, indexing and shared textures."""
import sys
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.fab_preparation import generated_fab_triplet, FabPrepareQueue
from polygroups_generator.operators import fab_preparation
from polygroups_generator import ui
from polygroups_generator.operators import mesh_export

scene = bpy.context.scene
settings = scene.polygroups_mesh_finalization_settings
settings.fab_asset_name = 'Rock'
settings.fab_asset_index = '07'
settings.fab_auto_increment_index = True
settings.fab_copy_textures = True
settings.fab_collection_color_tag = 'COLOR_04'

with tempfile.TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'Assets.blend'))
    image = bpy.data.images.new('Source BaseColor', width=2, height=2)
    image.filepath_raw = str(Path(directory) / 'original.png')
    image.file_format = 'PNG'
    image.save()
    source_image_name = image.name
    source_path = image.filepath
    material = bpy.data.materials.new('Shared Source')
    material.use_nodes = True
    node = material.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    node.label = 'BaseColor'
    mesh = bpy.data.meshes.new('Shared Geometry')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.materials.append(material)
    unrelated = bpy.data.objects.new('Unrelated Shared Asset', mesh)
    scene.collection.objects.link(unrelated)
    triplets = []
    older = []
    for number in (10, 1, 2):
        collection = bpy.data.collections.new(f'Generated.{number:03d}')
        scene.collection.children.link(collection)
        objects = []
        names = (f'Highpoly_Generated.{number:03d}',
                 f'Retopo_10_Highpoly_Generated.{number:03d}',
                 f'Retopo_10_Highpoly_Generated_SmartDecimated.{number:03d}',
                 f'Retopo_09_Highpoly_Generated.{number:03d}',
                 f'Retopo_09_Highpoly_Generated_SmartDecimated.{number:03d}')
        for name in names:
            if number == 2 and name == names[2]:
                continue
            obj = bpy.data.objects.new(name, mesh)
            collection.objects.link(obj)
            objects.append(obj)
        if number != 2:
            found, missing = generated_fab_triplet(collection)
            assert not missing and tuple(objects[:3]) == found
            triplets.append((number, found))
        else:
            found, missing = generated_fab_triplet(collection)
            assert found is None and 'LOW of latest MID' in missing
        older.extend(obj for obj in objects if '_09_' in obj.name)
        layer = bpy.context.view_layer.layer_collection.children[collection.name]
        layer.exclude = True

    # An existing asset must not be overwritten or produce a Blender .001 suffix.
    existing = bpy.data.collections.new('Rock_07_Collection')
    scene.collection.children.link(existing)
    assert bpy.ops.object.polygroups_auto_prepare_all_generated() == {'FINISHED'}
    assert settings.fab_asset_index == '10'
    assert image.name == source_image_name and image.filepath == source_path
    assert material.name == 'Shared Source'
    assert unrelated.data == mesh and mesh.materials[0] == material
    assert all(obj.active_material == material and obj.name.startswith('Retopo_09_') for obj in older)
    for number, objects in triplets:
        index = '08' if number == 1 else '09'
        destination = bpy.data.collections[f'Rock_{index}_Collection']
        assert destination.color_tag == 'COLOR_04'
        assert set(destination.objects) == set(objects)
        assert mesh_export._collection_asset_name(destination) == f'Rock_{index}'
        for variant, obj in zip(('HIGH', 'MID', 'LOW'), objects):
            assert obj.name == obj.data.name == f'SM_Rock_{index}_{variant}'
            assert tuple(obj.users_collection) == (destination,)
            expected_material = f'M_Rock_{index}' + ('_HIGH' if variant == 'HIGH' else '')
            assert obj.active_material.name == expected_material
            nodes = [node for node in obj.active_material.node_tree.nodes if node.type == 'TEX_IMAGE']
            assert len(nodes) == 1
            prepared_image = nodes[0].image
            expected_image = f'T_Rock_{index}' + ('_HIGH' if variant == 'HIGH' else '') + '_BaseColor'
            assert prepared_image.name == expected_image
            filepath = Path(bpy.path.abspath(prepared_image.filepath))
            assert filepath.is_file()
            assert filepath.parent.name == f'Rock_{index}'
            assert filepath.name == expected_image + '.png'
        assert objects[1].active_material == objects[2].active_material
        assert objects[0].active_material != objects[1].active_material
    # Repeat safely: incomplete / already prepared sets leave assets and index alone.
    before = (set(bpy.data.objects.keys()), set(bpy.data.materials.keys()))
    assert bpy.ops.object.polygroups_auto_prepare_all_generated() == {'CANCELLED'}
    assert settings.fab_asset_index == '10'
    assert before == (set(bpy.data.objects.keys()), set(bpy.data.materials.keys()))
# The button opens the same confirmation workflow as selected-set preparation.
operator_class = fab_preparation.OBJECT_OT_polygroups_auto_prepare_all_generated
dialog = Mock(return_value={'RUNNING_MODAL'})
dialog_context = SimpleNamespace(scene=scene, preferences=bpy.context.preferences,
                                 window_manager=SimpleNamespace(invoke_props_dialog=dialog))
assert operator_class.invoke(SimpleNamespace(), dialog_context, None) == {'RUNNING_MODAL'}
assert dialog.call_count == 1

# Drive actual modal TIMER handling: progress updates per asset, failures continue,
# and stopping preserves completed work and leaves pending triples untouched.
settings.fab_copy_textures = False
for number in (40, 41, 42):
    collection = bpy.data.collections.new(f'Generated.{number:03d}')
    scene.collection.children.link(collection)
    for name in (f'Highpoly_Generated.{number:03d}', f'Retopo_10_Highpoly_Generated.{number:03d}',
                 f'Retopo_10_Highpoly_Generated_SmartDecimated.{number:03d}'):
        obj = bpy.data.objects.new(name, mesh.copy())
        collection.objects.link(obj)
queue = FabPrepareQueue(bpy.context, lambda kind, message: None)
queue.begin()
assert settings.fab_prepare_is_running and settings.fab_prepare_total == 6
assert settings.fab_prepare_progress == 0
assert not operator_class.poll(bpy.context)
runner = SimpleNamespace(_queue=queue, _next_tick=0, _cleanup=Mock(), report=Mock())
real_prepare = fab_preparation.prepare_object_for_fab

def injected_failure(context, obj, variant, options, report=None):
    if queue.records[queue.position]['collection'] == 'Generated.040' and variant == 'MID':
        raise RuntimeError('Injected preparation error')
    return real_prepare(context, obj, variant, options, report)

with patch.object(fab_preparation, 'prepare_object_for_fab', side_effect=injected_failure):
    for _tick in range(30):
        runner._next_tick = 0
        assert operator_class.modal(runner, bpy.context, SimpleNamespace(type='TIMER')) == {'PASS_THROUGH'}
        if settings.fab_prepare_prepared == 1:
            break
assert settings.fab_prepare_failed == 1 and settings.fab_prepare_skipped == 3
assert settings.fab_prepare_done == 5 and 0 < settings.fab_prepare_progress < 1
assert any(record['status'] == 'ERROR' and record['message'] == 'Injected preparation error'
           for record in json.loads(settings.fab_prepare_queue_data))
probe = ui._probe_panel(ui.VIEW3D_PT_polygroups_mesh_finalization, bpy.context, 'Preparation Queue')
assert probe.section_match
assert bpy.ops.object.polygroups_stop_fab_prepare() == {'FINISHED'}
runner._next_tick = 0
assert operator_class.modal(runner, bpy.context, SimpleNamespace(type='TIMER')) == {'FINISHED'}
assert runner._cleanup.call_count == 1
assert settings.fab_prepare_status == 'STOPPED' and not settings.fab_prepare_is_running
assert bpy.data.objects.get('Highpoly_Generated.042') is not None
assert queue.records[-1]['status'] == 'STOPPED'
print('FAB_ALL_GENERATED_OK')
