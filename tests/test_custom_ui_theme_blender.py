"""Display color conversion, configurable surfaces, and appearance reset."""
from pathlib import Path
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.custom_ui import theme
from polygroups_generator.custom_ui.renderer import tooltip_text_width
from polygroups_generator.custom_ui.schema import Layout

p = bpy.context.preferences.addons[ROOT.name].preferences
p.ui_mode = 'UI_PANEL'
p.custom_ui_accent = (.5, .0031308, 1)
color = theme.accent(p)
assert abs(color[0] - .73535698) < 1e-6
assert abs(color[1] - .04044994) < 1e-6
assert abs(color[2] - 1) < 1e-6
p.custom_ui_bg = (.1, .2, .3)
p.custom_ui_secondary_bg = (.3, .4, .5)
p.custom_ui_accent_bg = (.6, .7, .8)
p.custom_ui_heading_color = (.8, .2, .3)
p.custom_ui_text_color = (.4, .6, .9)
assert all(abs(a-b) < 1e-6 for a,b in zip(theme.heading(p)[:3], p.custom_ui_heading_color))
assert all(abs(a-b) < 1e-6 for a,b in zip(theme.text_color(p)[:3], p.custom_ui_text_color))
for scale in (1, 1.5, 2):
    short = tooltip_text_width(['Save'], scale, 420*scale)
    long = tooltip_text_width(['Save all selected objects to a blend file'], scale, 420*scale)
    assert 20*scale < short < long <= 420*scale
    assert tooltip_text_width(['Save', 'Save all selected objects to a blend file'], scale, 420*scale) == long
for source, prop in ((theme.BACKGROUND, 'custom_ui_bg'), (theme.SURFACE, 'custom_ui_secondary_bg'),
                     (theme.RAISED, 'custom_ui_secondary_bg'), (theme.BORDER, 'custom_ui_accent_bg')):
    assert all(abs(a-b) < 1e-6 for a,b in zip(theme.surface(source,p)[:3], getattr(p,prop)))
layout = Layout(key='appearance')
p.draw_interface(layout)
assert not layout.errors, layout.errors
for prop in ('custom_ui_bg', 'custom_ui_secondary_bg', 'custom_ui_accent_bg', 'custom_ui_heading_color', 'custom_ui_text_color'):
    assert any(b[0] == 'property' and b[2] == prop for b in layout.bindings.values())
assert bpy.ops.wm.airetopo_reset_custom_appearance() == {'FINISHED'}
for prop in ('custom_ui_accent', 'custom_ui_bg', 'custom_ui_secondary_bg', 'custom_ui_accent_bg', 'custom_ui_heading_color', 'custom_ui_text_color'):
    assert not p.is_property_set(prop)
print('CUSTOM_UI_THEME_PASSED')
