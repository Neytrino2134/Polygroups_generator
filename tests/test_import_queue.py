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
from polygroups_generator.localization import t

context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
assert remesh_backend(context).__name__.endswith("qr_operators")
assert settings.batch_auto_remesh and settings.file_import_auto_remesh
assert settings.batch_clear_material and settings.file_import_clear_material
assert settings.batch_remesh_preset == "HIGH" and settings.file_import_remesh_preset == "HIGH"
assert settings.batch_remesh_method == "QUAD" and settings.file_import_remesh_method == "QUAD"
assert abs(settings.batch_voxel_size - 0.003) < 1e-7
assert abs(settings.file_import_voxel_size - 0.003) < 1e-7
assert settings.batch_auto_smart_uv_project and settings.file_import_auto_smart_uv_project
assert settings.batch_auto_unwrap_method == "SMART"
assert settings.file_import_auto_unwrap_method == "SMART"
assert settings.batch_import_mode == "AUTO"
assert settings.batch_disable_view_assist and settings.file_import_disable_view_assist
assert settings.batch_separate_collections and settings.file_import_separate_collections
assert settings.batch_include_subfolders
assert not settings.batch_auto_save and settings.batch_auto_save_interval == 5
assert settings.batch_stage_2_enabled
assert settings.batch_stage_3_enabled and settings.batch_stage_4_enabled
assert settings.batch_stage_5_enabled
for number in (3, 4):
    for name in ("auto_remesh", "auto_unwrap", "use_materials",
                 "prepare_polygroups", "material_seams"):
        assert getattr(settings, f"batch_stage_{number}_{name}")
