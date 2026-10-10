"""Actual registered fold buttons/hotkeys, all 13 sections, all discovered depths."""
import sys
from pathlib import Path
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.ui_folds import section_folds, step_folds, model_folds
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator.properties import SECTION_VISIBILITY_PROPERTIES

context = bpy.context
visibility = context.scene.airetopo_panel_visibility_settings
visibility.single_section_mode = False
prefs = context.preferences.addons[ROOT.name].preferences
session_before = (prefs.show_panel_save_restart, prefs.show_panel_autosave)

def entries(roots, depth=1):
    for fold in roots:
        yield depth, fold
        yield from entries(fold.children, depth+1)

def closed(roots):
    for _, fold in entries(roots):
        fold.set(False)

for mode in ('OBJECT', 'EDIT', 'SCULPT'):
    bpy.ops.object.mode_set(mode=mode)
    for index in range(13):
        roots = section_folds(context, index)
        closed(roots)
        maximum = max(depth for depth, _ in entries(roots))
        for expected in range(1, maximum+1):
            assert step_folds(roots, True) == expected, (mode, index, expected)
            for depth, fold in entries(roots):
                assert fold.opened() == (depth <= expected), (mode, index, fold.name, depth)
        assert step_folds(roots, True) is None
        for expected in range(maximum, 0, -1):
            assert step_folds(roots, False) == expected
            for depth, fold in entries(roots):
                assert fold.opened() == (depth < expected), (mode, index, fold.name, depth)
        assert step_folds(roots, False) is None
        print('HIERARCHICAL_SECTION_OK', mode, index+1, maximum, flush=True)
bpy.ops.object.mode_set(mode='OBJECT')

# The reported regression: actual Mesh Finalization folds reside in its own RNA group.
mesh = context.scene.polygroups_mesh_finalization_settings
roots = section_folds(context, 11, include_sections=False)
closed(roots)
assert bpy.ops.object.airetopo_set_section_subsection_visibility(
    section_property='show_mesh_finalization_section', visible=True) == {'FINISHED'}
assert all(root.opened() for root in roots)
assert mesh.show_unity_rename_settings and not mesh.show_unity_asset_render_settings
bpy.ops.object.airetopo_set_section_subsection_visibility(section_property='show_mesh_finalization_section', visible=True)
assert mesh.show_unity_asset_render_settings and mesh.show_unity_turnaround_settings
bpy.ops.object.airetopo_set_section_subsection_visibility(section_property='show_mesh_finalization_section', visible=False)
assert not mesh.show_unity_asset_render_settings and mesh.show_unity_rename_settings
bpy.ops.object.airetopo_set_section_subsection_visibility(section_property='show_mesh_finalization_section', visible=False)
assert not any(root.opened() for root in roots)
print('MESH_FINALIZATION_BUTTON_REGRESSION_OK', flush=True)

# Hidden descendant defaults cannot consume a collapse click or skip an expansion floor.
roots[0].set(False)
for root in roots:
    root.close_children()
mesh.show_unity_asset_render_settings = True
assert step_folds(roots, False) is None
assert step_folds(roots, True) == 1
assert not mesh.show_unity_asset_render_settings

# Global buttons and hotkeys share the same ordered levels, excluding session settings.
roots = section_folds(context)
closed(roots)
maximum = max(depth for depth, _ in entries(roots))
for depth in range(1, maximum+1):
    bpy.ops.object.airetopo_set_all_section_visibility(visible=True)
    assert all(fold.opened() == (level <= depth) for level, fold in entries(roots))
area = next(area for area in context.screen.areas if area.type == 'VIEW_3D')
region = next(region for region in area.regions if region.type == 'WINDOW')
prefs.enable_section_number_hotkeys = True
prefs.section_hotkey_scope = 'VIEWPORT'
prefs.ui_mode = 'CLASSIC'
with context.temp_override(area=area, region=region):
    for depth in range(maximum, 0, -1):
        assert bpy.ops.wm.airetopo_section_set_all(visible=False) == {'FINISHED'}
        assert all(fold.opened() == (level < depth) for level, fold in entries(roots))
    for depth in range(1, maximum+1):
        bpy.ops.wm.airetopo_section_set_all(visible=True)
        assert all(fold.opened() == (level <= depth) for level, fold in entries(roots))
    for mode in ('CUSTOM', 'UI_PANEL'):
        prefs.ui_mode = mode
        prefs.custom_ui_section = 11
        prefs.custom_ui_show_session = False
        local = section_folds(context, 11, include_sections=False)
        bpy.ops.wm.airetopo_section_set_all(visible=False)
        assert all(root.opened() for root in local)
        assert not mesh.show_unity_asset_render_settings
        bpy.ops.wm.airetopo_section_set_all(visible=False)
        assert not any(root.opened() for root in local)
        other = context.scene.polygroups_baking_settings.show_auto_pack_uv_settings
        bpy.ops.wm.airetopo_section_set_all(visible=True)
        assert all(root.opened() for root in local)
        assert context.scene.polygroups_baking_settings.show_auto_pack_uv_settings == other
        bpy.ops.wm.airetopo_section_set_all(visible=True)
        assert mesh.show_unity_asset_render_settings
        # Overlay All/Fold uses the same model-derived tree, including deep nodes.
        assert step_folds(model_folds(capture(context, 11), context), False) == 2
        assert not mesh.show_unity_asset_render_settings
        assert step_folds(model_folds(capture(context, 11), context), False) == 1
        assert not mesh.show_unity_rename_settings
        # Restore for the next mode.
        step_folds(local, True)
        step_folds(local, True)
assert session_before == (prefs.show_panel_save_restart, prefs.show_panel_autosave)
print('HIERARCHICAL_BUTTON_HOTKEY_AND_OVERLAY_OK', maximum, flush=True)
