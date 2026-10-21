"""Real GUI: docked draw inside UI region and native sidebar edge drag."""
import sys
import tempfile
import traceback
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.custom_ui import lifecycle, renderer
p = bpy.context.preferences.addons[ROOT.name].preferences
p.ui_mode = 'UI_PANEL'
log = Path(tempfile.gettempdir()) / 'airetopo_sidebar_embed_test.log'
log.write_text('Starting\n')
state = {'step': -1, 'draws': []}
original_draw = renderer.draw
def record(session, region):
    state['draws'].append((region.type, session.geometry(region)))
    return original_draw(session, region)
renderer.draw = record

def tick():
    try:
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        viewport = next(r for r in area.regions if r.type == 'WINDOW')
        sidebar = next(r for r in area.regions if r.type == 'UI')
        with bpy.context.temp_override(window=window, area=area, region=viewport):
            if state['step'] == -1:
                window.event_simulate(type='ESC', value='PRESS')
                window.event_simulate(type='ESC', value='RELEASE')
                state['step'] = 0
                return .5
            if state['step'] == 0:
                area.spaces.active.show_region_ui = True
                bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
                state['step'] = 1
                return 1
            session = lifecycle.SESSIONS[lifecycle.key_for(bpy.context)]
            assert not session.closed, session.note
            if state['step'] == 1:
                if not state.get('category_clicked'):
                    x, y = sidebar.x+sidebar.width-10, sidebar.y+sidebar.height-245
                    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
                    window.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
                    window.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x, y=y)
                    state['category_clicked'] = True
                    return .7
                assert state['draws'], 'No GPU draw callbacks in UI region'
                assert all(kind == 'UI' for kind, _ in state['draws']), state['draws']
                assert lifecycle.resolve(session) and session.region.type == 'UI'
                state['width'] = sidebar.width
                x, y = sidebar.x+1, sidebar.y + sidebar.height//3
                window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
                window.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
                state['x'], state['y'] = x, y
                state['step'] = 2
                return .5
            if state['step'] == 2:
                window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=state['x']-10, y=state['y'])
                state['step'] = 3
                return .5
            if state['step'] == 3:
                window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=state['x']-80, y=state['y'])
                state['step'] = 4
                return .5
            if state['step'] == 4:
                window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=state['x']-120, y=state['y'])
                state['step'] = 4.5
                return .5
            if state['step'] == 4.5:
                window.event_simulate(type='LEFTMOUSE', value='RELEASE', x=state['x']-120, y=state['y'])
                state['step'] = 5
                return .7
            if state['step'] == 5:
                assert sidebar.width > state['width']+30, (state['width'], sidebar.width)
                assert abs(session.geometry(sidebar)[2] - (sidebar.width-36)) < .01
                state['draws'].clear()
                bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')
                state['step'] = 6
                return .6
            if state['step'] == 6:
                assert state['draws'] and all(kind == 'WINDOW' for kind, _ in state['draws'])
                assert lifecycle.resolve(session) and session.region.type == 'WINDOW'
                state['draws'].clear()
                bpy.ops.wm.airetopo_custom_placement(placement='DOCKED')
                state['step'] = 7
                return .6
            assert state['draws'] and all(kind == 'UI' for kind, _ in state['draws'])
            assert lifecycle.resolve(session) and session.region.type == 'UI'
            log.write_text('SIDEBAR_EMBED_AND_NATIVE_RESIZE_PASSED\n' + str((state['width'], sidebar.width)))
        bpy.ops.wm.quit_blender()
    except Exception:
        with log.open('a') as output:
            output.write('\n' + traceback.format_exc())
        bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(tick, first_interval=1)
