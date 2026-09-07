"""Blender background regression for Cutter Draw stroke stabilization."""
import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.object_seam_cutter import _stabilize_stroke_position

settings = bpy.context.scene.polygroups_object_seam_cutter_settings
assert not settings.cutter_draw_stabilize_stroke
assert settings.cutter_draw_stabilize_radius == 25
assert abs(settings.cutter_draw_stabilize_factor - 0.75) < 1e-7

assert _stabilize_stroke_position(None, (10, 5), 20, 0.75) == Vector((10, 5))
current = Vector((0, 0))
assert _stabilize_stroke_position(current, (10, 0), 20, 0.75) == current
lagged = _stabilize_stroke_position(current, (100, 0), 20, 0.75)
assert (lagged - Vector((20, 0))).length < 1e-7
lagged = _stabilize_stroke_position(lagged, (100, 0), 20, 0.75)
assert (lagged - Vector((35, 0))).length < 1e-7

print("CUTTER_DRAW_STABILIZE_TEST_PASSED", flush=True)
addon_utils.disable(ROOT.name, default_set=True)
