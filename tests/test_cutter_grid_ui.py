"""Disposable Blender UI test; launch with --enable-event-simulate."""
import sys
import tempfile
import traceback
from pathlib import Path
import bpy
import addon_utils
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
AUTO_ROTATE = "--auto-rotate" in sys.argv
LOG = Path(tempfile.gettempdir()) / ("airetopo_cutter_grid_rotate_ui.log" if AUTO_ROTATE else "airetopo_cutter_grid_ui.log")
LOG.write_text("Starting\n")
bpy.context.preferences.view.show_splash = False


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.operators import cutter_grid as grid
    draws, errors = [], []
    original = grid.draw_grid_preview
    def draw(operator):
        try:
            original(operator)
            draws.append(True)
        except Exception:
            errors.append(traceback.format_exc())
    grid.draw_grid_preview = draw
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        target = context.object
        settings = context.scene.polygroups_object_seam_cutter_settings
        settings.cutter_grid_counts = (2, 1, 1)
        settings.cutter_grid_auto_rotate = AUTO_ROTATE
        bpy.ops.view3d.view_axis(type="FRONT" if AUTO_ROTATE else "TOP")
        bpy.ops.wm.tool_set_by_id(name=grid.TOOL_ID)
        bpy.ops.ed.undo_push(message="Grid baseline")
    yield .5
    def screen(point):
        p = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(point))
        return round(p.x + region.x), round(p.y + region.y)
    def event(key, value, point, ctrl=False):
        window.event_simulate(type=key, value=value, x=point[0], y=point[1], ctrl=ctrl)
    def click(point, ctrl=False):
        event("MOUSEMOVE", "NOTHING", point, ctrl)
        event("LEFTMOUSE", "PRESS", point, ctrl)
        event("LEFTMOUSE", "RELEASE", point, ctrl)
    def cutters():
        return [o for o in bpy.data.objects if o.get(grid.CUTTER_TYPE_PROP) == "GRID_PLANE"]

    a, b = ((screen((-2, -1, -2)), screen((2, -1, 2))) if AUTO_ROTATE
            else (screen((-2, -2, 1)), screen((2, 2, 1))))
    click(a, True)
    yield .2
    event("MOUSEMOVE", "NOTHING", b)
    yield .3
    assert draws and not errors, errors
    assert not cutters(), "Preview created objects before confirmation"
    click(b)
    yield .2
    if AUTO_ROTATE:
        direction = area.spaces.active.region_3d.view_rotation @ Vector((0, 0, 1))
        assert (direction - Vector((1, 0, 0))).length < 1e-5, direction
    depth = screen((0, 2.5, 0)) if AUTO_ROTATE else (b[0], b[1] + 50)
    event("MOUSEMOVE", "NOTHING", depth)
    yield .3
    with context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=str(LOG.with_suffix(".png")))
    click(depth)
    yield .4
    assert len(cutters()) == 4
    if AUTO_ROTATE:
        coords = [o.matrix_world @ v.co for o in cutters() for v in o.data.vertices]
        assert abs(min(p.y for p in coords) + 1) < .03
        assert abs(max(p.y for p in coords) - 2.5) < .03
    assert context.active_object == target and context.mode == "OBJECT"
    assert all(o.select_get() for o in cutters())
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()
    yield .3
    assert not cutters()
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.redo()
    yield .3
    assert len(cutters()) == 4
    before_rotation = area.spaces.active.region_3d.view_rotation.copy()
    click(a, True)
    yield .2
    event("MOUSEMOVE", "NOTHING", b)
    yield .2
    if AUTO_ROTATE:
        click(b)
        yield .2
    event("ESC", "PRESS", b)
    event("ESC", "RELEASE", b)
    yield .2
    assert len(cutters()) == 4
    if AUTO_ROTATE:
        assert area.spaces.active.region_3d.view_rotation.rotation_difference(before_rotation).angle < 1e-5
    count = len(draws)
    event("MOUSEMOVE", "NOTHING", a)
    yield .2
    assert len(draws) == count, "Preview callback survived cancellation"
    assert not errors, errors
    LOG.write_text("CUTTER_GRID_UI_TESTS_PASSED\n")


steps = run()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        with LOG.open("a") as stream:
            stream.write(traceback.format_exc())
        bpy.ops.wm.quit_blender()
bpy.app.timers.register(tick, first_interval=1)
