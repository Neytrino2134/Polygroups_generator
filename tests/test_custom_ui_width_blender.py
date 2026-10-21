"""Docked geometry follows live sidebar pixels; floating keeps its own size."""
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.custom_ui.lifecycle import Session
from polygroups_generator.custom_ui.schema import Layout
from polygroups_generator import ui

prefs = bpy.context.preferences.addons[ROOT.name].preferences
prefs.ui_mode = 'CUSTOM'
layout = Layout(key='custom')
ui.VIEW3D_PT_polygroups_generator.draw(NS(layout=layout), bpy.context)
assert not layout.errors, layout.errors
assert not any(b[0] == 'operator' and b[1] == 'wm.airetopo_custom_ui' for b in layout.bindings.values())
sidebar = NS(type='UI', width=430, x=570)
space = NS(show_region_ui=True)
session = NS(scale=1, prefs=NS(ui_mode='UI_PANEL', ui_panel_width=400), docked=True,
             area=NS(regions=[sidebar], spaces=NS(active=space)), collapsed=False,
             width=500, height=500, x=20, y=40)
region = NS(width=1000, height=800, x=0)
session.geometry = lambda region: Session.geometry(session, region)
for scale in (1, 1.5, 2):
    session.scale = scale
    for width in (320, 430, 600):
        sidebar.width = width
        sidebar.x = 1000-width
        x, top, actual, h = Session.geometry(session, region)
        assert actual == width-36 and x == sidebar.x+8
        assert x+actual == 972
        assert top == region.height-160
        assert Session.sidebar_resize_rect(session, region) is None
        embedded = NS(type='UI', width=width, height=800)
        assert Session.geometry(session, embedded) == (8, 640, width-36, 632)
session.docked = False
assert Session.sidebar_resize_rect(session, region) is None
before = Session.geometry(session, region)
sidebar.width = 200
assert Session.geometry(session, region) == before
session.docked = True
space.show_region_ui = False
assert Session.geometry(session, region)[2] == session.prefs.ui_panel_width*session.scale
print('CUSTOM_UI_WIDTH_PASSED')
