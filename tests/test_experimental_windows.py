"""Verify that floating-window controls are gated by Experimental Features."""
from pathlib import Path
from types import SimpleNamespace
import sys

import addon_utils
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)

from polygroups_generator import ui


class Layout:
    def __init__(self):
        self.operators = []
        self.alignment = "LEFT"

    def box(self):
        return self

    def row(self, **_kwargs):
        return self

    def column(self, **_kwargs):
        return self

    def prop(self, *_args, **_kwargs):
        return None

    def separator(self):
        return None

    def operator(self, identifier, **kwargs):
        operator = SimpleNamespace()
        self.operators.append((identifier, kwargs, operator))
        return operator


preferences = bpy.context.preferences.addons[root.name].preferences
settings = SimpleNamespace(show_test_group=True, path_from_id=lambda: "scene.test_settings")
ui._DRAWING_SECTION = type("TestSection", (), {})
try:
    preferences.enable_experimental_features = False
    disabled_layout = Layout()
    ui.draw_collapsible_box(disabled_layout, settings, "show_test_group", "Test", "TOOL_SETTINGS")
    assert not any(identifier == "wm.airetopo_detach_group" for identifier, _, _ in disabled_layout.operators)

    preferences.enable_experimental_features = True
    enabled_layout = Layout()
    ui.draw_collapsible_box(enabled_layout, settings, "show_test_group", "Test", "TOOL_SETTINGS")
    detached = [entry for entry in enabled_layout.operators if entry[0] == "wm.airetopo_detach_group"]
    assert len(detached) == 1
    assert detached[0][1]["icon"] == "XRAY"
finally:
    ui._DRAWING_SECTION = None
    preferences.enable_experimental_features = False

print("EXPERIMENTAL WINDOWS TEST PASSED")
