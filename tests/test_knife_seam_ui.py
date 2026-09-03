"""Disposable Blender UI test, launched with --factory-startup --enable-event-simulate."""

import sys
import tempfile
import traceback
from pathlib import Path

import bpy
import bmesh
import addon_utils

bpy.context.preferences.view.show_splash = False
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / "airetopo_knife_ui_test.log"
SCREENSHOT = Path(tempfile.gettempdir()) / "airetopo_knife_preview.png"
LOG.write_text("Starting\n")


def log(message):
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(message + "\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.operators import knife_seam_tool as knife
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    obj = context.active_object
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.wm.tool_set_by_id(name="polygroups_generator.knife_seam_tool")
    draws = []
    draw_errors = []
    original_draw = knife._draw_knife_preview
    def checked_draw(operator):
        try:
            original_draw(operator)
            draws.append(True)
        except Exception:
            draw_errors.append(traceback.format_exc())
    knife._draw_knife_preview = checked_draw
    yield 0.5
    cx, cy = region.x + region.width // 2, region.y + region.height // 2

    def event(key, value, x, y):
        window.event_simulate(type=key, value=value, x=x, y=y)

    def click(x, y):
        event("LEFTMOUSE", "PRESS", x, y)
        event("LEFTMOUSE", "RELEASE", x, y)

    event("MOUSEMOVE", "NOTHING", cx - 100, cy - 80)
    yield 0.2
    click(cx - 100, cy - 80)
    yield 0.2
    assert len(knife.ACTIVE_KNIFE_OPERATORS) == 1, "Tool click did not invoke Knife Seam"
    operator = knife.ACTIVE_KNIFE_OPERATORS[0]
    assert operator._draw_handle is not None
    event("MOUSEMOVE", "NOTHING", cx + 150, cy + 100)
    yield 0.4
    assert operator._mouse_region_pos == (cx + 150 - region.x, cy + 100 - region.y)
    assert operator._end_region_pos is None
    assert draws and not draw_errors, draw_errors
    with context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=str(SCREENSHOT))
    log(f"Preview screenshot: {SCREENSHOT}")
    click(cx + 150, cy + 100)
    yield 0.2
    assert operator._end_region_pos is not None
    before = len(bmesh.from_edit_mesh(obj.data).edges)
    event("RET", "PRESS", cx + 150, cy + 100)
    event("RET", "RELEASE", cx + 150, cy + 100)
    yield 0.3
    assert not knife.ACTIVE_KNIFE_OPERATORS
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.edges) > before and any(edge.seam for edge in bm.edges)
    log("Preview, confirmation, and seam marking passed")
    before = len(bm.edges)
    click(cx - 80, cy - 40)
    event("MOUSEMOVE", "NOTHING", cx + 80, cy + 60)
    yield 0.2
    assert knife.ACTIVE_KNIFE_OPERATORS
    event("ESC", "PRESS", cx + 80, cy + 60)
    event("ESC", "RELEASE", cx + 80, cy + 60)
    yield 0.3
    assert not knife.ACTIVE_KNIFE_OPERATORS
    assert len(bmesh.from_edit_mesh(obj.data).edges) == before
    log("Cancel cleanup passed")
    click(cx, cy)
    yield 0.2
    assert knife.ACTIVE_KNIFE_OPERATORS
    addon_utils.disable(ROOT.name, default_set=True)
    assert not knife.ACTIVE_KNIFE_OPERATORS
    log("KNIFE_UI_TESTS_PASSED")


steps = run()


def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        log(traceback.format_exc())
        bpy.ops.wm.quit_blender()


bpy.app.timers.register(tick, first_interval=1)
