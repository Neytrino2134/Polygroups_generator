"""Blender background regression for rebuilding one Generated.N collection."""

import sys
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
settings.batch_import_mode = "AUTO"
settings.batch_auto_arrange_objects = False
settings.batch_auto_save = False
settings.batch_auto_smart_uv_project = False
settings.batch_stage_2_enabled = True
settings.batch_stage_3_enabled = False
settings.batch_stage_4_enabled = False
settings.batch_stage_5_enabled = False
settings.batch_narrow_island_enabled = False
settings.batch_small_islands_enabled = False
settings.batch_second_narrow_island_enabled = False
settings.batch_second_small_islands_enabled = False
settings.batch_autobake_enabled = False


def make_mesh(collection, name):
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def in_collection(obj, collection):
    return obj in set(collection.objects)


first = bpy.data.collections.new("Generated.001")
second = bpy.data.collections.new("Generated.002")
context.scene.collection.children.link(first)
context.scene.collection.children.link(second)
source = make_mesh(first, "Highpoly_Generated.001")
old = make_mesh(first, "Retopo_Highpoly_Generated.001")
other_source = make_mesh(second, "Highpoly_Generated.002")
other_retopo = make_mesh(second, "Retopo_Highpoly_Generated.002")

assert import_queue.redo_collections(context.view_layer) == [first, second]
settings.batch_redo_collection_name = first.name
assert bpy.ops.object.polygroups_batch_redo_select(direction="NEXT") == {"FINISHED"}
assert settings.batch_redo_collection_name == second.name
assert bpy.ops.object.polygroups_batch_redo_select(direction="PREVIOUS") == {"FINISHED"}
assert settings.batch_redo_collection_name == first.name

# Redo launches without reading the original import folder or file list.
launcher = SimpleNamespace(
    use_file_selection=False, redo_collection_name=first.name,
    directory="missing folder", files=[], report=lambda *_: None,
)
launch_context = SimpleNamespace(scene=context.scene, window=context.window,
                                 window_manager=Mock(windows=[]))
with patch.object(import_queue, "ImportQueue") as queue_factory:
    assert batch_import.OBJECT_OT_polygroups_batch_import.execute(
        launcher, launch_context,
    ) == {"RUNNING_MODAL"}
    assert queue_factory.call_args.kwargs["redo_collection"] == first
    assert queue_factory.call_args.args[1] == [first.name]
import_queue.ACTIVE_QUEUE = None
source.hide_viewport = True


class FakeJob:
    def __init__(self, *_args):
        pass

    def start(self, scene_context):
        self.source = scene_context.active_object
        assert self.source == source

    def poll(self):
        return True, 1.0

    def finish(self, scene_context):
        result = self.source.copy()
        result.data = self.source.data.copy()
        result.name = "Retopo_Highpoly_Generated.001"
        scene_context.scene.collection.objects.link(result)

    def abort(self):
        pass


def run_until(queue, predicate):
    for _ in range(50):
        queue.step(context)
        if predicate():
            return
    raise AssertionError((queue.stage, settings.batch_last_error))


with patch.object(import_queue, "RemeshJob", FakeJob), patch.object(
    import_queue, "remesh_backend", lambda *_: object()
):
    queue = import_queue.ImportQueue(context, [first.name], False, print, redo_collection=first)
    queue.begin()
    run_until(queue, lambda: queue.stage == "WAIT_REMESH")
    assert not in_collection(old, first) and old in set(bpy.data.objects)
    assert in_collection(source, first) and in_collection(other_retopo, second)
    settings.batch_cancel_requested = True
    queue.step(context)
    assert queue.finished and settings.batch_stage == "CANCELLED"
    assert source.hide_viewport
    assert in_collection(old, first) and old.name == "Retopo_Highpoly_Generated.001"
    assert in_collection(other_source, second) and in_collection(other_retopo, second)

    queue = import_queue.ImportQueue(context, [first.name], False, print, redo_collection=first)
    queue.begin()
    run_until(queue, lambda: queue.finished)
    results = [obj for obj in first.objects if obj.name.startswith("Retopo_")]
    assert len(results) == 1 and results[0] != old
    assert old not in set(bpy.data.objects)
    assert in_collection(source, first) and in_collection(other_retopo, second)
    assert source.hide_viewport
    assert settings.batch_imported_count == 1 and settings.batch_failed_count == 0
    new_result = results[0]


class FailingJob(FakeJob):
    def poll(self):
        raise RuntimeError("test remesh failure")


with patch.object(import_queue, "RemeshJob", FailingJob), patch.object(
    import_queue, "remesh_backend", lambda *_: object()
):
    queue = import_queue.ImportQueue(context, [first.name], False, print, redo_collection=first)
    queue.begin()
    run_until(queue, lambda: queue.finished)
    assert in_collection(new_result, first) and new_result.name == "Retopo_Highpoly_Generated.001"
    assert settings.batch_failed_count == 1 and settings.batch_imported_count == 0
    assert in_collection(other_retopo, second)

settings.batch_stage_2_enabled = False
queue = import_queue.ImportQueue(context, [first.name], False, print, redo_collection=first)
queue.begin()
run_until(queue, lambda: queue.finished)
assert in_collection(new_result, first)
assert "at least one Remesh pass" in settings.batch_last_error
settings.batch_stage_2_enabled = True

addon_utils.disable(ROOT.name, default_set=True)
addon_utils.disable("quad_remesher", default_set=True)
print("BATCH_REDO_OK")
