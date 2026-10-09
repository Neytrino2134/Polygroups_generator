"""Sidebar/detach integration and icon navigation in a real Blender GUI."""
from pathlib import Path
from types import SimpleNamespace
import bpy,addon_utils,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator import ui
from polygroups_generator.custom_ui import lifecycle
from polygroups_generator.custom_ui.schema import Layout,walk
prefs=bpy.context.preferences.addons[ROOT.name].preferences
prefs.ui_mode='CUSTOM'
LOG=ROOT/'docs/custom_ui/docking_test.log'
LOG.write_text('Starting\n')
state={'step':0}
def tick():
    try:
        w=bpy.context.window_manager.windows[0]
        a=next(a for a in w.screen.areas if a.type=='VIEW_3D')
        r=next(r for r in a.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=w,area=a,region=r):
            step=state['step']
            if step==0:
                assert prefs.custom_ui_presentation=='DOCKED'
                a.spaces.active.show_region_ui=True
                for index in range(13):
                    bpy.ops.wm.airetopo_custom_section(section=index)
                    model=Layout(key='dock')
                    ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=model),bpy.context)
                    assert not model.errors,model.errors
                    rail=[b for b in model.bindings.values() if b[0]=='operator' and b[1]=='wm.airetopo_custom_section']
                    assert len(rail)==13
                bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')
                state['step']=1
                return 1
            s=lifecycle.SESSIONS[lifecycle.key_for(bpy.context)]
            if step==1:
                assert s.section==12
                s.width=400
                a.tag_redraw()
                state['step']=2
                return .6
            if step==2:
                assert len([h for h in s.hits if h[1][0]=='section'])==13
                assert all(h[2] for h in s.hits if h[1][0]=='section')
                state['session']=s
                bpy.ops.wm.airetopo_custom_placement(placement='DOCKED')
                bpy.ops.wm.airetopo_custom_section(section=9)
                state['step']=3
                return .6
            if step==3:
                assert s is state['session'] and s.section==9
                bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')
                state['step']=4
                return .6
            assert s is state['session'] and s.section==9
            LOG.write_text(LOG.read_text()+'13 sidebar sections, detach/dock state preservation and 13 compact icon targets passed\nCUSTOM_UI_DOCKING_TESTS_PASSED\n')
            addon_utils.disable(ROOT.name)
            bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc())
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(tick,first_interval=1)
