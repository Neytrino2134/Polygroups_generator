"""Run in a separate factory-startup Blender UI process."""
import contextlib
import io
import sys
import tempfile
import traceback
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / 'airetopo_group_windows_test.log'
LOG.write_text('Starting\n')
bpy.context.preferences.view.show_splash = False

def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator import ui
    from polygroups_generator.operators.detached_groups import WINDOW_GROUPS
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    groups = []
    original = ui.draw_collapsible_box
    def capture(layout, settings, prop, label, icon):
        if ui._DRAWING_SECTION:
            groups.append((ui._DRAWING_SECTION.__name__, settings.path_from_id()+'.'+prop, label))
            assert not settings.bl_rna.properties[prop].default, prop
        return ui._NullLayout()
    ui.draw_collapsible_box = capture
    output = io.StringIO()
    try:
        with bpy.context.temp_override(window=window, area=area, region=region), contextlib.redirect_stdout(output):
            for cls in ui.SECTION_PANEL_CLASSES:
                ui.draw_section_panel_content(cls, bpy.context, ui._NullLayout(), '')
    finally:
        ui.draw_collapsible_box = original
    assert 'failed to draw' not in output.getvalue(), output.getvalue()
    assert len(set(item[0] for item in groups)) == 13, groups
    with bpy.context.temp_override(window=window, area=area, region=region), contextlib.redirect_stdout(output):
        for section, group, title in groups:
            ui.draw_detached_group(bpy.context, ui._NullLayout(), section, group)
        section, group, title = groups[0]
        assert bpy.ops.wm.airetopo_detach_group(section=section, group=group, title=title) == {'FINISHED'}
    assert 'failed to draw' not in output.getvalue(), output.getvalue()
    yield 2
    assert len(WINDOW_GROUPS) == 1
    pointer, state = next(iter(WINDOW_GROUPS.items()))
    assert state['pinned'] and state['handle'], state
    new = next(w for w in bpy.context.window_manager.windows if w.as_pointer() == pointer)
    target = next(a for a in new.screen.areas if a.type == 'VIEW_3D')
    with bpy.context.temp_override(window=new, area=target):
        assert bpy.ops.wm.airetopo_group_window_control(action='COLLAPSE') == {'FINISHED'}
        assert state['collapsed']
        bpy.ops.wm.airetopo_group_window_control(action='COLLAPSE')
        assert not state['collapsed']
        bpy.ops.wm.airetopo_group_window_control(action='PIN')
        assert not state['pinned']
        bpy.ops.wm.airetopo_group_window_control(action='CLOSE')
    yield .5
    assert not WINDOW_GROUPS
    assert len(bpy.context.window_manager.windows) == 1
    LOG.write_text(f'PASSED: {len(groups)} groups; detach, pin, collapse, close\n')

steps = run()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
bpy.app.timers.register(tick, first_interval=1)
