"""Blender background regression for Batch Import's Auto Bake handoff."""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators import import_queue, safety_checks


context = bpy.context
collection = bpy.data.collections.new("Generated.001")
context.scene.collection.children.link(collection)


def mesh_object(name):
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


highpoly = mesh_object("Highpoly_Generated.001")
lowpoly = mesh_object("Retopo_03_Highpoly_Generated.001")
lowpoly.data.uv_layers.new(name="UVMap")
temporary_directory = tempfile.TemporaryDirectory()
bpy.ops.wm.save_as_mainfile(filepath=str(Path(temporary_directory.name) / "batch_autobake.blend"))
settings = context.scene.polygroups_model_preparation_settings
bake = context.scene.polygroups_baking_settings
bake.use_auto_cage = True
bake.auto_save_textures_after_bake = False
bake.use_selected_to_active = False

queue = import_queue.ImportQueue(context, [], False, lambda *_args: None)
queue.file_objects = [highpoly, lowpoly]
calls = []
real_bpy = safety_checks.bpy
safety_checks.bpy = SimpleNamespace(
    app=real_bpy.app,
    ops=SimpleNamespace(object=SimpleNamespace(
        polygroups_bake_task=lambda *args, **kwargs: calls.append((args, kwargs)) or {"RUNNING_MODAL"},
    )),
)
try:
    settings.batch_autobake_cage_mode = "SMART"
    queue.start_auto_bake(context, lowpoly)
    assert len(calls) == 1 and calls[0][1] == {"prepare_materials": True}
    assert context.active_object == lowpoly
    assert highpoly.select_get() and lowpoly.select_get()
    assert bake.autogenerate_smart_cage and not bake.use_auto_cage
    assert bake.auto_save_textures_after_bake and bake.use_selected_to_active
    generated_cage = mesh_object("Retopo_03_Highpoly_Generated_Cage.001")
    generated_cage["polygroups_smart_cage"] = True
    generated_cage["smart_cage_target_object"] = lowpoly
    unrelated = mesh_object("Unrelated During Bake")
    queue.collect_bake_created()
    assert generated_cage in queue.owned_objects
    assert generated_cage in queue.file_objects
    assert unrelated not in queue.owned_objects
    assert unrelated not in queue.file_objects
    queue.restore_bake_settings()
    assert bake.use_auto_cage and not bake.autogenerate_smart_cage
    assert not bake.auto_save_textures_after_bake and not bake.use_selected_to_active

    settings.batch_autobake_cage_mode = "AUTO"
    queue.start_auto_bake(context, lowpoly)
    assert len(calls) == 2
    assert bake.use_auto_cage and not bake.autogenerate_smart_cage
    queue.collect_bake_created()
    queue.restore_bake_settings()

    # Regression: Blender 5.2 crashed when separate saving used a temporary
    # Scene through libraries.write after the bake handoff.
    working_path = bpy.data.filepath
    separate_path = Path(temporary_directory.name) / "batch_autobake_Generated_001.blend"
    import_queue.write_collection_blend(str(separate_path), collection)
    assert separate_path.is_file()
    assert bpy.data.filepath == working_path
finally:
    safety_checks.bpy = real_bpy

temporary_directory.cleanup()
for obj in (generated_cage, unrelated, lowpoly, highpoly):
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)
bpy.data.collections.remove(collection)
addon_utils.disable(ROOT.name, default_set=True)
print("BATCH_AUTOBAKE_OK")
