"""Separate Blender --factory-startup --python tests/test_standalone_windows_ui.py."""
import contextlib
import io
import json
import sys
import tempfile
import traceback
from unittest.mock import patch
import os
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / 'airetopo_standalone_test.log'
LOG.write_text('Starting\n')
bpy.context.preferences.view.show_splash = False

def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator import ui
    from polygroups_generator.core.window_schema import Layout
    from polygroups_generator.operators.detached_groups import SESSIONS, cleanup_windows
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    output = io.StringIO()
    with bpy.context.temp_override(window=window, area=area, region=region), contextlib.redirect_stdout(output):
        groups = ui.collect_window_groups(bpy.context)
        assert len(set(g['section'] for g in groups)) == 13
        schemas = []
        for group in groups:
            layout = Layout()
            ui.draw_detached_group(bpy.context, layout, group['section'], group['group'])
            json.dumps(layout.items)
            schemas.append(dict(group=group, items=layout.items))
        assert 'failed to draw' not in output.getvalue(), output.getvalue()
        (Path(tempfile.gettempdir()) / 'airetopo_schemas.json').write_text(json.dumps(schemas), encoding='utf8')
        group = next(g for g in groups if g['group'].endswith('topic_batch_2'))
        with patch.object(bpy.utils, 'user_resource', return_value=tempfile.gettempdir()):
            assert bpy.ops.wm.airetopo_detach_group(**group) == {'FINISHED'}
    yield 2
    assert len(SESSIONS) == 1
    session = SESSIONS[0]
    assert session.authenticated and session.process.poll() is None
    assert len(bpy.context.window_manager.windows) == 1, 'Must not duplicate a 3D window'
    if os.name == 'nt':
        assert session.owner_handle, 'Blender owner window was not detected'
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        handles = []
        @callback_type
        def visit(hwnd, _):
            process = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(process))
            if process.value == session.process.pid and user.IsWindowVisible(hwnd):
                handles.append(hwnd)
            return True
        user.EnumWindows(visit, 0)
        assert handles, 'Standalone client window not found'
        assert any(user.GetWindow(hwnd, 4) == session.owner_handle for hwnd in handles), (
            'Standalone panel is not owned by Blender'
        )
    with session.context():
        model = session.model()
        item = next(i for i in model['items'] if i.get('type') == 'BOOLEAN')
        binding = session.bindings[item['id']]
        previous = getattr(binding[1], binding[2])
        session.handle(dict(type='action', id=item['id'], revision=model['revision'], value=not previous))
        assert getattr(binding[1], binding[2]) == (not previous)
        # Stale / arbitrary commands cannot mutate RNA.
        session.handle(dict(type='action', id=item['id'], revision='stale', value=previous))
        assert getattr(binding[1], binding[2]) == (not previous)
        group = next(g for g in groups if g['group'].endswith('show_selection_group'))
        session.handle(dict(type='select', **group))
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        model = session.model()
        # Select more on empty selection is a safe real operator dispatch.
        key = next(k for k,v in session.bindings.items() if v[0]=='operator' and v[1]=='mesh.select_more')
        session.outgoing = b''
        session.handle(dict(type='action', id=key, revision=model['revision']))
        assert json.loads(session.outgoing.splitlines()[-1])['ok'] is True
        bpy.ops.object.mode_set(mode='OBJECT')
    yield .6
    child = session.process
    cleanup_windows()
    yield .4
    assert child.poll() is not None and not SESSIONS
    addon_utils.disable(ROOT.name, default_set=True)
    LOG.write_text(f'PASSED: {len(groups)} group schemas, independent process, RNA edits, operator dispatch, stale rejection, cleanup\n')

steps = run()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
bpy.app.timers.register(tick, first_interval=1)
