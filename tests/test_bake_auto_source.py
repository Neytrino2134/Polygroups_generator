"""Blender smoke test for automatic highpoly lookup from a single lowpoly."""

from pathlib import Path
import sys
from types import SimpleNamespace

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators import safety_checks
from polygroups_generator.operators import baking


def mesh_object(name, collection):
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


context = bpy.context
collection = bpy.data.collections.new("Generated.001")
context.scene.collection.children.link(collection)
highpoly = mesh_object("Highpoly_Generated.001", collection)
lowpoly = mesh_object("Retopo_02_Highpoly_Generated.001", collection)

assert safety_checks.expected_highpoly_name(lowpoly.name) == highpoly.name
found, expected, owner = safety_checks.find_matching_highpoly(lowpoly)
assert found == highpoly and expected == highpoly.name and owner == collection

bpy.ops.object.select_all(action="DESELECT")
lowpoly.select_set(True)
context.view_layer.objects.active = lowpoly
highpoly.hide_viewport = True
highpoly.hide_render = True
source, _expected, _owner = safety_checks.auto_select_matching_highpoly(context, lowpoly)
assert source == highpoly
assert highpoly.select_get() and lowpoly.select_get()
assert context.active_object == lowpoly
assert not highpoly.hide_viewport and not highpoly.hide_render

# The public bake gate must select the pair before dispatching the bake task.
bpy.ops.object.select_all(action="DESELECT")
lowpoly.select_set(True)
context.view_layer.objects.active = lowpoly
bake_calls = []
real_bpy = safety_checks.bpy
safety_checks.bpy = SimpleNamespace(
    app=real_bpy.app,
    ops=SimpleNamespace(
        object=SimpleNamespace(
            polygroups_bake_task=lambda *args, **kwargs: bake_calls.append((args, kwargs)) or {"RUNNING_MODAL"},
        ),
    ),
)
try:
    operator = SimpleNamespace(report=lambda *_args: None)
    assert safety_checks.run_bake_action(
        operator, context, "PREPARE_AND_BAKE", check_uv=False,
    ) == {"RUNNING_MODAL"}
finally:
    safety_checks.bpy = real_bpy
assert bake_calls and highpoly.select_get() and lowpoly.select_get()
assert context.active_object == lowpoly

bake_settings = context.scene.polygroups_baking_settings
assert bake_settings.hide_highpoly_after_bake
baking._hide_highpoly_sources(context, [highpoly], bake_settings)
assert highpoly.hide_get(view_layer=context.view_layer)
assert not highpoly.hide_viewport

missing = mesh_object("Retopo_03_Highpoly_Generated.002", collection)
bpy.ops.object.select_all(action="DESELECT")
missing.select_set(True)
context.view_layer.objects.active = missing
reports = []
operator = SimpleNamespace(report=lambda level, message: reports.append((level, message)))
assert safety_checks.run_bake_action(
    operator, context, "PREPARE_AND_BAKE", check_uv=False,
) == {"CANCELLED"}
assert reports and "Highpoly_Generated.002" in reports[-1][1]
assert list(context.selected_objects) == [missing]

addon_utils.disable(ROOT.name, default_set=True)
print("BAKE_AUTO_SOURCE_OK", flush=True)
