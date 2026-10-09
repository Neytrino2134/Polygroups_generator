"""Actual Blender event simulation; use --enable-event-simulate, without -b."""
from pathlib import Path
import sys
import os
import traceback
import time
import bpy
import addon_utils
import bmesh
bpy.context.preferences.use_preferences_save = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
OUT=Path(os.environ.get('AIRETOPO_UI_VALIDATION_OUTPUT',ROOT/'docs/custom_ui'))
OUT.mkdir(parents=True,exist_ok=True)
LOG = OUT / 'input_test.log'
LOG.write_text('Starting\n')
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.custom_ui import lifecycle
prefs=bpy.context.preferences.addons[ROOT.name].preferences
prefs.ui_mode='CUSTOM'
window=bpy.context.window_manager.windows[0]
area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')


def press(kind,unicode='',**kwargs):
    window.event_simulate(type=kind,value='PRESS',unicode=unicode,x=region.x+120,y=region.y+120,**kwargs)
    window.event_simulate(type=kind,value='RELEASE',x=region.x+120,y=region.y+120,**kwargs)


def click(hit):
    x,y,w,h=hit[0]
    x,y=int(region.x+x+w/2),int(region.y+y+h/2)
    window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
    window.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
    window.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x,y=y)


def binding_hit(session,predicate):
    for hit in session.hits:
        if hit[1][0]=='binding':
            binding=session.model.bindings.get(hit[1][1])
            if binding and predicate(binding):
                return hit
    raise AssertionError('Visible binding not found')


def run():
    yield 1
    s=lifecycle.SESSIONS[lifecycle.key_for(bpy.context)]
    s.select(3)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm=bmesh.from_edit_mesh(bpy.context.object.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].select=True
    bmesh.update_edit_mesh(bpy.context.object.data)
    settings=bpy.context.scene.airetopo_panel_visibility_settings
    settings.topic_seam_prep_0=True
    s.refresh(bpy.context)
    area.tag_redraw()
    yield .5
    # Real existing operator, launched through the overlay with its VIEW_3D context.
    before=sum(v.select for v in bm.verts)
    hit=binding_hit(s,lambda b:b[0]=='operator' and b[1]=='mesh.select_more')
    click(hit)
    yield .5
    assert sum(v.select for v in bm.verts)>before, s.note
    LOG.write_text(LOG.read_text()+'Real mesh operator dispatch passed\n')
    # Real checkbox writes the same RNA used by the classic panel.
    hit=binding_hit(s,lambda b:b[0]=='property' and b[2]=='prefer_linked_seam')
    binding=s.model.bindings[hit[1][1]]
    before=getattr(binding[1],binding[2])
    click(hit)
    yield .4
    assert getattr(binding[1],binding[2]) != before
    # Numeric text field commits; Escape does not write a value.
    hit=binding_hit(s,lambda b:b[0]=='property' and b[2]=='selection_smooth_iterations')
    binding=s.model.bindings[hit[1][1]]
    click(hit)
    yield .3
    assert s.edit
    press('FOUR','4')
    press('RET')
    yield .3
    assert getattr(binding[1],binding[2])==4, s.note
    click(hit)
    yield .3
    press('NINE','9')
    press('ESC')
    yield .3
    assert getattr(binding[1],binding[2])==4
    LOG.write_text(LOG.read_text()+'Checkbox and text commit/cancel passed\n')
    # Slider stages a value and rolls it back without touching RNA on Escape.
    slider=next(hit for hit in s.hits if hit[1][0]=='slider' and hit[1][1]==binding_hit(s,lambda b:b[0]=='property' and b[2]=='selection_smooth_iterations')[1][1])
    rx,ry,rw,rh=slider[0]
    window.event_simulate(type='LEFTMOUSE',value='PRESS',x=int(region.x+rx+rw*.3),y=int(region.y+ry+rh/2))
    yield .2
    assert s.slider
    press('ESC')
    yield .2
    assert s.slider is None and getattr(binding[1],binding[2])==4
    # Group fold does not hide sibling groups or corrupt captured bindings.
    group=next(hit for hit in s.hits if hit[1][0]=='binding' and hit[1][1].endswith('.topic_seam_prep_0'))
    click(group)
    yield .3
    assert not settings.topic_seam_prep_0
    click(group)
    yield .3
    assert settings.topic_seam_prep_0
    LOG.write_text(LOG.read_text()+'Slider rollback and group fold passed\n')
    # Enum selection uses a custom dropdown and real RNA identifiers.
    s.select(9)
    s.query='Bake Settings'
    s.refresh(bpy.context)
    area.tag_redraw()
    yield .5
    hit=binding_hit(s,lambda b:b[0]=='property' and b[2]=='bake_background_mode')
    binding=s.model.bindings[hit[1][1]]
    before=getattr(binding[1],binding[2])
    click(hit)
    yield .3
    assert s.dropdown
    choice=next(hit for hit in s.hits if hit[1][0]=='choice' and hit[1][1]!=before)
    expected=choice[1][1]
    click(choice)
    yield .3
    assert getattr(binding[1],binding[2])==expected
    s.query=''
    LOG.write_text(LOG.read_text()+'Custom enum dropdown passed\n')
    # Native Save As handoff opens Blender's file browser and can be cancelled
    # without saving anything or losing the originating custom session.
    s.query='Save Project'
    s.refresh(bpy.context)
    area.tag_redraw()
    yield .5
    hit=binding_hit(s,lambda b:b[0]=='operator' and b[1]=='object.polygroups_save_blend_file_as')
    click(hit)
    yield .8
    browsers=[w for w in bpy.context.window_manager.windows if any(a.type=='FILE_BROWSER' for a in w.screen.areas)]
    assert browsers, 'Save As did not open the native Blender file browser: '+s.note
    browser=browsers[0]
    browser.event_simulate(type='ESC',value='PRESS',x=100,y=100)
    browser.event_simulate(type='ESC',value='RELEASE',x=100,y=100)
    yield .8
    assert s.key in lifecycle.SESSIONS and not s.closed
    assert not bpy.data.filepath
    s.query=''
    LOG.write_text(LOG.read_text()+'Native file browser handoff/cancel passed\n')
    # Repeated mode changes leave one modal session and no duplicate handlers.
    for _ in range(3):
        prefs.ui_mode='CLASSIC'
        yield .6
        assert not lifecycle.SESSIONS
        prefs.ui_mode='CUSTOM'
        yield .6
        assert len(lifecycle.SESSIONS)==1
    bpy.ops.object.mode_set(mode='OBJECT')
    LOG.write_text(LOG.read_text()+'Mode switching passed\nCUSTOM_UI_INPUT_TESTS_PASSED\n')


iterator=run()
def tick():
    try:
        if area in window.screen.areas[:]:
            with bpy.context.temp_override(window=window,area=area,region=region):
                return next(iterator)
        return next(iterator)
    except StopIteration:
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc())
        addon_utils.disable(ROOT.name)
        bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(tick,first_interval=.5)
