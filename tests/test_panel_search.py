"""Verify N-panel search matching and temporary expansion behavior."""
from pathlib import Path
import sys

import addon_utils
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)

from polygroups_generator import ui

context = bpy.context
visibility = context.scene.airetopo_panel_visibility_settings
visibility.panel_search = "mark selected edges"

matches = {
    panel_class.__name__: ui._probe_panel(panel_class, context, visibility.panel_search)
    for panel_class in ui.SECTION_PANEL_CLASSES
}
seams = matches["VIEW3D_PT_polygroups_seam_preparation"]
assert seams.section_match
assert any("topic_seam_prep_2" in key for key in seams.groups)
assert not matches["VIEW3D_PT_polygroups_remesh"].section_match
assert not matches["VIEW3D_PT_polygroups_model_preparation"].section_match


class Layout:
    def __init__(self):
        self.operator_labels = []

    def box(self):
        return self

    def row(self, **kwargs):
        return self

    def column(self, **kwargs):
        return self

    def prop(self, *args, **kwargs):
        return self

    def operator(self, *args, **kwargs):
        self.operator_labels.append(kwargs.get("text", ""))
        return type("OperatorProperties", (), {})()

    def separator(self):
        return None


visibility.show_seam_preparation_section = False
key = visibility.path_from_id() + ".show_seam_preparation_section"
ui._SEARCH_FILTER_GROUPS = {key}
try:
    content = ui.draw_collapsible_box(
        Layout(), visibility, "show_seam_preparation_section", "Seam Preparation", "EDGE_SEAM"
    )
finally:
    ui._SEARCH_FILTER_GROUPS = None
assert content is not None
assert not visibility.show_seam_preparation_section

# Inside a matching branch, controls with unrelated visible names are omitted.
mark_result = ui._probe_panel(ui.VIEW3D_PT_polygroups_seam_preparation, context, "mark")
recording = Layout()
ui._SEARCH_FILTER_GROUPS = mark_result.groups
ui._SEARCH_FILTER_TERMS = mark_result.terms
try:
    filtered = ui._FilteredLayout(recording, mark_result.terms)
    ui.draw_section_panel_content(
        ui.VIEW3D_PT_polygroups_seam_preparation,
        context,
        filtered,
        "show_seam_preparation_section",
    )
finally:
    ui._SEARCH_FILTER_GROUPS = None
    ui._SEARCH_FILTER_TERMS = ()
named_operators = [label for label in recording.operator_labels if label]
assert named_operators
assert all("mark" in label.casefold() for label in named_operators), named_operators

print("PANEL_SEARCH_TESTS_PASSED")
