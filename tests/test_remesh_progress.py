"""Integration test: Blender --background --factory-startup --python-exit-code 1 --python.

Requires the installed and activated Quad Remesher engine. Uses disposable spheres.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable("quad_remesher", default_set=True)
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.remesh_progress import RemeshSession
from polygroups_generator.core.remesh_job import next_retopo_name

context = bpy.context
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
source = context.active_object
source.name = "Highpoly_Generated.001"
collection = bpy.data.collections.new("Generated.001")
context.scene.collection.children.link(collection)
collection.objects.link(source)
for old in list(source.users_collection):
    if old != collection:
        old.objects.unlink(source)
context.scene.qremesher.target_count = 100


def run_remesh(obj, expected, expected_source_name=None):
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    previous_name = obj.name
    session = RemeshSession(context, lambda kind, message: print(kind, message))
    assert session.status.stage == "STARTING" and session.status.progress == 0
    states = {session.status.stage}
    previous_progress = 0
    limit = time.monotonic() + 50
    try:
        while not session.done and time.monotonic() < limit:
            session.step(context)
            states.add(session.status.stage)
            assert session.status.progress >= previous_progress
            previous_progress = session.status.progress
            time.sleep(0.05)
        assert session.done and session.status.stage == "DONE", session.status.message
        assert states == {"STARTING", "RUNNING", "FINISHING", "DONE"}, states
        result = context.active_object
        assert result.name == expected, result.name
        assert obj.name == (expected_source_name or previous_name)
        assert tuple(result.users_collection) == (collection,)
        assert session.status.progress == 100
        assert session.status.polygon_count == len(result.data.polygons) > 0
        assert session.status.elapsed_seconds > 0
        assert session.status.result_name == result.name
        return result
    finally:
        if not session.done:
            session.finish(context, "CANCELLED")


first = run_remesh(source, "Retopo_Highpoly_Generated.001")
second = run_remesh(first, "Retopo_02_Highpoly_Generated.001", "Retopo_01_Highpoly_Generated.001")
third = run_remesh(second, "Retopo_03_Highpoly_Generated.001")
assert next_retopo_name(source.name) == "Retopo_04_Highpoly_Generated.001"
assert first.name == "Retopo_01_Highpoly_Generated.001"

before = set(bpy.data.objects)
session = RemeshSession(context, lambda *_: None)
session.status.cancel_requested = True
session.step(context)
assert session.status.stage == "CANCELLED" and not session.status.is_running
assert set(bpy.data.objects) == before

session = RemeshSession(context, lambda *_: None)
with patch.object(session.job, "start", side_effect=RuntimeError("Test engine failure")):
    session.step(context)
assert session.status.stage == "FAILED" and session.status.message == "Test engine failure"
assert not session.status.is_running and session.done
assert not third.hide_get()

addon_utils.disable(ROOT.name, default_set=True)
addon_utils.disable("quad_remesher", default_set=True)
print("REMESH_PROGRESS_TESTS_PASSED")
