"""Blender background smoke test for render queue output folders and image."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)

from polygroups_generator.operators import render_queue

scene = bpy.context.scene
settings = scene.polygroups_render_settings
settings.render_engine = "EEVEE"
settings.resolution_x = 32
settings.resolution_y = 32
settings.resolution_scale = 100
settings.render_low = True
settings.render_mid = False
settings.freestyle_edges = False
settings.transparent_background = False
settings.multiview_render = False

collection = bpy.data.collections.new("RenderTest_01_Collection")
scene.collection.children.link(collection)
mesh = bpy.data.meshes.new("RenderTest")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
source = bpy.data.objects.new("SM_RenderTest_01_LOW", mesh)
collection.objects.link(source)
bpy.ops.object.camera_add(location=(0.5, -3.0, 1.0))
camera = bpy.context.object
camera.rotation_euler = (source.location - camera.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = camera

with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / "Pack.blend"))
    settings.output_directory = "//!Renders"
    assert settings.output_directory == "//!Renders"
    queue, count = render_queue._scan_render_queue(settings)
    assert count == 1 and len(queue) == 1
    job = queue[0]
    render_queue._ensure_render_job_directories(queue)
    assert Path(job["output_path"]).parent.is_dir()
    assert render_queue._prepare_scene_for_job(job)
    render_queue._render_current_job(bpy.context, settings, job)
    assert Path(job["output_path"]).is_file(), job["output_path"]
    settings.output_directory = "//!Started"
    assert bpy.ops.object.polygroups_start_render_queue("INVOKE_DEFAULT") == {"RUNNING_MODAL"}
    assert (Path(directory) / "!Started" / "RenderTest_01").is_dir()
    settings.stop_requested = True

print("RENDER QUEUE OUTPUT TEST PASSED")
