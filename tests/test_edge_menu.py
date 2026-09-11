"""Smoke test for AI Retopo commands added to Blender's Ctrl+E menu."""

from pathlib import Path
import sys
from types import SimpleNamespace

import addon_utils
import bpy


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))

from polygroups_generator.ui import draw_delete_menu, draw_edge_menu

addon_utils.enable("polygroups_generator")


class Layout:
    def __init__(self):
        self.operators = []
        self.properties = []

    def separator(self):
        pass

    def label(self, **_kwargs):
        pass

    def prop(self, owner, name, **kwargs):
        self.properties.append((owner, name, kwargs))

    def operator(self, identifier, **kwargs):
        self.operators.append((identifier, kwargs.get("text", "")))
        return SimpleNamespace()


layout = Layout()
draw_edge_menu(SimpleNamespace(layout=layout), bpy.context)

assert layout.operators[:2] == [
    ("mesh.polygroups_connect_vertex_seam", "Connect Vertices with Seam"),
    ("mesh.polygroups_edge_seam_path", "Connect Vertices with Edge Seam Path"),
]
assert layout.properties[1][0] == bpy.context.scene.polygroups_seam_finalization_settings
assert layout.properties[1][1] == "auto_unwrap_after_seam"
assert layout.properties[1][2]["toggle"] is True

delete_layout = Layout()
draw_delete_menu(SimpleNamespace(layout=delete_layout), bpy.context)
assert delete_layout.operators == [
    ("mesh.polygroups_delete_and_fill", "Delete and Fill"),
]
print("EDGE_MENU_OK", flush=True)
