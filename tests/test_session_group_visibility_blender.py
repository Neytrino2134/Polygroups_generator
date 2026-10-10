"""Native draw path: all independent Save/Autosave fold combinations."""
from pathlib import Path
from types import SimpleNamespace
import sys,bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator import ui
from polygroups_generator.custom_ui.schema import Layout,walk
# Native UILayout has no GPU capture hook; exercise that native path even
# when Custom delegates its session draw with _CUSTOM_CAPTURING enabled.
delattr(Layout, 'grouped')
prefs=bpy.context.preferences.addons[ROOT.name].preferences
w=bpy.context.window_manager.windows[0]
a=next(a for a in w.screen.areas if a.type=='VIEW_3D')
r=next(r for r in a.regions if r.type=='WINDOW')
with bpy.context.temp_override(window=w,area=a,region=r):
    prefs.show_panel_session_status=True
    for mode in ('CLASSIC','CUSTOM'):
        prefs.ui_mode=mode
        prefs.custom_ui_show_session=True
        for save_open in (False,True):
            for auto_open in (False,True):
                prefs.show_panel_save_restart=save_open
                prefs.show_panel_autosave=auto_open
                model=Layout(key='native-folds')
                ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=model),bpy.context)
                assert not model.errors,model.errors
                ops={b[1] for b in model.bindings.values() if b[0]=='operator'}
                assert ('wm.airetopo_relocate_project' in ops)==save_open,(mode,save_open,auto_open,ops)
                assert ('wm.airetopo_open_recent_autosave' in ops)==auto_open
                assert prefs.show_panel_session_status
                if mode=='CLASSIC':
                    assert 'object.airetopo_set_all_section_visibility' in ops
                    groups={n['id'] for n in walk(model.node) if n['kind']=='group'}
                    for _,prop in ui.SECTION_PANEL_VISIBILITY:
                        assert any(g.endswith('.'+prop) for g in groups),prop
print('SESSION_GROUP_VISIBILITY_TESTS_PASSED')
