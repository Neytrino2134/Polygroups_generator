"""Blender runtime capture/dispatch coverage; no paid API or destructive output."""
import contextlib
import io
import json
from pathlib import Path
import sys
import os
import addon_utils
import bpy
bpy.context.preferences.use_preferences_save = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator import ui
from polygroups_generator.custom_ui.schema import capture, walk
from polygroups_generator.custom_ui import lifecycle, renderer
from polygroups_generator.custom_ui.events import edit_key, parsed_value
from types import SimpleNamespace
sys.path.insert(0,str(ROOT/'scripts'))
from build_custom_ui_inventory import collect

prefs = bpy.context.preferences.addons[ROOT.name].preferences
assert prefs.ui_mode == 'CLASSIC'
records = []
errors = io.StringIO()
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(window=window, area=area, region=region), contextlib.redirect_stdout(errors):
    for mode in ('OBJECT', 'EDIT', 'SCULPT'):
        bpy.ops.object.mode_set(mode=mode)
        for index in range(13):
            model = capture(bpy.context, index)
            assert not model.errors, model.errors
            nodes = list(walk(model.node))
            assert len(nodes) > 3, ui.SECTION_PANEL_CLASSES[index].__name__
            identifiers=[n['id'] for n in nodes if n['kind'] in {'property','button','group','list'}]
            assert len(identifiers)==len(set(identifiers)), 'Duplicate semantic control identifiers'
            for node in nodes:
                if node['kind'] in {'property', 'button', 'group'}:
                    assert node['id'] in model.bindings
            records.append(dict(mode=mode, section=index+1, nodes=[{k:v for k,v in n.items() if k!='children'} for n in nodes],
                                bindings={key: {'kind': b[0], 'operator': b[1] if b[0]=='operator' else '',
                                'parameters': vars(b[2]) if b[0]=='operator' else {},
                                'execution_context': b[3] if b[0]=='operator' else ''}
                                for key,b in model.bindings.items()}))
    bpy.ops.object.mode_set(mode='OBJECT')
    session = lifecycle.Session(bpy.context)
    session.select(9)
    session.refresh(bpy.context)
    before = session.model.node
    session.refresh(bpy.context)
    assert before == session.model.node, 'Stable capture must not drift'
    session.select(0, True)
    session.refresh(bpy.context)
    assert session.model.bindings, 'Global header actions must be available'
    assert not session.model.errors
    for node in walk(session.model.node):
        if node.get('secret'):
            assert node['value'] in ('', '••••••')
    assert any(node['kind']=='property' and node.get('property')=='custom_ui_accent' for node in walk(session.model.node))
    session.show_header = False
    session.query = 'cage'
    session.refresh(bpy.context)
    assert len(session.model.node['children']) == 13
    assert any(renderer.visible(child,'cage') for child in session.model.node['children'])
    session.query = ''
    original = prefs.custom_ui_section
    prefs.interface_language = 'RU'
    session.refresh(bpy.context)
    assert 'Бейкинг' in session.titles[9], session.titles
    prefs.interface_language = 'EN'
    edit = dict(text='12',cursor=2,all=True)
    clipboard = SimpleNamespace(clipboard='24')
    def event(kind, unicode='',ctrl=False):
        return SimpleNamespace(type=kind,unicode=unicode,ctrl=ctrl,alt=False,value='PRESS')
    edit_key(edit,event('V',ctrl=True),clipboard)
    assert edit['text']=='24'
    assert edit_key(edit,event('ESC'),clipboard)=='cancel'
    assert parsed_value(edit,dict(type='INT',min=0,max=20))==20
    bpy.ops.object.select_all(action='DESELECT')
    for index in range(13):
        assert not capture(bpy.context,index).errors
    bpy.context.view_layer.objects.active = bpy.data.objects['Cube']
    bpy.data.objects['Cube'].select_set(True)
    for scale in (1, 1.5, 2):
        prefs.custom_ui_scale = scale
        x, top, width, h = session.geometry(region)
        assert width <= region.width and h <= region.height
        for small in (SimpleNamespace(width=400,height=250),SimpleNamespace(width=128,height=96)):
            x,top,width,h=session.geometry(small)
            assert x>=0 and top<=small.height and x+width<=small.width and top-h>=0
    bpy.ops.wm.airetopo_reset_custom_appearance()
    assert prefs.custom_ui_scale == 1
assert 'failed to draw' not in errors.getvalue(), errors.getvalue()
for scale in (1, 1.5, 2):
    viewport = (1000*scale, 700*scale)
    for anchor in ((200,200,160,40), (820,200,160,40), (200,630,160,40)):
        anchor = tuple(value*scale for value in anchor)
        mouse = (anchor[0]+anchor[2]/2, anchor[1]+anchor[3]/2)
        bounds = renderer.tooltip_bounds(anchor, (320*scale, 60*scale), viewport, mouse, scale)
        assert bounds
        x,y,w,h = bounds
        assert 0 <= x and x+w <= viewport[0] and 0 <= y and y+h <= viewport[1]
        assert not (x <= mouse[0] <= x+w and y <= mouse[1] <= y+h)
        if anchor[1]+anchor[3]+72*scale <= viewport[1]-8*scale:
            assert y > anchor[1]+anchor[3], 'Tooltip should be above the hovered control'
out = Path(os.environ.get('AIRETOPO_UI_VALIDATION_OUTPUT',ROOT / 'docs' / 'custom_ui'))
out.mkdir(parents=True, exist_ok=True)
(out / 'control_inventory.json').write_text(json.dumps(dict(baseline='b67e6c8',runtime=records,static_calls=collect(ROOT)), indent=2, ensure_ascii=False, default=lambda value: sorted(value) if isinstance(value,set) else str(value)), encoding='utf8')
addon_utils.disable(ROOT.name)
assert not lifecycle.SESSIONS
addon_utils.enable(ROOT.name, default_set=True)
addon_utils.disable(ROOT.name)
print('CUSTOM_UI_BLENDER_TESTS_PASSED')

