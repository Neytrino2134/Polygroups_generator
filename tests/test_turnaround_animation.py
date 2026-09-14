"""Blender background smoke test for turnaround setup and state isolation."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

scene = bpy.context.scene
settings = scene.polygroups_render_settings
settings.animation_frame_count = 300
visibility = scene.airetopo_panel_visibility_settings
assert hasattr(visibility, "topic_render_5")

bpy.ops.mesh.primitive_cube_add(location=(3.0, 1.0, 2.0))
source = bpy.context.active_object
source.name = "Turnaround Test"
assert bpy.ops.object.polygroups_prepare_turnaround_animation() == {"FINISHED"}

collection = bpy.data.collections[settings.animation_collection_name]
duplicate = bpy.data.objects[settings.animation_object_name]
root = duplicate.parent
assert collection.get("polygroups_turnaround_collection")
assert root is not None and root.get("polygroups_turnaround_empty")
assert scene.frame_start == 1 and scene.frame_end == 300
from polygroups_generator.operators.turnaround_animation import _action_fcurves

curves = _action_fcurves(root.animation_data.action)
assert len(curves) == 1
curve = curves[0]
assert [point.co.x for point in curve.keyframe_points] == [1.0, 300.0]
assert all(point.interpolation == "LINEAR" for point in curve.keyframe_points)
assert abs(root.location.x - 3.0) < 1.0e-6

from polygroups_generator.operators.turnaround_animation import (
    _configure_animation_output,
    _isolate_turnaround,
    _render_snapshot,
    _restore_render,
    _restore_visibility,
)

snapshot = _isolate_turnaround(scene, collection)
assert not duplicate.hide_render and not duplicate.hide_viewport
assert source.hide_render and source.hide_viewport
_restore_visibility(snapshot)
assert not source.hide_render and not source.hide_viewport

# Optional Scene/Light/Camera collections stay visible, including nested meshes.
scene_group = bpy.data.collections.new("Scene.001")
scene.collection.children.link(scene_group)
nested_group = bpy.data.collections.new("Environment")
scene_group.children.link(nested_group)
light_group = bpy.data.collections.new("Light_Rig")
scene.collection.children.link(light_group)
camera_group = bpy.data.collections.new("Camera.002")
scene.collection.children.link(camera_group)
other_group = bpy.data.collections.new("Props")
scene.collection.children.link(other_group)
protected_objects = []
for index, group in enumerate((nested_group, light_group, camera_group, other_group)):
    mesh = bpy.data.meshes.new(f"Backdrop {index}")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(f"Backdrop {index}", mesh)
    group.objects.link(obj)
    protected_objects.append(obj)
scene_group.hide_render = True
protected_objects[1].hide_viewport = True

snapshot = _isolate_turnaround(scene, collection)
assert all(obj.hide_render for obj in protected_objects)
_restore_visibility(snapshot)
snapshot = _isolate_turnaround(scene, collection, keep_named_collections=True)
assert all(not obj.hide_render and not obj.hide_viewport for obj in protected_objects[:3])
assert protected_objects[3].hide_render and protected_objects[3].hide_viewport
assert not scene_group.hide_render and not nested_group.hide_render
assert source.hide_render and source.hide_viewport
_restore_visibility(snapshot)
assert scene_group.hide_render and protected_objects[1].hide_viewport

# Media Type must be set to Video before FFmpeg becomes a valid file format.
render_state = _render_snapshot(scene)
assert settings.animation_media_type == "VIDEO"
assert settings.animation_container == "MKV"
for container, extension, codec in (
    ("MKV", ".mkv", "H264"),
    ("MPEG4", ".mp4", "H264"),
    ("WEBM", ".webm", "WEBM"),
    ("QUICKTIME", ".mov", "H264"),
):
    settings.animation_container = container
    output = _configure_animation_output(scene, settings, "/tmp/turnaround")
    assert output.endswith(extension)
    assert scene.render.image_settings.media_type == "VIDEO"
    assert scene.render.image_settings.file_format == "FFMPEG"
    assert scene.render.ffmpeg.format == container and scene.render.ffmpeg.codec == codec
settings.animation_media_type = "IMAGE"
assert _configure_animation_output(scene, settings, "/tmp/turnaround").endswith("_####.png")
assert scene.render.image_settings.media_type == "IMAGE"
assert scene.render.image_settings.file_format == "PNG"
_restore_render(scene, render_state)
assert _render_snapshot(scene) == render_state

# Render a tiny Eevee turnaround to exercise the actual FFmpeg output path.
settings.animation_media_type = "VIDEO"
settings.animation_container = "MKV"
settings.animation_frame_count = 2
settings.resolution_x = settings.resolution_y = 32
settings.render_engine = "EEVEE"
settings.animation_keep_scene_collections = True
bpy.ops.object.camera_add(location=(3.0, -7.0, 3.0))
camera = bpy.context.object
camera.rotation_euler = (duplicate.matrix_world.translation - camera.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = camera
with TemporaryDirectory() as directory:
    settings.output_directory = directory
    rendered_frames = []
    observed_visibility = []

    def record_visibility(rendered_scene, *args):
        if rendered_scene == scene:
            observed_visibility.append(tuple(obj.hide_render for obj in protected_objects))

    def record_frame(rendered_scene, *args):
        if rendered_scene == scene:
            rendered_frames.append(rendered_scene.frame_current)

    bpy.app.handlers.render_post.append(record_frame)
    bpy.app.handlers.render_pre.append(record_visibility)
    try:
        assert bpy.ops.object.polygroups_render_turnaround_animation() == {"FINISHED"}
    finally:
        bpy.app.handlers.render_post.remove(record_frame)
        bpy.app.handlers.render_pre.remove(record_visibility)
    assert len(rendered_frames) == 2
    assert observed_visibility and all(values == (False, False, False, True) for values in observed_visibility)
    assert scene_group.hide_render and protected_objects[1].hide_viewport
    assert settings.animation_progress == 100.0
    assert settings.animation_last_output.endswith(".mkv")
    assert Path(settings.animation_last_output).is_file()
    settings.animation_media_type = "IMAGE"
    assert bpy.ops.object.polygroups_render_turnaround_animation() == {"FINISHED"}
    assert len(list(Path(directory).rglob("Turnaround_Test_Turnaround_*.png"))) == 2
assert _render_snapshot(scene) == render_state

addon_utils.disable(ROOT.name, default_set=True)
print("TURNAROUND_ANIMATION_OK", flush=True)
