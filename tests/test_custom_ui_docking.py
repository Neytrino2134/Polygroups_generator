"""Sidebar/detach integration and icon navigation in a real Blender GUI."""
from pathlib import Path
from types import SimpleNamespace
import bpy,addon_utils,sys,traceback,gpu
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
def snapshot():
    if not state.get('capture') or bpy.context.region.type!='WINDOW':
        return
    s=lifecycle.SESSIONS.get(lifecycle.key_for(bpy.context))
    if not s:
        return
    x,top,width,height=s.geometry(bpy.context.region)
    x,y,width,height=int(x),int(top-height),int(width),int(height)
    pixels=gpu.state.active_framebuffer_get().read_color(x,y,width,height,4,0,'FLOAT')
    pixels.dimensions=width*height*4
    image=bpy.data.images.new('Docked UI Panel',width=width,height=height,alpha=True)
    image.pixels.foreach_set(pixels)
    image.filepath_raw=str(ROOT/'docs/custom_ui/ui_panel_docked.png')
    image.file_format='PNG'
    image.save()
    bpy.data.images.remove(image)
    state['capture']=False
handle=bpy.types.SpaceView3D.draw_handler_add(snapshot,(),'WINDOW','POST_PIXEL')
def tick():
    try:
        w=bpy.context.window_manager.windows[0]
        a=next(a for a in w.screen.areas if a.type=='VIEW_3D')
        r=next(r for r in a.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=w,area=a,region=r):
            step=state['step']
            if step==0:
                assert prefs.ui_mode=='CUSTOM'
                assert {item.identifier for item in prefs.bl_rna.properties['ui_mode'].enum_items} == {'CLASSIC','CUSTOM','UI_PANEL'}
                a.spaces.active.show_region_ui=True
                for index in range(13):
                    bpy.ops.wm.airetopo_custom_section(section=index)
                    model=Layout(key='dock')
                    ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=model),bpy.context)
                    assert not model.errors,model.errors
                    rail=[b for b in model.bindings.values() if b[0]=='operator' and b[1]=='wm.airetopo_custom_section']
                    assert len(rail)==13
                bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
                bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')
                state['step']=1
                return 1
            s=lifecycle.SESSIONS[lifecycle.key_for(bpy.context)]
            if step==1:
                assert prefs.ui_mode=='UI_PANEL' and not s.docked
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
                state['capture']=True
                state['step']=3
                return .6
            if step==3:
                assert s is state['session'] and s.section==9
                assert prefs.ui_mode=='UI_PANEL' and s.docked
                x,top,width,height=s.geometry(r)
                assert abs(x+width-(r.width-22))<.01
                assert top==r.height-200 and height==r.height-208
                assert not any(h[1][0] in {'move','resize'} for h in s.hits)
                for rw,rh in ((400,300),(1400,900)):
                    x,top,width,height=s.geometry(SimpleNamespace(width=rw,height=rh))
                    assert abs(x+width-(rw-22))<.01 and top==rh-200
                bpy.ops.screen.screen_full_area(use_hide_panels=False)
                state['step']=4
                return .6
            if step==4:
                assert s.docked and s is state['session']
                x,top,width,height=s.geometry(r)
                assert abs(x+width-(r.width-22))<.01 and top==r.height-200
                bpy.ops.screen.screen_full_area(use_hide_panels=False)
                state['step']=5
                return .6
            if step==5:
                rect=next(h[0] for h in s.hits if h[1][0]=='dock')
                x,y=int(r.x+rect[0]+rect[2]/2),int(r.y+rect[1]+rect[3]/2)
                w.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
                w.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
                w.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x,y=y)
                state['step']=6
                return .6
            assert s is state['session'] and s.section==9
            if step==6:
                assert prefs.ui_mode=='UI_PANEL' and not s.docked
                assert any(h[1][0]=='resize' for h in s.hits)
                state['position']=(s.x,s.y)
                rect=next(h[0] for h in s.hits if h[1][0]=='move')
                x,y=int(r.x+rect[0]+30),int(r.y+rect[1]+20)
                w.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
                w.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
                w.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x+40,y=y-30)
                w.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x+40,y=y-30)
                state['step']=7
                return .6
            if step==7:
                assert (s.x,s.y)!=state['position'], 'Detached panel did not move'
                rect=next(h[0] for h in s.hits if h[1][0]=='dock')
                x,y=int(r.x+rect[0]+rect[2]/2),int(r.y+rect[1]+rect[3]/2)
                w.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
                w.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
                w.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x,y=y)
                state['step']=8
                return .6
            assert s.docked and prefs.ui_mode=='UI_PANEL'
            assert not any(h[1][0]=='move' for h in s.hits)
            assert not state['capture']
            LOG.write_text(LOG.read_text()+'13 sidebar sections, detach/dock state preservation and 13 compact icon targets passed\nCUSTOM_UI_DOCKING_TESTS_PASSED\n')
            addon_utils.disable(ROOT.name)
            bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
            bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc())
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(tick,first_interval=1)
