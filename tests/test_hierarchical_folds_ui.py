"""Real clicks and key events in docked/floating UI Panel; --enable-event-simulate."""
import os
import sys
import traceback
from pathlib import Path
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / 'tests'))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.ui_folds import section_folds, step_folds
from polygroups_generator.custom_ui import lifecycle
from custom_ui_test_support import open_panel

prefs = bpy.context.preferences.addons[ROOT.name].preferences
prefs.ui_mode = 'UI_PANEL'
prefs.enable_section_number_hotkeys = True
prefs.section_hotkey_scope = 'SIDEBAR'
open_panel()
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
mesh = bpy.context.scene.polygroups_mesh_finalization_settings

def click(session, action):
    hit = next(hit for hit in session.hits if hit[1][0] == action)
    x, y, w, h = hit[0]
    x, y = int(region.x+x+w/2), int(region.y+y+h/2)
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    window.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
    window.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x, y=y)
    return x, y

def key(kind, point):
    x, y = point
    window.event_simulate(type=kind, value='PRESS', x=x, y=y, shift=kind == 'EQUAL')
    window.event_simulate(type=kind, value='RELEASE', x=x, y=y, shift=kind == 'EQUAL')

def run():
    yield 1
    session = lifecycle.SESSIONS[lifecycle.key_for(bpy.context)]
    session.select(11)
    roots = section_folds(bpy.context, 11, include_sections=False)
    for placement in ('DOCKED', 'FLOATING'):
        bpy.ops.wm.airetopo_custom_placement(placement=placement)
        for root in roots:
            root.set(False)
            root.close_children()
        session.refresh(bpy.context)
        area.tag_redraw()
        yield .3
        click(session, 'expand')
        yield .3
        assert all(root.opened() for root in roots) and not mesh.show_unity_asset_render_settings
        click(session, 'expand')
        yield .3
        assert mesh.show_unity_asset_render_settings
        point = click(session, 'fold')
        yield .3
        assert not mesh.show_unity_asset_render_settings and all(root.opened() for root in roots)
        click(session, 'fold')
        yield .3
        assert not any(root.opened() for root in roots)
        plus, minus = ('EQUAL', 'MINUS') if placement == 'DOCKED' else ('NUMPAD_PLUS', 'NUMPAD_MINUS')
        key(plus, point)
        yield .3
        assert all(root.opened() for root in roots) and not mesh.show_unity_asset_render_settings
        key(plus, point)
        yield .3
        assert mesh.show_unity_asset_render_settings
        key(minus, point)
        yield .3
        assert not mesh.show_unity_asset_render_settings and all(root.opened() for root in roots)
        key(minus, point)
        yield .3
        assert not any(root.opened() for root in roots)
        print('HIERARCHICAL_REAL_UI_OK', placement, flush=True)

steps = run()
def tick():
    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            return next(steps)
    except StopIteration:
        print('HIERARCHICAL_REAL_UI_TESTS_PASSED', flush=True)
        bpy.ops.wm.quit_blender()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(1)
    return None
bpy.app.timers.register(tick, first_interval=.5)
