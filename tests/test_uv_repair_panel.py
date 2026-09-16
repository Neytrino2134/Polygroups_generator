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
settings = scene.polygroups_seam_finalization_settings
assert 'topic_uv_3' in SECTION_SUBSECTION_PROPERTIES['show_uv_preparation_section']
assert not visibility.topic_uv_3
assert settings.uv_repair_threshold == 4.0
assert abs(settings.uv_repair_grow_threshold - 1.8) < 1e-5
assert (settings.uv_repair_min_faces, settings.uv_repair_smooth_steps) == (6, 2)
assert abs(settings.uv_repair_surface_angle - 0.7853981634) < 1e-5
assert settings.uv_repair_create_edges
assert settings.uv_repair_merge_small_islands
assert settings.uv_repair_pin_generated
assert settings.uv_repair_smart_relax
assert settings.uv_repair_average_island_scale
assert settings.uv_repair_native_pack
assert settings.uv_repair_cleanup_artifacts
assert settings.uv_repair_artifact_method == 'MERGE_CENTER'

class Layout:
    def __init__(self, buttons=None, artifact_buttons=None):
        self.buttons = buttons if buttons is not None else []
        self.artifact_buttons = artifact_buttons if artifact_buttons is not None else []
        self.operator_context = ''
        self.enabled = True
    def box(self): return self
    def row(self, **kwargs): return self
    def column(self, **kwargs): return self
    def prop(self, *args, **kwargs): pass
    def label(self, *args, **kwargs): pass
    def separator(self, **kwargs): pass
    def operator(self, idname, **kwargs):
        button = type('Button', (), {})()
        if idname == 'mesh.polygroups_repair_uv_stretch':
            self.buttons.append(button)
        if idname == 'mesh.polygroups_uv_artifact_cleanup':
            self.artifact_buttons.append(button)
        return button

visibility.show_uv_preparation_section = True
visibility.topic_uv_3 = True
layout = Layout()
ui.draw_section_panel_content(ui.VIEW3D_PT_polygroups_uv_preparation, bpy.context,
                              layout, 'show_uv_preparation_section')
assert [button.action for button in layout.buttons] == ['SELECT', 'REPAIR']
for button in layout.buttons:
    assert button.threshold == settings.uv_repair_threshold
    assert button.grow_threshold == settings.uv_repair_grow_threshold
    assert button.min_faces == settings.uv_repair_min_faces
    assert button.smooth_steps == settings.uv_repair_smooth_steps
    assert button.surface_angle == settings.uv_repair_surface_angle
    assert button.selected_only == settings.uv_repair_selected_only
    assert button.sharp_preference == settings.uv_repair_sharp_preference
    assert button.create_edges == settings.uv_repair_create_edges
    assert button.merge_small_islands == settings.uv_repair_merge_small_islands
    assert button.small_island_threshold == settings.uv_repair_small_island_threshold
    assert button.pin_generated == settings.uv_repair_pin_generated
    assert button.smart_relax == settings.uv_repair_smart_relax
    assert button.average_island_scale == settings.uv_repair_average_island_scale
    assert button.native_pack == settings.uv_repair_native_pack
    assert button.cleanup_artifacts == settings.uv_repair_cleanup_artifacts
    assert button.artifact_method == settings.uv_repair_artifact_method
    assert button.artifact_max_faces == settings.uv_repair_artifact_max_faces
    assert button.artifact_stretch == settings.uv_repair_artifact_stretch
    assert button.artifact_compactness == settings.uv_repair_artifact_compactness
assert [button.action for button in layout.artifact_buttons] == ['SELECT', 'APPLY']
for button in layout.artifact_buttons:
    assert button.method == settings.uv_repair_artifact_method
    assert button.max_faces == settings.uv_repair_artifact_max_faces
    assert button.stretch_threshold == settings.uv_repair_artifact_stretch
    assert button.compactness_threshold == settings.uv_repair_artifact_compactness
    assert button.selected_only == settings.uv_repair_selected_only

search = ui._probe_panel(ui.VIEW3D_PT_polygroups_uv_preparation,
                         bpy.context, 'Smart UV Repair')
assert any('topic_uv_3' in key for key in search.groups)
print('UV REPAIR PANEL PASSED')
