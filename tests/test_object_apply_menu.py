"""Blender smoke test for Apply Cutter Seams in Object > Apply."""

from pathlib import Path
import sys
from types import SimpleNamespace

import bpy


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
import polygroups_generator as addon
from polygroups_generator.ui import draw_object_apply_menu


calls = []


class FakeLayout:
    def separator(self):
        calls.append(("separator", {}))

    def operator(self, operator_id, **kwargs):
        calls.append((operator_id, kwargs))
        return SimpleNamespace()


draw_object_apply_menu(SimpleNamespace(layout=FakeLayout()), bpy.context)
assert calls[0][0] == "separator"
assert calls[1][0] == "object.polygroups_apply_cutter_seams"
assert calls[1][1]["icon"] == "EDGE_SEAM"

addon.register()
try:
    # Successful full registration verifies the public Menu.append path.
    pass
finally:
    addon.unregister()
print("OBJECT_APPLY_MENU_OK", flush=True)
