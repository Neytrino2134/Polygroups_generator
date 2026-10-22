"""Open actual Generated.N copies and verify idle state plus live-queue restoration."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators import import_queue as iq


def state_groups(scene):
    return (
        (scene.polygroups_model_preparation_settings, tuple(iq._BATCH_IMPORT_IDLE_STATE)),
        (scene.polygroups_baking_settings, ('bake_task_is_running', 'bake_task_stage',
                                         'bake_task_progress', 'bake_task_message')),
        (scene.polygroups_remesh_status, ('is_running', 'cancel_requested',
                                        'stage', 'progress', 'message')),
    )


def snapshot():
    return {(scene.name, index, name): (getattr(group, name), group.is_property_set(name))
            for scene in bpy.data.scenes
            for index, (group, names) in enumerate(state_groups(scene)) for name in names}


with TemporaryDirectory() as directory:
    source = Path(directory) / 'Batch.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(source))
    extra = bpy.data.scenes.new('Other Scene')
    col = bpy.data.collections.new('Generated.001')
    bpy.context.scene.collection.children.link(col)
    mesh = bpy.data.meshes.new('Saved result')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new('Retopo_Saved result', mesh)
    col.objects.link(obj)
    for scene in bpy.data.scenes:
        for group, names in state_groups(scene):
            for name in names:
                current = getattr(group, name)
                value = (True if isinstance(current, bool) else
                         'IMPORT_BUSY' if isinstance(current, str) else
                         3 if isinstance(current, int) else .5)
                setattr(group, name, value)
        scene.polygroups_model_preparation_settings.batch_save_generated_separately = True
        scene.polygroups_model_preparation_settings.batch_import_directory = directory
    # Preserve an unset property too; rollback must not create stored defaults.
    extra.polygroups_model_preparation_settings.property_unset('batch_eta_seconds')
    before = snapshot()
    output = Path(directory) / 'Batch_Generated_001.blend'
    iq.write_collection_blend(str(output), col)
    assert output.is_file() and bpy.data.filepath == str(source)
    assert snapshot() == before, 'Live queue state changed after successful save'

    def failed_save(**kwargs):
        for scene in bpy.data.scenes:
            assert not scene.polygroups_model_preparation_settings.batch_is_running
            assert scene.polygroups_model_preparation_settings.batch_stage == ''
        raise RuntimeError('Injected copy write failure')

    failed_bpy = SimpleNamespace(data=bpy.data, context=bpy.context,
        ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=failed_save)))
    with patch.object(sys.modules[iq.write_collection_blend.__module__], 'bpy', failed_bpy):
        try:
            iq.write_collection_blend(str(Path(directory) / 'Failed.blend'), col)
        except RuntimeError as error:
            assert 'Injected copy write failure' in str(error)
        else:
            raise AssertionError('Expected save failure')
    assert snapshot() == before, 'Live queue state changed after failed save'
    assert bpy.data.filepath == str(source)

    assert bpy.ops.wm.open_mainfile(filepath=str(output)) == {'FINISHED'}
    assert bpy.data.objects.get('Retopo_Saved result')
    for scene in bpy.data.scenes:
        settings = scene.polygroups_model_preparation_settings
        assert not settings.batch_is_running and not settings.batch_is_paused
        assert not settings.batch_stop_requested and not settings.batch_cancel_requested
        assert settings.batch_stage == '' and settings.batch_current_file == ''
        assert settings.batch_last_error == '' and settings.batch_remaining_count == 0
        assert settings.batch_total_count == settings.batch_imported_count == 0
        assert settings.batch_imported_object_count == settings.batch_failed_count == 0
        assert settings.batch_import_progress == settings.batch_current_progress == 0
        assert settings.batch_remesh_progress == settings.batch_baking_progress == 0
        assert settings.batch_elapsed_seconds == settings.batch_current_seconds == 0
        assert settings.batch_average_seconds == 0 and settings.batch_eta_seconds == -1
        assert settings.batch_save_generated_separately
        assert settings.batch_import_directory == directory
        bake = scene.polygroups_baking_settings
        assert not bake.bake_task_is_running and bake.bake_task_stage == ''
        assert bake.bake_task_progress == 0 and bake.bake_task_message == ''
        remesh = scene.polygroups_remesh_status
        assert not remesh.is_running and not remesh.cancel_requested
        assert remesh.stage == '' and remesh.progress == 0 and remesh.message == ''
print('BATCH_SEPARATE_IDLE_STATE_TESTS_PASSED')
