"""Disposable Blender UI test; --factory-startup --enable-event-simulate."""
import sys
import tempfile
import traceback
from pathlib import Path

import addon_utils
import bmesh
import bpy
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

bpy.context.preferences.view.show_splash = False
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / "airetopo_remesh_cursor_ui.log"
LOG.write_text("Starting\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.core.remesh_cursor import RemeshCursor, update_remesh_cursor
    from types import SimpleNamespace
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    draws = []
    errors = []
    original = RemeshCursor.draw
    def checked(self):
        try:
            original(self)
            draws.append(self.percent)
        except Exception as error:
            errors.append(str(error))
    RemeshCursor.draw = checked
    with context.temp_override(window=window, area=area, region=region):
        cursor = RemeshCursor(context)
        update_remesh_cursor(context, SimpleNamespace(mouse_x=region.x+region.width//2, mouse_y=region.y+region.height//2))
        cursor.percent = 42
        cursor.secondary_percent = 67
        cursor.status_line = "Processing"
    yield 0.5
    assert draws and not errors, errors
    with context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=str(LOG.with_suffix(".png")))
    cursor.close()
    count = len(draws)
    yield 0.3
    assert cursor.handle is None and len(draws) == count
    RemeshCursor.draw = original
    addon_utils.disable(ROOT.name, default_set=True)
    LOG.write_text("REMESH_CURSOR_UI_TESTS_PASSED\n")


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
