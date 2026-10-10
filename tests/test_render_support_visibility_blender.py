"""Render support preflight must leave hidden asset meshes and collections alone."""
from pathlib import Path
import sys

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import render_queue as rq, turnaround_animation as ta

scene = bpy.context.scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)


def collection(name, parent=None):
    result = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(result)
    return result


def object_in(col, name, kind='MESH'):
    data = (bpy.data.cameras.new(name) if kind == 'CAMERA' else
            bpy.data.lights.new(name, 'POINT') if kind == 'LIGHT' else
            bpy.data.meshes.new(name))
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    return obj


def layer_for(col):
    def visit(layer):
        if layer.collection == col:
            return layer
        for child in layer.children:
            found = visit(child)
            if found:
                return found
    return visit(bpy.context.view_layer.layer_collection)


def hidden(col, obj):
    obj.hide_set(True)
    obj.hide_render = obj.hide_viewport = obj.hide_select = True
    col.hide_render = col.hide_viewport = col.hide_select = True
    layer_for(col).exclude = True
    layer_for(col).hide_viewport = True


def flags(col, obj):
    layer = layer_for(col)
    return (col.hide_render, col.hide_viewport, col.hide_select, layer.exclude,
            layer.hide_viewport, obj.hide_render, obj.hide_viewport, obj.hide_select)


assets = collection('Assets')
ancestor_mesh = object_in(assets, 'Hidden ancestor mesh')
ancestor_mesh.hide_set(True)
ancestor_mesh.hide_render = ancestor_mesh.hide_viewport = ancestor_mesh.hide_select = True
support = []
for name, kind in [('Scene_Studio', 'MESH'), ('Camera_Studio', 'CAMERA'), ('Light_Studio', 'LIGHT')]:
    col = collection(name, assets)
    obj = object_in(col, name, kind)
    support.append((col, obj))
renamed = collection('Renamed studio')
renamed['polygroups_studio_role'] = 'scene'
backdrop = object_in(renamed, 'Tagged backdrop')
support.append((renamed, backdrop))
nested = collection('Backdrop details', support[0][0])
nested_obj = object_in(nested, 'Backdrop detail')
hidden(nested, nested_obj)
support.append((nested, nested_obj))
for col, obj in support[:-1]:
    hidden(col, obj)

unrelated = []
for name in ['Hidden Assets', 'SceneAssets', 'CameraModels', 'Lightbulbs']:
    col = collection(name)
    obj = object_in(col, name)
    hidden(col, obj)
    unrelated.append((col, obj, flags(col, obj)))
root_mesh = object_in(scene.collection, 'Hidden root mesh')
root_mesh.hide_set(True)
root_mesh.hide_render = root_mesh.hide_viewport = root_mesh.hide_select = True
mixed = collection('Mixed rig')
mixed_camera = object_in(mixed, 'Legacy camera', 'CAMERA')
mixed_mesh = object_in(mixed, 'Hidden mixed mesh')
mixed_mesh.hide_set(True)
mixed_mesh.hide_render = mixed_mesh.hide_viewport = mixed_mesh.hide_select = True
mixed_camera.hide_render = mixed_camera.hide_viewport = True

assert not rq.is_render_support_collection(scene, scene.collection)
rq.ensure_render_support_visible(bpy.context)
rq.ensure_render_support_visible(bpy.context)  # Repeated LOD positioning/preflight is safe.
for col, obj in support:
    assert not any(flags(col, obj)), (col.name, flags(col, obj))
    assert not obj.hide_get()
for col, obj, original in unrelated:
    assert flags(col, obj) == original, (col.name, original, flags(col, obj))
for obj in [root_mesh, ancestor_mesh, mixed_mesh]:
    assert obj.hide_render and obj.hide_viewport and obj.hide_select and obj.hide_get(), obj.name
assert not mixed_camera.hide_render and not mixed_camera.hide_viewport

turn = collection('Turnaround')
turn_mesh = object_in(turn, 'Render target')
for keep_scene in (False, True):
    snapshot = ta._isolate_turnaround(scene, turn, keep_scene)
    assert not turn_mesh.hide_render
    for col, obj, _ in unrelated:
        assert col.hide_render and obj.hide_render, col.name
    assert root_mesh.hide_render and ancestor_mesh.hide_render and mixed_mesh.hide_render
    assert support[0][1].hide_render == (not keep_scene)
    assert backdrop.hide_render == (not keep_scene)
    ta._restore_visibility(snapshot)
    for col, obj, original in unrelated:
        assert flags(col, obj) == original, col.name
print('RENDER_SUPPORT_VISIBILITY_TESTS_PASSED')
