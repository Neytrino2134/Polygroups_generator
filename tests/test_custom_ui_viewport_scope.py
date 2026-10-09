"""UI Panel opens/places only in the editor that invoked it."""
from pathlib import Path
import bpy,addon_utils,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
sys.path.insert(0,str(ROOT/'tests'))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.custom_ui import lifecycle as ui
from custom_ui_test_support import open_panel
prefs=bpy.context.preferences.addons[ROOT.name].preferences
prefs.ui_mode='UI_PANEL'
open_panel()
LOG=ROOT/'docs/custom_ui/viewport_scope_test.log'
LOG.write_text('Starting\n')
state={'step':0}
def tick():
    try:
        step=state['step']
        if step==0:
            assert len(ui.SESSIONS)==1
            s=next(iter(ui.SESSIONS.values()))
            state['first']=s
            assert s.docked and ui.resolve(s)
            with bpy.context.temp_override(window=s.window,area=s.area,region=s.region):
                bpy.ops.screen.area_split(direction='VERTICAL',factor=.5)
            state['step']=1
            return .7
        first=state['first']
        assert ui.resolve(first)
        w=first.window
        other=next(a for a in w.screen.areas if a.type=='VIEW_3D' and a.as_pointer()!=first.area.as_pointer())
        r=next(r for r in other.regions if r.type=='WINDOW')
        if step==1:
            assert len(ui.SESSIONS)==1,'Split unexpectedly opened a second panel'
            with bpy.context.temp_override(window=w,area=first.area,region=first.region):
                bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')
                prefs.custom_ui_brightness=1.1
            assert not first.docked
            state['step']=2
            return .7
        if step==2:
            assert len(ui.SESSIONS)==1,'Placement or preference update opened another panel'
            with bpy.context.temp_override(window=w,area=other,region=r):
                bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
                second=ui.SESSIONS[ui.key_for(bpy.context)]
                assert second.docked,'Open must start docked'
                bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')
            assert len(ui.SESSIONS)==2 and not first.docked and not second.docked
            state['second']=second
            with bpy.context.temp_override(window=w,area=first.area,region=first.region):
                bpy.ops.wm.airetopo_custom_placement(placement='DOCKED')
                x,top,width,height=first.geometry(first.region)
                assert abs(first.region.width-x-width-22)<.01
            assert first.docked and not second.docked,'Dock affected another editor'
            state['step']=3
            return .7
        second=state['second']
        if step==3:
            with bpy.context.temp_override(window=w,area=first.area,region=first.region):
                bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')
                bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
            assert first.docked and not second.docked,'Open did not dock only its own session'
            second.closed=True
            ui.SESSIONS.pop(second.key)
            ui.request_update()
            state['step']=4
            return .7
        assert len(ui.SESSIONS)==1,'Closed panel was automatically reopened'
        LOG.write_text(LOG.read_text()+'Origin-only open, independent Dock/Detach, right margin 22 px and no automatic reopening passed\nCUSTOM_UI_VIEWPORT_SCOPE_TESTS_PASSED\n')
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc())
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(tick,first_interval=1)
