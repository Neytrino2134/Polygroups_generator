"""Blender smoke test for compact AI Retopo controls in the Outliner header."""

from pathlib import Path
import sys
from types import SimpleNamespace


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
from polygroups_generator.ui import draw_outliner_header


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
    "object.polygroups_object_visibility",
    "object.polygroups_object_visibility",
    "object.polygroups_object_visibility",
    "object.polygroups_object_visibility",
]
assert calls[0][2].action == "PREVIOUS"
assert calls[1][2].action == "NEXT"
assert calls[2][2].prefix == "Retopo_" and calls[2][2].hidden is True
assert calls[3][2].prefix == "Retopo_" and calls[3][2].hidden is False
assert calls[4][2].prefix == "Highpoly_" and calls[4][2].hidden is True
assert calls[5][2].prefix == "Highpoly_" and calls[5][2].hidden is False
assert [call[1]["text"] for call in calls] == ["", "", "L", "L", "H", "H"]
print("OUTLINER_HEADER_OK", flush=True)