settings.batch_stage_3_enabled = False
settings.batch_stage_4_enabled = False
settings.batch_stage_5_enabled = False
assert settings.remesh_auto_unwrap_checker
settings.batch_auto_remesh = True
settings.batch_separate_collections = True
settings.batch_auto_arrange_objects = True
settings.batch_remesh_preset = "LOW"
context.preferences.addons[ROOT.name].preferences.remesh_low_count = 1234
existing = set(bpy.data.objects)
events = []
source_material = bpy.data.materials.new("Imported Textured Material")
source_material.use_nodes = True
source_material.node_tree.nodes.new("ShaderNodeTexImage")
settings.batch_clear_material = True

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
settings.batch_stage = "PAUSED"
settings.batch_is_paused = True
assert modal(modal_operator, context, SimpleNamespace(type="ESC")) == {"RUNNING_MODAL"}
assert not settings.batch_cancel_requested and modal_queue.step.call_count == 2
settings.batch_stage = "IMPORT"
settings.batch_is_paused = False
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
        self.source.data.materials.append(source_material)
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
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / "batch_import_test.blend"))
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
        context.scene.polygroups_seam_finalization_settings.auto_unwrap_after_seam = True
        context.scene.polygroups_seam_finalization_settings.smart_uv_unwrap_auto_pack = True
        context.scene.polygroups_seam_finalization_settings.show_checker_solid_mode = True
        context.scene.polygroups_seam_preparation_settings.show_seams_object_mode = True
        settings.remesh_auto_unwrap_checker = True
        settings.batch_auto_save = True
        settings.batch_auto_save_interval = 2
        save_mock = Mock(return_value={"FINISHED"})
        with patch.object(queue_module, "save_current_blend_file", save_mock):
            queue = queue_module.ImportQueue(context, paths, False, report)
            queue.begin()
            assert not context.scene.polygroups_seam_finalization_settings.auto_unwrap_after_seam
            assert not context.scene.polygroups_seam_finalization_settings.smart_uv_unwrap_auto_pack
            assert not context.scene.polygroups_seam_finalization_settings.show_checker_solid_mode
            assert not context.scene.polygroups_seam_preparation_settings.show_seams_object_mode
            assert not settings.remesh_auto_unwrap_checker
            advance_until(queue, lambda: queue.stage == "WAIT_REMESH")
            assert settings.batch_remesh_progress == 0
            assert queue.cursor.secondary_percent == 0
            assert queue.cursor.status_line == t(context, "import_cursor_processing")
            queue.step(context)
            assert 33 <= settings.batch_remesh_progress <= 34
            assert queue.cursor.secondary_percent == settings.batch_remesh_progress
            settings.batch_is_paused = True
            advance_until(queue, lambda: queue.stage == "NEXT")
            assert settings.batch_remesh_progress == 100
            assert settings.batch_imported_count == 1
            assert save_mock.call_count == 0
            queue.step(context)
            assert settings.batch_stage == "PAUSED"
            assert queue.cursor.status_line == t(context, "import_cursor_paused")
            assert queue.index == 1
            settings.batch_is_paused = False
            first_collection = queue.completed_collection
            assert first_collection is not None
            advance_until(queue, lambda: queue.finished)
            assert save_mock.call_count == 1
        settings.batch_auto_save = False
        assert settings.batch_imported_count == 2 and settings.batch_failed_count == 0
        assert settings.batch_import_progress == 100
        assert events == ["start", "finish", "start", "finish"]
        assert len([c for c in queue.owned_collections if c.name.startswith("Generated.")]) == 2
        collection_layers = {
            layer.collection: layer
            for layer in context.view_layer.layer_collection.children
        }
        assert collection_layers[first_collection].exclude
        assert not collection_layers[queue.collection].exclude
        for anchor, objects in queue.groups:
            assert len(objects) == 2
            result = next(obj for obj in objects if obj != anchor)
            assert result.data.uv_layers.active is not None
            assert any(edge.use_seam for edge in result.data.edges)
            assert list(anchor.data.materials) == [source_material]
            assert len(result.data.materials) == 1
            gray = result.active_material
            assert gray != source_material and gray.name.startswith("Remesh Gray")
            assert tuple(gray.diffuse_color) == (0.5, 0.5, 0.5, 1.0)
            assert len(gray.node_tree.nodes) == 2
            assert tuple(gray.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value) == (0.5, 0.5, 0.5, 1.0)
            assert all(face.material_index == 0 for face in result.data.polygons)
            assert objects[0].users_collection == objects[1].users_collection
            assert objects[0].users_collection[0].name.startswith("Generated.")
            assert (objects[0].matrix_world.translation - objects[1].matrix_world.translation).length < 1e-6
        # Remove this test run only, so subsequent tests start with original objects.
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)
        assert set(bpy.data.objects) == existing

        assert not any(mat.name.startswith("Remesh Gray") for mat in bpy.data.materials)

        # Step mode completes the current file before pausing. Do Next processes
        # exactly one file with settings edited during the pause; Do Next All
        # then releases every remaining file in this run.
        settings.batch_import_mode = "PAUSE_EACH"
        settings.batch_auto_arrange_objects = False
        settings.batch_clear_material = True
        events.clear()
        step_queue = queue_module.ImportQueue(
            context,
            [paths[0], paths[1], paths[0]],
            False,
            report,
        )
        queue_module.ACTIVE_QUEUE = step_queue
        step_queue.begin()
        advance_until(step_queue, lambda: settings.batch_stage == "PAUSED")
        assert settings.batch_imported_count == 1 and step_queue.index == 1
        assert len(step_queue.groups) == 1 and step_queue.job is None

        settings.batch_clear_material = False
        assert bpy.ops.object.polygroups_import_control(action="NEXT_ONE") == {"FINISHED"}
        advance_until(step_queue, lambda: settings.batch_stage == "PAUSED")
        assert settings.batch_imported_count == 2 and step_queue.index == 2
        second_result = step_queue.groups[1][1][-1]
        assert list(second_result.data.materials) == [source_material]

        assert bpy.ops.object.polygroups_import_control(action="NEXT_ALL") == {"FINISHED"}
        advance_until(step_queue, lambda: step_queue.finished)
        assert settings.batch_imported_count == 3 and step_queue.index == 3
        assert len(step_queue.groups) == 3
        queue_module.ACTIVE_QUEUE = None
        step_queue.finished = False
        step_queue.finish(context, "CANCELLED", rollback=True)
        settings.batch_import_mode = "AUTO"
        settings.batch_auto_arrange_objects = True

        settings.batch_clear_material = False
        events.clear()
        queue = queue_module.ImportQueue(context, paths, False, report)
        queue.begin()
        advance_until(queue, lambda: queue.stage == "WAIT_REMESH")
        settings.batch_stop_requested = True
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_imported_count == 1 and queue.index == 1
        assert settings.batch_remaining_count == 1 and settings.batch_stage == "STOPPED"
        assert all(list(obj.data.materials) == [source_material] for obj in queue.groups[0][1])
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
        settings.file_import_clear_material = True
        settings.file_import_auto_remesh = False
        assert not settings.file_import_auto_smart_uv_project
        settings.file_import_separate_collections = True
        queue = queue_module.ImportQueue(context, paths[:1], True, report)
        queue.begin()
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_imported_count == 1
        assert len(queue.groups[0][1]) == 1
        assert queue.groups[0][0].data.uv_layers.active is None
        assert not queue.groups[0][0].data.materials
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)

    # Each enabled pass consumes the preceding pass's mesh. A disabled middle
    # pass is bypassed, so LOW consumes the first pass's result directly.
    chain = []

    class ChainedJob:
        def __init__(self, backend, report):
            pass

        def start(self, context):
            self.source = context.active_object
            chain.append(("start", self.source, context.scene.qremesher.target_count))

        def poll(self):
            return True, 1.0

        def finish(self, context):
            result = self.source.copy()
            result.data = self.source.data.copy()
            result.name = "Retopo_" + self.source.name
            context.scene.collection.objects.link(result)
            self.source.hide_set(True)
            chain.append(("finish", result, None))

        def abort(self):
            pass

    settings.batch_auto_remesh = True
    settings.batch_auto_smart_uv_project = True
    settings.batch_clear_material = False
    settings.batch_auto_arrange_objects = False
    settings.batch_stage_3_enabled = False
    settings.batch_stage_4_enabled = True
    settings.batch_stage_4_auto_unwrap = False
    with patch.object(queue_module, "RemeshJob", ChainedJob):
        queue = queue_module.ImportQueue(context, paths[:1], False, report)
        queue.begin()
        advance_until(queue, lambda: queue.finished)
        assert settings.batch_failed_count == 0
        assert [item[0] for item in chain] == ["start", "finish"] * 2
        assert chain[2][1] == chain[1][1]
        assert chain[2][2] == dict(queue_module.get_remesh_preset_counts(context))["LOW"]
        assert len(queue.groups[0][1]) == 3
        assert queue.cursor is None
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
