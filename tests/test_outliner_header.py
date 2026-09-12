"""Blender smoke test for compact AI Retopo controls in the Outliner header."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
from polygroups_generator import ui
from polygroups_generator.ui import draw_object_select_tool_actions, draw_outliner_header


calls = []


class FakeRow:
    def separator(self):
        pass

    def operator(self, operator_id, **kwargs):
        properties = SimpleNamespace()
        calls.append((operator_id, kwargs, properties))
        return properties


class FakeLayout:
    def row(self, **_kwargs):
        return FakeRow()


draw_outliner_header(SimpleNamespace(layout=FakeLayout()), None)
assert [call[0] for call in calls] == [
    "object.polygroups_generated_collection",
    "object.polygroups_generated_collection",
    "object.polygroups_generated_collection",
    "object.polygroups_object_visibility",
    "object.polygroups_object_visibility",
    "object.polygroups_object_visibility",
    "object.polygroups_object_visibility",
]
assert calls[0][2].action == "PREVIOUS"
assert calls[1][2].action == "NEXT"
assert calls[2][2].action == "ISOLATE"
assert calls[3][2].prefix == "Highpoly_" and calls[3][2].hidden is True
assert calls[4][2].prefix == "Highpoly_" and calls[4][2].hidden is False
assert calls[5][2].prefix == "Retopo_" and calls[5][2].hidden is True
assert calls[6][2].prefix == "Retopo_" and calls[6][2].hidden is False
assert [call[1]["text"] for call in calls] == ["Prev", "Next", "", "", "", "", ""]


header_calls = []


class HeaderLayout:
    def row(self, **_kwargs):
        return self

    def separator(self):
        pass

    def label(self, **_kwargs):
        pass

    def operator(self, operator_id, **kwargs):
        properties = SimpleNamespace()
        header_calls.append((operator_id, kwargs, properties))
        return properties


tools = SimpleNamespace(
    from_space_view3d_mode=lambda *_args, **_kwargs: SimpleNamespace(idname="builtin.select_box")
)
header_context = SimpleNamespace(mode="OBJECT", workspace=SimpleNamespace(tools=tools))
with patch.object(ui, "get_remesh_preset_counts", return_value=[("LOW", 1000)]):
    draw_object_select_tool_actions(
        SimpleNamespace(layout=HeaderLayout()),
        header_context,
    )

assert [call[0] for call in header_calls[:3]] == [
    "object.polygroups_generated_collection",
    "object.polygroups_generated_collection",
    "object.polygroups_checked_quad_remesh",
]
assert header_calls[0][2].action == "PREVIOUS"
assert header_calls[1][2].action == "NEXT"
assert header_calls[2][1]["text"] == "LOW"
print("OUTLINER_HEADER_OK", flush=True)
