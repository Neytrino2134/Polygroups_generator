"""Verify the combined View Assists header toggle."""
from pathlib import Path
from types import SimpleNamespace
import sys

import addon_utils
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)

from polygroups_generator import seam_object_overlay, uv_checker_overlay
from polygroups_generator.ui import draw_view_assists_header

scene = bpy.context.scene
seams = scene.polygroups_seam_preparation_settings
checker = scene.polygroups_seam_finalization_settings
seams.show_seams_object_mode = False
checker.show_checker_solid_mode = False

assert bpy.ops.wm.airetopo_toggle_view_assists() == {"FINISHED"}
assert seams.show_seams_object_mode and checker.show_checker_solid_mode

seam_object_overlay._BATCH_CACHE = ("key", "batch")
uv_checker_overlay._BATCH_CACHE = ("key", "batch")
assert bpy.ops.wm.airetopo_toggle_view_assists() == {"FINISHED"}
assert not seams.show_seams_object_mode and not checker.show_checker_solid_mode
assert seam_object_overlay._BATCH_CACHE is None
assert uv_checker_overlay._BATCH_CACHE is None

# A mixed state is normalized by enabling both assists.
seams.show_seams_object_mode = True
checker.show_checker_solid_mode = False
assert bpy.ops.wm.airetopo_toggle_view_assists() == {"FINISHED"}
assert seams.show_seams_object_mode and checker.show_checker_solid_mode


class Layout:
    def __init__(self):
        self.button = None

    def row(self, **kwargs):
        return self

    def separator(self):
        pass

    def operator(self, identifier, **kwargs):
        self.button = (identifier, kwargs)
        return SimpleNamespace()


layout = Layout()
draw_view_assists_header(SimpleNamespace(layout=layout), bpy.context)
assert layout.button[0] == "wm.airetopo_toggle_view_assists"
assert layout.button[1]["depress"] is True

print("VIEW_ASSISTS_TOGGLE_TEST_PASSED")
