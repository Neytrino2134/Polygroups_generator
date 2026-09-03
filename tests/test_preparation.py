"""Run with Blender --background --factory-startup --python-exit-code 1 --python."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators import safety_checks
from polygroups_generator.operators.rename_objects import rename_and_move_objects

context = bpy.context
scene = context.scene
obj = context.active_object
collection = bpy.data.collections.new("Generated.001")
scene.collection.children.link(collection)
for old in list(obj.users_collection):
    old.objects.unlink(obj)
collection.objects.link(obj)
operator_class = safety_checks.OBJECT_OT_polygroups_checked_generate_polygroups

# Invoke must bypass the dialog AND execute must bypass Rename/Weld for Retopo.
for name in ("Retopo_Highpoly_Generated.001", "Retopo_Custom", "Highpoly_Generated.001"):
    obj.name = name
    runner = SimpleNamespace(run_generate_polygroups=Mock(return_value={"FINISHED"}))
    runner.execute = lambda ctx: operator_class.execute(runner, ctx)
    with patch.object(safety_checks, "rename_and_move_objects", side_effect=AssertionError("Unexpected rename")), \
         patch.object(safety_checks, "apply_weld_to_objects", side_effect=AssertionError("Unexpected Weld")):
        assert operator_class.invoke(runner, context, None) == {"FINISHED"}
    runner.run_generate_polygroups.assert_called_once_with(context)
    assert obj.name == name and tuple(obj.users_collection) == (collection,)
assert not safety_checks.is_polygroups_ready_name("Cube")
assert not safety_checks.is_generated_highpoly_name("Retopo_Custom")

# Unprepared names keep the existing confirmation dialog.
obj.name = "Cube"
dialog = Mock(return_value={"RUNNING_MODAL"})
ctx = SimpleNamespace(active_object=obj, window_manager=SimpleNamespace(invoke_props_dialog=dialog))
assert operator_class.invoke(SimpleNamespace(), ctx, None) == {"RUNNING_MODAL"}
dialog.assert_called_once()

# Preserve numbered collection memberships without creating an empty Generated collection.
rename_and_move_objects(context, [obj])
assert obj.name.startswith("Highpoly_Generated.")
assert tuple(obj.users_collection) == (collection,)
assert bpy.data.collections.get("Generated") is None
second_collection = bpy.data.collections.new("Generated.002")
scene.collection.children.link(second_collection)
second = bpy.data.objects.new("Another", bpy.data.meshes.new("AnotherMesh"))
second_collection.objects.link(second)
plain = bpy.data.objects.new("Plain", bpy.data.meshes.new("PlainMesh"))
scene.collection.objects.link(plain)
rename_and_move_objects(context, [obj, second, plain])
assert tuple(obj.users_collection) == (collection,)
assert tuple(second.users_collection) == (second_collection,)
assert tuple(plain.users_collection) == (bpy.data.collections["Generated"],)
assert len({obj.name, second.name, plain.name}) == 3

addon_utils.disable(ROOT.name, default_set=True)
print("PREPARATION_TESTS_PASSED")
