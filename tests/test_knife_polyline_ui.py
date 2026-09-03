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
LOG = Path(tempfile.gettempdir()) / "airetopo_knife_polyline_ui.log"
LOG.write_text("Starting\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.operators import knife_seam_tool as knife
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_plane_add(size=4)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="EDGE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.view3d.view_axis(type="TOP")
        settings = context.scene.polygroups_knife_seam_settings
        assert settings.cut_mode == "PLANE"
        settings.cut_mode = "POLYLINE"
        assert not settings.stable_view_cut
        settings.mark_seam = True
        settings.use_occlude_geometry = True
        bpy.ops.wm.tool_set_by_id(name="polygroups_generator.knife_seam_tool")
        bpy.ops.ed.undo_push(message="Knife polyline baseline")
    yield 0.5

    def event(key, value, pos):
        window.event_simulate(type=key, value=value, x=pos[0], y=pos[1])

    def position(x, y):
        p = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector((x, y, 0)))
        return round(p.x + region.x), round(p.y + region.y)

    def click(pos):
        event("MOUSEMOVE", "NOTHING", pos)
        event("LEFTMOUSE", "PRESS", pos)
        event("LEFTMOUSE", "RELEASE", pos)

    def bm():
        return bmesh.from_edit_mesh(context.active_object.data)

    points = [position(-2, -2), position(-1, -0.5), position(0.5, -1), position(2, 0)]
    for pos in points:
        click(pos)
        yield 0.3
    assert knife.ACTIVE_KNIFE_OPERATORS
    with context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=str(LOG.with_suffix(".png")))
    # Native RMB starts another line, keeping all previous pending cuts.
    event("RIGHTMOUSE", "PRESS", points[-1])
    event("RIGHTMOUSE", "RELEASE", points[-1])
    yield 0.3
    assert knife.ACTIVE_KNIFE_OPERATORS
    for pos in [position(-2, 1), position(-0.5, 0.5), position(2, 1)]:
        click(pos)
        yield 0.3
    event("SPACE", "PRESS", pos)
    event("SPACE", "RELEASE", pos)
    yield 0.9
    assert not knife.ACTIVE_KNIFE_OPERATORS, [op.bl_idname for op in window.modal_operators]
    assert not context.screen.is_animation_playing
    seams = [e for e in bm().edges if e.seam]
    assert len(seams) == 5, [(tuple(e.verts[0].co), tuple(e.verts[1].co)) for e in seams]
    assert not any(e.seam for e in bm().edges if e.is_boundary), "Old selection became seams"
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()
    yield 0.3
    assert len(bm().faces) == 1 and len(bm().edges) == 4 and not any(e.seam for e in bm().edges), (
        len(bm().faces), len(bm().edges), sum(e.seam for e in bm().edges),
        [op.bl_idname for op in context.window_manager.operators])
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.redo()
    yield 0.3
    assert sum(e.seam for e in bm().edges) == 5

    # Cancelling must restore selection and leave geometry/seams unchanged.
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.select_all(action="SELECT")
    before = len(bm().edges), sum(e.seam for e in bm().edges)
    click(position(-2, 2))
    yield 0.3
    click(position(0, 1.5))
    yield 0.3
    event("ESC", "PRESS", pos)
    event("ESC", "RELEASE", pos)
    yield 0.6
    assert not knife.ACTIVE_KNIFE_OPERATORS
    assert before == (len(bm().edges), sum(e.seam for e in bm().edges))
    assert all(e.select for e in bm().edges)
    addon_utils.disable(ROOT.name, default_set=True)
    LOG.write_text("KNIFE_POLYLINE_UI_TESTS_PASSED\n")


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
