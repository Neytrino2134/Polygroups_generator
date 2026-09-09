"""Verify the dedicated Cutter Tweak pie layout and default shortcut."""
from pathlib import Path
from types import SimpleNamespace
import sys

import addon_utils
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)

from polygroups_generator import hotkeys
from polygroups_generator.tools import CUTTER_TOOL_ORDER

preferences = bpy.context.preferences.addons[root.name].preferences
assert not preferences.enable_experimental_features
assert preferences.enable_cutter_tweak_pie_hotkey
assert preferences.cutter_tweak_pie_key == "D"
assert not preferences.cutter_tweak_pie_ctrl and not preferences.cutter_tweak_pie_shift
assert not preferences.cutter_tweak_pie_alt
assert preferences.cutter_tweak_key == "D"
assert preferences.cutter_tweak_ctrl
assert not preferences.cutter_tweak_shift and not preferences.cutter_tweak_alt

cycle_items = [
    item for _keymap, item in hotkeys.KEYMAP_ITEMS
    if item.idname == hotkeys.AIRETOPO_OT_select_cutter_tweak.bl_idname
]
assert len(cycle_items) == 1
cycle_item = cycle_items[0]
assert cycle_item.type == "D" and cycle_item.ctrl and not cycle_item.shift and not cycle_item.alt

menu_items = [
    item for _keymap, item in hotkeys.KEYMAP_ITEMS
    if item.idname == "wm.call_menu_pie"
    and item.properties.name == hotkeys.VIEW3D_MT_airetopo_cutter_tweak_pie.bl_idname
]
assert len(menu_items) == 1
item = menu_items[0]
assert item.type == "D" and not item.ctrl and not item.shift and not item.alt


class Layout:
    def __init__(self):
        self.tools = []
        self.enabled = True

    def menu_pie(self):
        return self

    def row(self):
        return self

    def operator(self, identifier, **kwargs):
        assert identifier == "wm.tool_set_by_id"
        operator = SimpleNamespace(name="")
        self.tools.append(operator)
        return operator

    def separator(self):
        self.tools.append(None)


layout = Layout()
hotkeys.VIEW3D_MT_airetopo_cutter_tweak_pie.draw(SimpleNamespace(layout=layout), bpy.context)
assert len(layout.tools) == 8
assert {operator.name for operator in layout.tools if operator} == set(CUTTER_TOOL_ORDER)

for property_name in (
    "show_preferences_info", "show_preferences_updates", "show_preferences_icons",
    "show_preferences_language", "show_preferences_operations", "show_preferences_remesh",
    "show_preferences_api", "show_preferences_hotkeys", "show_preferences_pie_menu",
    "show_preferences_windows", "show_preferences_dev",
    "enable_experimental_features",
):
    assert property_name in preferences.bl_rna.properties

print("CUTTER_TWEAK_PIE_TESTS_PASSED")
