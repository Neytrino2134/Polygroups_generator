"""Blender background regression for scene and transparent companion renders."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.render_queue import _render_current_job

scene = bpy.context.scene
settings = scene.polygroups_render_settings
settings.render_engine = "EEVEE"
settings.resolution_x = 32
settings.resolution_y = 32
settings.resolution_scale = 100
settings.transparent_background = True
settings.scene_collection_prefix = "Scene"
settings.freestyle_edges = False

scene_group = bpy.data.collections.new("Scene_Backdrop")
scene.collection.children.link(scene_group)
bpy.ops.mesh.primitive_cube_add()
asset = bpy.context.object
asset.location = (0.0, 0.0, 0.0)
bpy.ops.object.camera_add(location=(0.0, -8.0, 0.0))
camera = bpy.context.object
camera.rotation_euler = (asset.location - camera.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = camera

with TemporaryDirectory() as directory:
    main_path = Path(directory) / "Asset.png"
    transparent_path = Path(directory) / "Asset_transparent.png"
    _render_current_job(bpy.context, settings, {
        "output_path": str(main_path),
        "transparent_output_path": str(transparent_path),
    })
    assert main_path.is_file() and transparent_path.is_file()
    assert not scene_group.hide_render
    main = bpy.data.images.load(str(main_path), check_existing=False)
    transparent = bpy.data.images.load(str(transparent_path), check_existing=False)
    assert main.pixels[3] > 0.99
    assert transparent.pixels[3] < 0.01

addon_utils.disable(ROOT.name, default_set=True)
print("RENDER_TRANSPARENT_COMPANION_OK", flush=True)
