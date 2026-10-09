"""Real Blender maximize/restore regression; no user preferences saved."""
from pathlib import Path
import bpy, addon_utils, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.custom_ui import lifecycle as ui
bpy.context.preferences.addons[ROOT.name].preferences.ui_mode='CUSTOM'
LOG=ROOT/'docs/custom_ui/maximize_test.log'
state={'step':0}
def tick():
    try:
        w=bpy.context.window_manager.windows[0]
        a=next(a for a in w.screen.areas if a.type=='VIEW_3D')
        r=next(r for r in a.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=w,area=a,region=r):
            s=ui.SESSIONS.get(ui.key_for(bpy.context))
            assert s and not s.closed, 'Panel disappeared'
            assert ui.resolve(s)
            if state['step']==0:
                state['session']=s
                s.select(9)
                s.query=''
                LOG.write_text('Starting maximize/restore regression\n')
            assert s is state['session'], 'Session state was replaced'
            assert s.section==9
            assert (len(w.screen.areas)==1)==bool(min(state['step'],12)%2), 'Ctrl+Space did not change layout'
            assert s.hits, 'Panel has no rendered interactive controls'
            if state['step'] in (12,13):
                assert s.collapsed == (state['step']==13), 'Input handler stopped after restore'
                rect=next(hit[0] for hit in s.hits if hit[1][0]=='collapse')
                x,y=int(r.x+rect[0]+rect[2]/2),int(r.y+rect[1]+rect[3]/2)
                w.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
                w.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
                w.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x,y=y)
                state['step']+=1
                return .8
            if state['step']>=14:
                assert not s.collapsed, 'Restored panel failed to reopen'
                LOG.write_text(LOG.read_text()+'12 maximize/restore transitions passed; same session, section and controls\nCUSTOM_UI_MAXIMIZE_TESTS_PASSED\n')
                addon_utils.disable(ROOT.name)
                bpy.ops.wm.quit_blender()
                return None
            bpy.ops.screen.screen_full_area(use_hide_panels=False)
            state['step']+=1
        return .8
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc() if LOG.exists() else traceback.format_exc())
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
        return None
bpy.app.timers.register(tick,first_interval=2)
