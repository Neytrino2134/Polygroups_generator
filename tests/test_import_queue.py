"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
addon_utils.enable("quad_remesher", default_set=True)

from polygroups_generator.operators import import_queue as queue_module
from polygroups_generator.operators import batch_import
from polygroups_generator.core.remesh_job import remesh_backend, RemeshJob

context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
assert remesh_backend(context).__name__.endswith("qr_operators")
settings.batch_auto_remesh = True
settings.batch_separate_collections = True
settings.batch_auto_arrange_objects = True
settings.batch_remesh_preset = "LOW"
context.preferences.addons[ROOT.name].preferences.remesh_low_count = 1234
existing = set(bpy.data.objects)
events = []

# Exercise the modal entry point with Blender's Event shape (no timer field).
modal_queue = SimpleNamespace(
    finished=False, scene=context.scene, view_layer=context.view_layer,
    settings=settings, step=Mock(),
)
modal_operator = SimpleNamespace(_queue=modal_queue, _next_tick=0.0)
modal = batch_import.OBJECT_OT_polygroups_batch_import.modal
with patch.object(batch_import.time, "monotonic", side_effect=[1.0, 1.05, 1.25]):
    assert modal(modal_operator, context, SimpleNamespace(type="TIMER")) == {"PASS_THROUGH"}
    assert modal_queue.step.call_count == 1
    modal(modal_operator, context, SimpleNamespace(type="TIMER"))
    assert modal_queue.step.call_count == 1
    modal(modal_operator, context, SimpleNamespace(type="TIMER"))
    assert modal_queue.step.call_count == 2
modal(modal_operator, context, SimpleNamespace(type="MOUSEMOVE"))
assert modal_queue.step.call_count == 2
modal(modal_operator, context, SimpleNamespace(type="ESC"))
assert settings.batch_cancel_requested and modal_queue.step.call_count == 3
settings.batch_cancel_requested = False


class FakeJob:
    def __init__(self, backend, report):
        self.ticks = 0
    def start(self, context):
        self.source = context.active_object
        assert self.source.name.startswith("Highpoly_Generated.")
        assert not self.source.modifiers
        assert context.scene.qremesher.target_count == 1234
        events.append("start")
    def poll(self):
        self.ticks += 1
        return self.ticks == 3, self.ticks / 3
    def finish(self, context):
        result = self.source.copy()
        result.data = self.source.data.copy()
        result.name = "Retopo_" + self.source.name
        context.scene.collection.objects.link(result)
        self.source.hide_set(True)
        events.append("finish")
    def abort(self):
        events.append("abort")


def report(kind, text):
    print(kind, text)


def advance_until(queue, predicate, limit=100):
    for _ in range(limit):
        queue.step(context)
        if predicate():
            return
    raise AssertionError((queue.stage, settings.batch_last_error))


