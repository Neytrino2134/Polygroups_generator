"""Session UI stays pinned while only the thirteen workflow sections are searched."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator import ui
from polygroups_generator.custom_ui.schema import Layout, walk
from polygroups_generator.custom_ui import lifecycle, renderer

prefs = bpy.context.preferences.addons[ROOT.name].preferences
visibility = bpy.context.scene.airetopo_panel_visibility_settings
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(window=window, area=area, region=region):
    prefs.ui_mode = 'CLASSIC'
    prefs.show_panel_save_restart = prefs.show_panel_autosave = True
    visibility.show_seam_preparation_section = False
    for language in ('EN', 'RU'):
        prefs.interface_language = language
        for query in ('mark', 'Autosave', 'zz_no_workflow_matches_zz'):
            visibility.panel_search = query
            for opened in (True, False):
                prefs.show_panel_session_status = opened
                model = Layout(key='native-search')
                with patch.object(ui, '_probe_panel', wraps=ui._probe_panel) as probe:
                    ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=model), bpy.context)
                assert not model.errors, model.errors
                assert [call.args[0] for call in probe.call_args_list] == list(ui.SECTION_PANEL_CLASSES), [(call.args[0].__name__) for call in probe.call_args_list]
                nodes = list(walk(model.node))
                assert any(b[0] == 'property' and b[2] == 'show_panel_session_status' for b in model.bindings.values())
                assert any(n.get('property') == 'panel_search' for n in nodes)
                ops = {b[1] for b in model.bindings.values() if b[0] == 'operator'}
                assert ('wm.airetopo_relocate_project' in ops) == opened
                assert ('wm.airetopo_open_recent_autosave' in ops) == opened
                assert prefs.show_panel_session_status == opened
                assert not visibility.show_seam_preparation_section
                assert ui._SEARCH_FILTER_GROUPS is None and ui._SEARCH_FILTER_TERMS == ()

    prefs.show_panel_session_status = True
    prefs.interface_language = 'EN'
    prefs.ui_mode = 'CUSTOM'
    prefs.custom_ui_show_session = True
    native = Layout(key='custom-session')
    ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=native), bpy.context)
    assert not native.errors, native.errors
    assert any(b[0] == 'operator' and b[1] == 'wm.airetopo_relocate_project' for b in native.bindings.values())

    session = lifecycle.Session(bpy.context)
    session.query = 'zz_no_workflow_matches_zz'
    session.select(9, True)
    session.refresh(bpy.context)
    assert renderer.workflow_query(session) == ''
    assert renderer.height(session.model.node, 420, 1, renderer.workflow_query(session)) == renderer.height(session.model.node, 420, 1)
    assert any(b[0] == 'operator' and b[1] == 'wm.airetopo_relocate_project' for b in session.model.bindings.values())
    session.select(9)
    session.refresh(bpy.context)
    assert renderer.workflow_query(session) == session.query
    assert len(session.model.node['children']) == 13
    assert all(n['kind'] == 'section' for n in session.model.node['children'])
    assert not any(b[0] == 'operator' and b[1] == 'wm.airetopo_relocate_project' for b in session.model.bindings.values())

    session.select(9, True)
    lifecycle.SESSIONS[session.key] = session
    try:
        assert bpy.ops.wm.airetopo_custom_search(session_key=session.key, query='cage') == {'FINISHED'}
        assert not session.show_header
        assert len(session.model.node['children']) == 13
        session.select(9, True)
        session.refresh(bpy.context)
        assert session.query == 'cage' and renderer.workflow_query(session) == ''
    finally:
        lifecycle.SESSIONS.pop(session.key, None)
print('PANEL_SEARCH_SCOPE_TESTS_PASSED')
