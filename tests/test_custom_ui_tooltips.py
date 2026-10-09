"""Hover real controls and verify the bounds actually used by the GPU renderer."""
from pathlib import Path
import bpy,addon_utils,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.custom_ui import lifecycle,renderer
prefs=bpy.context.preferences.addons[ROOT.name].preferences
prefs.ui_mode='UI_PANEL'
LOG=ROOT/'docs/custom_ui/tooltip_test.log'
LOG.write_text('Starting\n')
original=renderer.tooltip_bounds
state={'step':0,'bounds':None}
def record(*args,**kwargs):
    value=original(*args,**kwargs)
    state['bounds']=value
    return value
renderer.tooltip_bounds=record
def tick():
    try:
        w=bpy.context.window_manager.windows[0]
        a=next(a for a in w.screen.areas if a.type=='VIEW_3D')
        r=next(r for r in a.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=w,area=a,region=r):
            s=lifecycle.SESSIONS[lifecycle.key_for(bpy.context)]
            step=state['step']
            if step in (0,2):
                hit=next(h for h in s.hits if h[1][0]=='section' and h[1][1]==9)
                rect=hit[0]
                mx,my=rect[0]+rect[2]/2,rect[1]+rect[3]/2
                state['anchor']=rect
                state['mouse']=(mx,my)
                state['bounds']=None
                w.event_simulate(type='MOUSEMOVE',value='NOTHING',x=int(r.x+mx),y=int(r.y+my))
                state['step']+=1
                return 1.1
            bounds=state['bounds']
            assert bounds,'Renderer did not display tooltip'
            x,y,width,height=bounds
            ax,ay,aw,ah=state['anchor']
            mx,my=state['mouse']
            assert y>ay+ah,'Tooltip is not above the hovered button'
            assert not (x<=mx<=x+width and y<=my<=y+height)
            assert x>=0 and y>=0 and x+width<=r.width and y+height<=r.height
            if step==1:
                prefs.ui_panel_docked=False
                s.width=400
                state['step']=2
                return .6
            LOG.write_text(LOG.read_text()+'Real docked and floating hover bounds passed\nCUSTOM_UI_TOOLTIP_TESTS_PASSED\n')
            renderer.tooltip_bounds=original
            addon_utils.disable(ROOT.name)
            bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc())
        renderer.tooltip_bounds=original
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(tick,first_interval=1)