with tempfile.TemporaryDirectory() as directory:
    paths = []
    for index in range(2):
        path = Path(directory) / f"model{index}.obj"
        path.write_text('o Test\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        paths.append(str(path))
    # Starting a folder import must ignore remembered file-browser selections.
    settings.batch_import_directory = directory
    settings.batch_import_format = "OBJ"
    operator = SimpleNamespace(
        use_file_selection=False, directory="invalid remembered directory",
        files=[SimpleNamespace(name="old_selection.obj")], report=report,
    )
    wm = Mock(windows=[])
    start_context = SimpleNamespace(scene=context.scene, window=context.window, window_manager=wm)
    with patch.object(queue_module, "ImportQueue") as queue_factory:
        result = batch_import.OBJECT_OT_polygroups_batch_import.execute(operator, start_context)
        assert result == {"RUNNING_MODAL"}
        assert queue_factory.call_args.args[1] == paths
        assert queue_factory.call_args.args[2] is False
        wm.fileselect_add.assert_not_called()
    queue_module.ACTIVE_QUEUE = None
    with patch.object(queue_module, "RemeshJob", FakeJob):
        queue = queue_module.ImportQueue(context, paths, False, report)
        queue.begin()
        advance_until(queue, lambda: queue.stage == "WAIT_REMESH")
        settings.batch_is_paused = True
        advance_until(queue, lambda: queue.stage == "NEXT")
        assert settings.batch_imported_count == 1
        queue.step(context)
        assert settings.batch_stage == "PAUSED"
        assert queue.index == 1
        settings.batch_is_paused = False
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_imported_count == 2 and settings.batch_failed_count == 0
        assert settings.batch_import_progress == 100
        assert events == ["start", "finish", "start", "finish"]
        assert len([c for c in queue.owned_collections if c.name.startswith("Generated.")]) == 2
        for anchor, objects in queue.groups:
            assert len(objects) == 2
            assert objects[0].users_collection == objects[1].users_collection
            assert objects[0].users_collection[0].name.startswith("Generated.")
            assert (objects[0].matrix_world.translation - objects[1].matrix_world.translation).length < 1e-6
        # Remove this test run only, so subsequent tests start with original objects.
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)
        assert set(bpy.data.objects) == existing

        events.clear()
        queue = queue_module.ImportQueue(context, paths, False, report)
        queue.begin()
        advance_until(queue, lambda: queue.stage == "WAIT_REMESH")
        settings.batch_stop_requested = True
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_imported_count == 1 and queue.index == 1
        assert settings.batch_remaining_count == 1 and settings.batch_stage == "STOPPED"
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)

        # Cancellation while engine is working must leave unrelated objects untouched.
        queue = queue_module.ImportQueue(context, paths, False, report)
        queue.begin()
        advance_until(queue, lambda: queue.stage == "WAIT_REMESH")
        bpy.ops.mesh.primitive_cube_add()
        unrelated = context.active_object
        settings.batch_cancel_requested = True
        queue.step(context)
        assert queue.finished and events[-1] == "abort"
        assert set(bpy.data.objects) == existing | {unrelated}
        bpy.data.objects.remove(unrelated, do_unlink=True)

        # Failure counts as failed, not completed, and the next file can proceed.
        queue = queue_module.ImportQueue(context, [str(Path(directory) / "missing.obj"), paths[1]], False, report)
        queue.begin()
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_failed_count == 1 and settings.batch_imported_count == 1
        assert settings.batch_import_progress == 100 and settings.batch_remaining_count == 0
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)

        # A file with multiple meshes completes every remesh before the next import.
        multi = Path(directory) / "multi.obj"
        multi.write_text('o First\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
                         'o Second\nv 2 0 0\nv 3 0 0\nv 2 1 0\nf 4 5 6\n')
        events.clear()
        queue = queue_module.ImportQueue(context, [str(multi), paths[0]], False, report)
        queue.begin()
        queue_module.ACTIVE_QUEUE = queue
        advance_until(queue, lambda: queue.stage == "WAIT_REMESH")
        bpy.ops.object.polygroups_import_control(action="PAUSE")
        advance_until(queue, lambda: settings.batch_stage == "PAUSED")
        assert queue.index == 1 and len(queue.groups[0][1]) == 4
        assert events == ["start", "finish", "start", "finish"]
        bpy.ops.object.polygroups_import_control(action="PAUSE")
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_imported_count == 2
        assert events == ["start", "finish"] * 3
        queue_module.ACTIVE_QUEUE = None
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)

        # Import-tab settings are independent of Batch Import settings.
        settings.file_import_auto_remesh = False
        settings.file_import_separate_collections = True
        queue = queue_module.ImportQueue(context, paths[:1], True, report)
        queue.begin()
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_imported_count == 1
        assert len(queue.groups[0][1]) == 1
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)

    # Verify actual progress-file protocol and failure handling without launching engine.
    path = Path(directory) / "progress.txt"
    job = RemeshJob(None, report)
    job.state.progressFilename = str(path)
    assert job.poll() == (False, 0)
    path.write_text("0.5\n")
    assert job.poll() == (False, 0.5)
    path.write_text("2\n")
    assert job.poll() == (True, 1)
    path.write_text("-2\nActivation required\n")
    try:
        job.poll()
        raise AssertionError("Expected engine error")
    except RuntimeError as error:
        assert "Activation" in str(error)

addon_utils.disable(ROOT.name, default_set=True)
addon_utils.disable("quad_remesher", default_set=True)
print("IMPORT_QUEUE_TESTS_PASSED")
