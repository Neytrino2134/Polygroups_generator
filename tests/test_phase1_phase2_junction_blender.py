"""Phase 1 + 2 junction: Generated.N already saved to files are removed so Phase 2 starts at .001 again."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import skip_marks  # noqa: E402
from polygroups_generator.operators import import_queue, phase2_processing as phase  # noqa: E402

scene = bpy.context.scene


def generated(number):
    """A Generated.N collection holding one Highpoly_Generated.N mesh."""
    digits = f'{number:03d}'
    collection = bpy.data.collections.new(f'Generated.{digits}')
    scene.collection.children.link(collection)
    mesh = bpy.data.meshes.new(f'Highpoly_Generated.{digits}')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(mesh.name, mesh)
    collection.objects.link(obj)
    return collection, obj


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    blend = root / 'scene.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    # Phase 1 leaves an empty placeholder for every file it saved.
    for number in (1, 2):
        collection, obj = generated(number)
        bpy.data.libraries.write(str(root / f'scene_Generated_{number:03d}.blend'), {collection}, fake_user=True)
        bpy.data.objects.remove(obj, do_unlink=True)
    unsaved, unsaved_obj = generated(3)      # no file: exists only in this scene
    marked, marked_obj = generated(4)
    bpy.data.libraries.write(str(root / 'scene_Generated_004.blend'), {marked}, fake_user=True)
    skip_marks.mark(marked, 'kept for manual work')

    settings = scene.polygroups_model_preparation_settings
    settings.phase2_clear_generated = False   # the junction does not depend on this option
    phase.clear_saved_generated_collections(scene, bpy.data.filepath)
    assert 'Generated.001' not in bpy.data.collections and 'Generated.002' not in bpy.data.collections
    assert unsaved.name in bpy.data.collections and unsaved_obj.name in bpy.data.objects
    assert marked.name in bpy.data.collections and marked_obj.name in bpy.data.objects
    restored = phase.restore_collection(str(root / 'scene_Generated_001.blend'), 'Generated.001', scene)
    assert restored.name == 'Generated.001', restored.name
    print('JUNCTION_CLEAR_OK')

    # Without saved files nothing is removed: the results live only in this scene.
    empty = root / 'other'
    empty.mkdir()
    phase.clear_saved_generated_collections(scene, str(empty / 'scene.blend'))
    assert restored.name in bpy.data.collections and unsaved.name in bpy.data.collections

    # schedule_phase2 clears right before it starts Phase 2, and only once Phase 2 can start.
    calls, timers = [], []
    fake = MagicMock()
    fake.context.window_manager.windows = [object()]
    fake.data.filepath = 'working.blend'
    fake.app.timers.register = lambda function, first_interval=0: timers.append(function)
    fake.ops.object.polygroups_start_phase2 = lambda *_: calls.append('start')
    states = [False, True]
    with patch.object(import_queue, 'bpy', fake), patch.object(import_queue, 't', lambda *_: ''), \
            patch.object(phase, 'available', lambda _context: states.pop(0)), \
            patch.object(phase, 'clear_saved_generated_collections',
                         lambda *args: calls.append(('clear', args))):
        import_queue.schedule_phase2(scene, bpy.context.view_layer, lambda *_: None)
        assert timers[0]() == 0.5 and calls == []       # still busy: nothing is deleted yet
        assert timers[0]() is None
    assert calls == [('clear', (scene, 'working.blend')), 'start'], calls
    print('JUNCTION_ORDER_OK')
