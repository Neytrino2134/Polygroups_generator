"""Real GLB scan order and cancellation recovery, including separate output."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators.batch_import import collect_import_files, import_path_sort_key, arrange_objects_zx
from polygroups_generator.operators.import_queue import ImportQueue

settings = bpy.context.scene.polygroups_model_preparation_settings
for name in (
    'batch_auto_arrange_objects', 'batch_apply_weld', 'batch_stage_2_enabled',
    'batch_stage_3_enabled', 'batch_stage_4_enabled', 'batch_stage_5_enabled',
    'batch_narrow_island_enabled', 'batch_small_islands_enabled',
    'batch_second_narrow_island_enabled', 'batch_second_small_islands_enabled',
    'batch_autobake_enabled', 'batch_auto_restore_separate_retopo',
):
    setattr(settings, name, False)
settings.batch_import_mode = 'AUTO'
settings.batch_separate_collections = True
assert sorted(['10/a.glb', '2/z.glb', '1/y.glb'], key=import_path_sort_key) == ['1/y.glb', '2/z.glb', '10/a.glb']


def until(queue, predicate):
    for _ in range(100):
        if predicate():
            return
        queue.step(bpy.context)
    raise AssertionError((queue.stage, queue.index))

with TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'source'
    cube = bpy.data.objects['Cube']
    bpy.ops.object.select_all(action='DESELECT')
    cube.select_set(True)
    for folder, name in [('10 Models', 'A'), ('02 Models', 'Z'), ('01 Models', 'Y')]:
        directory = source / folder
        directory.mkdir(parents=True)
        cube.name = name
        bpy.ops.export_scene.gltf(filepath=str(directory / (name + '.glb')),
                                  export_format='GLB', use_selection=True)
    paths = collect_import_files(str(source), 'GLB', True)
    assert [Path(path).parent.name for path in paths] == ['01 Models', '02 Models', '10 Models']
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    settings.batch_auto_rename_objects = False
    settings.batch_save_generated_separately = False
    queue = ImportQueue(bpy.context, paths, False, lambda *args: None)
    queue.begin()
    until(queue, lambda: queue.index == 1 and queue.stage == 'NEXT')
    first = queue.collection
    assert any(obj.name.startswith('Y') for obj in first.objects)
    until(queue, lambda: queue.index == 1 and queue.stage == 'RENAME')
    second = queue.collection
    assert any(obj.name.startswith('Z') for obj in second.objects)
    settings.batch_cancel_requested = True
    queue.step(bpy.context)
    assert queue.finished and first.all_objects and second.all_objects

    # Layout must also follow the imported groups instead of mesh names.
    anchor_a = next(obj for obj in first.objects if obj.type == 'MESH')
    anchor_b = next(obj for obj in second.objects if obj.type == 'MESH')
    anchor_a.name, anchor_b.name = 'Z_First', 'A_Second'
    arrange_objects_zx([anchor_a, anchor_b], alignment='ORIGIN', preserve_order=True)
    assert anchor_a.matrix_world.translation.x < anchor_b.matrix_world.translation.x

    settings.batch_save_generated_separately = True
    queue = ImportQueue(bpy.context, paths, False, lambda *args: None)
    queue.begin()
    until(queue, lambda: queue.index == 1 and queue.stage == 'NEXT')
    completed_name = queue.collection.name
    assert not queue.collection.all_objects
    until(queue, lambda: queue.index == 1 and queue.stage == 'RENAME')
    partial_name = queue.collection.name
    # Simulate an already completed remesh before a later stage is interrupted.
    source_obj = queue.meshes[0]
    retopo = source_obj.copy()
    retopo.data = source_obj.data.copy()
    retopo.name = 'Retopo_Interrupted'
    queue.collection.objects.link(retopo)
    queue.owned_objects.add(retopo)
    queue.owned_meshes.add(retopo.data)
    settings.batch_cancel_requested = True
    queue.step(bpy.context)
    assert queue.finished
    assert bpy.data.collections[completed_name].all_objects
    assert retopo in set(bpy.data.collections[partial_name].all_objects)
    output = root / ('Working_' + partial_name.replace('.', '_') + '.blend')
    with bpy.data.libraries.load(str(output)) as (data, _):
        assert 'Retopo_Interrupted' in data.objects
    # Reopen the working file to verify cancellation recovery was persisted.
    bpy.ops.wm.open_mainfile(filepath=str(root / 'Working.blend'))
    assert bpy.data.collections[completed_name].all_objects
    assert bpy.data.collections[partial_name].all_objects
    assert bpy.data.objects.get('Retopo_Interrupted')
    assert not bpy.context.scene.polygroups_model_preparation_settings.batch_is_running
print('BATCH_ORDER_RECOVERY_PASSED')
