"""Blender background regression for persistent Multi View previews."""

import math
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)

from polygroups_generator.operators import render_queue

scene = bpy.context.scene
settings = scene.polygroups_render_settings
settings.multiview_offset = 2.0
settings.multiview_angle = "30"

collection = bpy.data.collections.new("Preview_01_Collection")
scene.collection.children.link(collection)
mesh = bpy.data.meshes.new("Preview")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
source = bpy.data.objects.new("SM_Preview_01_LOW", mesh)
collection.objects.link(source)
bpy.ops.object.select_all(action="DESELECT")
source.select_set(True)
bpy.context.view_layer.objects.active = source

assert bpy.ops.object.polygroups_prepare_selected_multiview() == {"FINISHED"}
views = render_queue._prepared_multiview_views(source)
assert len(views) == 3
assert sorted(round(math.degrees(obj.rotation_euler.z) % 360) for obj in views) == [30, 120, 210]
assert sorted(round(obj.location.x, 3) for obj in views) == [-2.0, 0.0, 2.0]
assert source.hide_render and source.hide_viewport

job = {"collection": collection.name, "object": source.name, "asset_name": "Preview_01"}
assert render_queue._prepare_scene_for_job(job)
assert render_queue._create_multiview_setup(job) == []
assert all(not obj.hide_render for obj in views)
render_queue._finish_render_job(job)
assert len(render_queue._prepared_multiview_views(source)) == 3

assert bpy.ops.object.polygroups_clear_multiview_render() == {"FINISHED"}
assert not render_queue._prepared_multiview_views(source)
assert not source.hide_render and not source.hide_viewport

settings.multiview_angle = "-30"
assert render_queue._prepare_scene_for_job(job)
temporary = render_queue._create_multiview_setup(job)
assert len(temporary) == 3
assert sorted(round(math.degrees(obj.rotation_euler.z) % 360) for obj in temporary) == [60, 150, 330]
temporary_names = [obj.name for obj in temporary]
render_queue._finish_render_job(job, temporary)
assert all(name not in bpy.data.objects for name in temporary_names)

print("MULTIVIEW PREVIEW TEST PASSED")
