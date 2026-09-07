"""Verify Smart Seam Generation invokes shared Smart Relax settings."""
import importlib
import sys
from pathlib import Path

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

module = importlib.import_module("polygroups_generator.operators.smart_angle_seams")
obj = bpy.context.active_object
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="FACE")
bpy.ops.mesh.select_all(action="SELECT")

settings = bpy.context.scene.polygroups_seam_preparation_settings
settings.smart_seam_auto_relax = True
settings.seam_relax_iterations = 6
settings.seam_relax_use_corner_angle = False
settings.seam_relax_protection_radius = 2

calls = []
original_relax = module.relax_seams


def record_relax(context, mode, iterations, angle, radius,
                 use_corner_angle=True, select_result=True,
                 selected_area_only=False):
    calls.append((context, mode, iterations, angle, radius,
                  use_corner_angle, select_result, selected_area_only))
    return 7, 3


try:
    module.relax_seams = record_relax
    assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {"FINISHED"}
finally:
    module.relax_seams = original_relax

assert len(calls) == 1
assert calls[0][1] == "SMART"
assert calls[0][2] == 6
assert calls[0][4] == 2
assert calls[0][5] is False
assert calls[0][6] is False
assert calls[0][7] is True

print("SMART_AUTO_RELAX_TEST_PASSED")
