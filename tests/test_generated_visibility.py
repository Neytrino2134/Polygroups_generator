"""Run using Blender --background --factory-startup --python-exit-code 1 --python."""

import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.generated_visibility import generated_paths

context = bpy.context
scene = context.scene
layer = context.view_layer
objects = {}
for number in (1, 2, 10):
    collection = bpy.data.collections.new(f"Generated.{number:03d}")
    scene.collection.children.link(collection)
    for prefix in ("Highpoly_", "Retopo_"):
        mesh = bpy.data.meshes.new("TestMesh")
        obj = bpy.data.objects.new(f"{prefix}Test.{number:03d}", mesh)
        collection.objects.link(obj)
        objects[number, prefix] = obj
other_layer = scene.view_layers.new("Unaffected")
layer.update()
paths = generated_paths(layer)
unrelated = layer.layer_collection.children["Collection"]
unrelated.exclude = True

for prefix in ("Highpoly_", "Retopo_"):
    assert bpy.ops.object.polygroups_object_visibility(prefix=prefix, hidden=True) == {"FINISHED"}
    for (number, obj_prefix), obj in objects.items():
        assert obj.hide_get(view_layer=layer) == (obj_prefix == prefix)
        assert not obj.hide_viewport and not obj.hide_render
        assert not obj.hide_get(view_layer=other_layer)
    bpy.ops.object.polygroups_object_visibility(prefix=prefix, hidden=False)

selected = objects[2, "Retopo_"]
selected.select_set(True)
layer.objects.active = selected
assert bpy.ops.object.polygroups_generated_collection(action="ISOLATE") == {"FINISHED"}
assert [path[-1].exclude for path in paths] == [True, False, True]
assert unrelated.exclude
assert not any(path[-1].exclude for path in generated_paths(other_layer))

assert bpy.ops.object.polygroups_generated_collection(action="NEXT") == {"FINISHED"}
assert [path[-1].exclude for path in paths] == [True, True, False]
assert context.active_object == objects[10, "Retopo_"]
assert bpy.ops.object.polygroups_generated_collection(action="NEXT") == {"CANCELLED"}
assert [path[-1].exclude for path in paths] == [True, True, False]
assert bpy.ops.object.polygroups_generated_collection(action="PREVIOUS") == {"FINISHED"}
assert context.active_object == objects[2, "Retopo_"]
assert unrelated.exclude

# Empty collection navigation falls back to the active layer collection.
empty = bpy.data.collections.new("Generated.003")
scene.collection.children.link(empty)
layer.update()
assert bpy.ops.object.polygroups_generated_collection(action="NEXT") == {"FINISHED"}
assert context.active_object is None
assert layer.active_layer_collection.collection == empty
assert bpy.ops.object.polygroups_generated_collection(action="NEXT") == {"FINISHED"}
assert context.active_object == objects[10, "Retopo_"]

# Nested numbered collection: isolation must keep its parent enabled.
parent = bpy.data.collections.new("Generated.020")
child = bpy.data.collections.new("Generated.021")
scene.collection.children.link(parent)
parent.children.link(child)
mesh = bpy.data.meshes.new("NestedMesh")
obj = bpy.data.objects.new("Retopo_Nested", mesh)
child.objects.link(obj)
layer.update()
obj.select_set(True)
layer.objects.active = obj
layer.active_layer_collection = layer.layer_collection.children[parent.name]
assert bpy.ops.object.polygroups_generated_collection(action="ISOLATE") == {"FINISHED"}
enabled = [path[-1].name for path in generated_paths(layer) if not path[-1].exclude]
assert enabled == ["Generated.020", "Generated.021"], enabled

addon_utils.disable(ROOT.name, default_set=True)
print("GENERATED_VISIBILITY_TESTS_PASSED")
