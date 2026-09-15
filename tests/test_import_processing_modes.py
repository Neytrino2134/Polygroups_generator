"""Blender background regression for Simple and Automatic selected-file imports."""

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

from polygroups_generator.operators import batch_import, import_queue


context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
assert not settings.file_import_automatic_processing
settings.batch_import_format = "OBJ"
settings.batch_import_mode = "AUTO"
settings.batch_auto_arrange_objects = False
settings.batch_auto_save = False
settings.batch_auto_smart_uv_project = True
settings.batch_stage_2_enabled = True
settings.batch_stage_3_enabled = False
settings.batch_stage_4_enabled = False
settings.batch_stage_5_enabled = False
settings.batch_narrow_island_enabled = False
settings.batch_small_islands_enabled = True
settings.batch_second_narrow_island_enabled = False
settings.batch_second_small_islands_enabled = False
settings.batch_autobake_enabled = False

simple = import_queue.ImportQueue(context, ["mesh.obj"], True, print)
simple.configure_passes(context)
assert simple.prefix == "file_import" and not simple.batch_stages
assert simple.passes[0][0] == 1
assert simple.first_cleanup_stage() == "PASS_SETUP"

settings.file_import_automatic_processing = True
automatic = import_queue.ImportQueue(
    context, ["mesh.obj"], True, print, automatic_processing=True,
)
automatic.configure_passes(context)
assert automatic.prefix == "batch" and automatic.batch_stages
assert automatic.passes[0][0] == 2
assert automatic.first_cleanup_stage() == "SMALL_ISLANDS"


class FakeJob:
    def __init__(self, *_args):
        pass

    def start(self, scene_context):
        self.source = scene_context.active_object

    def poll(self):
        return True, 1.0

    def finish(self, scene_context):
        result = self.source.copy()
        result.data = self.source.data.copy()
        result.name = "Retopo_" + self.source.name
        scene_context.scene.collection.objects.link(result)

    def abort(self):
        pass


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "mesh.obj"
    path.write_text("o Test\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")

    simple_stages = []
    settings.file_import_automatic_processing = False
    with patch.object(import_queue, "RemeshJob", FakeJob), patch.object(
        import_queue, "remesh_backend", lambda *_: object(),
    ), patch.object(
        import_queue,
        "remove_small_loose_parts",
        lambda *_args, **_kwargs: simple_stages.append("loose") or {"part_count": 0},
    ), patch.object(
        import_queue,
        "smart_uv_unwrap_all",
        lambda *_args, **_kwargs: simple_stages.append("unwrap") or (True, False),
    ):
        simple_queue = import_queue.ImportQueue(context, [str(path)], True, print)
        simple_queue.begin()
        for _ in range(50):
            simple_queue.step(context)
            if simple_queue.finished:
                break
        else:
            raise AssertionError((simple_queue.stage, settings.batch_last_error))
        assert simple_stages == ["loose", "unwrap"]
        simple_queue.finished = False
        simple_queue.finish(context, "CANCELLED", rollback=True)

    settings.file_import_automatic_processing = True
    launcher = SimpleNamespace(
        use_file_selection=True, redo_collection_name="", directory=directory,
        files=[SimpleNamespace(name=path.name)], report=lambda *_: None,
    )
    launch_context = SimpleNamespace(scene=context.scene, window=context.window,
                                     window_manager=Mock(windows=[]))
    with patch.object(import_queue, "ImportQueue") as queue_factory:
        assert batch_import.OBJECT_OT_polygroups_batch_import.execute(
            launcher, launch_context,
        ) == {"RUNNING_MODAL"}
        assert queue_factory.call_args.args[1] == [str(path)]
        assert queue_factory.call_args.kwargs["automatic_processing"] is True
    import_queue.ACTIVE_QUEUE = None

    stages = []
    with patch.object(import_queue, "RemeshJob", FakeJob), patch.object(
        import_queue, "remesh_backend", lambda *_: object(),
    ), patch.object(import_queue.ImportQueue, "merge_small_islands",
                    lambda self, _context, _obj, **_kwargs: stages.append("small")), patch.object(
        import_queue,
        "remove_small_loose_parts",
        lambda *_args, **_kwargs: stages.append("loose") or {"part_count": 0},
    ), patch.object(
        import_queue,
        "smart_uv_unwrap_all",
        lambda *_args, **_kwargs: stages.append("unwrap") or (True, False),
    ):
        queue = import_queue.ImportQueue(
            context, [str(path)], True, print, automatic_processing=True,
        )
        queue.begin()
        for _ in range(50):
            queue.step(context)
            if queue.finished:
                break
        else:
            raise AssertionError((queue.stage, settings.batch_last_error))
        assert settings.batch_imported_count == 1 and settings.batch_failed_count == 0
        assert stages == ["loose", "unwrap", "small"]
        assert queue.groups[0][0].name.startswith("Highpoly_Generated.")
        assert any(obj.name.startswith("Retopo_") for obj in queue.groups[0][1])
        queue.finished = False
        queue.finish(context, "CANCELLED", rollback=True)

addon_utils.disable(ROOT.name, default_set=True)
addon_utils.disable("quad_remesher", default_set=True)
print("IMPORT_PROCESSING_MODES_OK")
