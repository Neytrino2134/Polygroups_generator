"""Blender --background --factory-startup --python-exit-code 1 --python FILE."""
import sys
from pathlib import Path

import addon_utils
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=False)
from polygroups_generator import ui
from polygroups_generator.properties import SECTION_SUBSECTION_PROPERTIES

scene = bpy.context.scene
visibility = scene.airetopo_panel_visibility_settings
narrow = scene.polygroups_seam_finalization_settings
assert 'topic_uv_2' in SECTION_SUBSECTION_PROPERTIES['show_uv_preparation_section']
assert not visibility.topic_uv_2
assert narrow.narrow_island_source == 'UV'
assert narrow.narrow_island_width == 3
assert narrow.narrow_island_min_faces == 8
assert narrow.narrow_island_min_length == 3
assert not narrow.narrow_island_create_edges


class Layout:
    def __init__(self, buttons=None):
        self.buttons = buttons if buttons is not None else []
        self.enabled = True
        self.operator_context = ''

    def box(self):
        return self

    def row(self, **kwargs):
        child = Layout(self.buttons)
        child.enabled = self.enabled
        child.operator_context = self.operator_context
        return child

    def column(self, **kwargs):
        return self

    def prop(self, *args, **kwargs):
        pass

    def label(self, *args, **kwargs):
        pass

    def separator(self, **kwargs):
        pass

    def operator(self, idname, **kwargs):
        properties = type('Button', (), {})()
        if idname == 'mesh.polygroups_split_narrow_islands':
            self.buttons.append((properties, self.enabled, self.operator_context))
        return properties


def draw_buttons():
    layout = Layout()
    ui.draw_section_panel_content(
        ui.VIEW3D_PT_polygroups_uv_preparation, bpy.context,
        layout, 'show_uv_preparation_section',
    )
    return layout.buttons


visibility.show_uv_preparation_section = True
visibility.topic_uv_2 = True
buttons = draw_buttons()
assert [button.action for button, _, _ in buttons] == ['PREVIEW', 'SEAMS', 'SPLIT']
assert all(enabled and context == 'EXEC_DEFAULT' for _, enabled, context in buttons)

narrow.narrow_island_source = 'MESH'
narrow.narrow_island_width = 5
narrow.narrow_island_min_faces = 12
narrow.narrow_island_min_length = 4
narrow.narrow_island_selected_only = True
narrow.narrow_island_create_edges = True
buttons = draw_buttons()
assert [enabled for _, enabled, _ in buttons] == [True, True, False]
assert all(button.create_edges for button, _, _ in buttons)
assert all((button.source, button.width, button.min_faces,
            button.min_length, button.selected_only) == ('MESH', 5, 12, 4, True)
           for button, _, _ in buttons)

search = ui._probe_panel(ui.VIEW3D_PT_polygroups_uv_preparation,
                         bpy.context, 'Narrow Island Splitter')
assert any('topic_uv_2' in key for key in search.groups)
print('NARROW PANEL PASSED')
