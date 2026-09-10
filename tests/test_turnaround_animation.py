"""Blender background smoke test for turnaround setup and state isolation."""

from pathlib import Path
import sys

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

from polygroups_generator.operators.turnaround_animation import _isolate_turnaround, _restore_visibility

snapshot = _isolate_turnaround(scene, collection)
assert not duplicate.hide_render and not duplicate.hide_viewport
assert source.hide_render and source.hide_viewport
_restore_visibility(snapshot)
assert not source.hide_render and not source.hide_viewport

addon_utils.disable(ROOT.name, default_set=True)
print("TURNAROUND_ANIMATION_OK", flush=True)
