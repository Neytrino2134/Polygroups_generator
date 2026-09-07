"""Check the shared Auto UV controls used by Edit Mode seam tools."""
import sys
from pathlib import Path

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator import tools


class LayoutRecorder:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
        self.enabled = True

    def separator(self, **kwargs):
        self.calls.append(("separator", kwargs))

    def row(self, **kwargs):
        return LayoutRecorder(self.calls)

    def prop(self, data, name, **kwargs):
        self.calls.append(("prop", name, self.enabled, data, kwargs))


settings = bpy.context.scene.polygroups_seam_finalization_settings
settings.auto_unwrap_after_seam = False
layout = LayoutRecorder()
tools._draw_seam_auto_uv_settings(bpy.context, layout)
props = [call for call in layout.calls if call[0] == "prop"]
assert [call[1] for call in props] == [
    "auto_unwrap_after_seam",
    "auto_average_islands_scale_after_unwrap",
]
assert props[0][2] is True
assert props[1][2] is False
assert all(call[3].path_from_id() == settings.path_from_id() for call in props)

settings.auto_unwrap_after_seam = True
layout = LayoutRecorder()
tools._draw_seam_auto_uv_settings(bpy.context, layout)
assert [call for call in layout.calls if call[0] == "prop"][1][2] is True

print("SEAM_AUTO_UV_HEADER_TEST_PASSED")
