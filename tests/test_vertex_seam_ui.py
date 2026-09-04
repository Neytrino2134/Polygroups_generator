"""Disposable Blender UI test; launch with --enable-event-simulate."""
import sys
import tempfile
import traceback
from pathlib import Path

import addon_utils
import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

bpy.context.preferences.view.show_splash = False
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
EDGE_MODE = "--edge-path" in sys.argv
LOG = Path(tempfile.gettempdir()) / ("airetopo_edge_seam_ui.log" if EDGE_MODE else "airetopo_vertex_seam_ui.log")
LOG.write_text("Starting\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator import tools
    from polygroups_generator.operators import connect_vertex_seam as seam
    from polygroups_generator.operators import edge_seam_path
    tool_class = (tools.VIEW3D_WST_polygroups_edge_seam_path if EDGE_MODE
                  else tools.VIEW3D_WST_polygroups_connect_vertex_seam)
    tool_id = edge_seam_path.TOOL_ID if EDGE_MODE else seam.TOOL_ID
    first_count, second_count = (3, 3) if EDGE_MODE else (2, 3)
    draws, errors = [], []
    def checked_draw(context, tool, xy):
        try:
            draw = edge_seam_path.draw_edge_seam_cursor if EDGE_MODE else seam.draw_vertex_seam_cursor
            draw(context, tool, xy)
            draws.append(True)
        except Exception:
            errors.append(traceback.format_exc())
    # ToolDef captures draw_cursor at registration, so re-register this tool.
    bpy.utils.unregister_tool(tool_class)
    tool_class.draw_cursor = staticmethod(checked_draw)
    bpy.utils.register_tool(tool_class,
                            after={"polygroups_generator.quick_knife_seam_tool"})
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        mesh = bpy.data.meshes.new("Strip")
        mesh.from_pydata([(x, y, 0) for y in (0, 1) for x in (0, 1, 2)], [],
                         [(0, 1, 4, 3), (1, 2, 5, 4)])
        obj = bpy.data.objects.new("Strip", mesh)
        context.collection.objects.link(obj)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="VERT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.view3d.view_axis(type="TOP")
        bpy.ops.wm.tool_set_by_id(name=tool_id)
        bpy.ops.ed.undo_push(message="Vertex seam test baseline")
    yield 0.6

    def position(index):
        bm = bmesh.from_edit_mesh(context.active_object.data)
        bm.verts.ensure_lookup_table()
        point = location_3d_to_region_2d(region, area.spaces.active.region_3d, bm.verts[index].co)
        return (round(point.x + region.x), round(point.y + region.y))

    def event(key, value, pos, ctrl=False):
        window.event_simulate(type=key, value=value, x=pos[0], y=pos[1], ctrl=ctrl)

    def click(pos, ctrl=True):
        event("MOUSEMOVE", "NOTHING", pos)
        event("LEFTMOUSE", "PRESS", pos, ctrl=ctrl)
        event("LEFTMOUSE", "RELEASE", pos, ctrl=ctrl)

    def state():
        bm = bmesh.from_edit_mesh(context.active_object.data)
        return sum(e.seam for e in bm.edges), [tuple(v.co) for v in bm.verts if v.select]

    a, b, c = position(0), position(5), position(2)
    # Ordinary clicks and the chosen fallback box selection must not create seams.
    click(a, ctrl=False)
    yield 0.3
    click(b, ctrl=False)
    yield 0.3
    assert state() == (0, [(2.0, 1.0, 0.0)]), state()
    if not EDGE_MODE:
        with context.temp_override(window=window, area=area, region=region):
            assert not seam.cursor_ctrl_held(context), "Plain selection enabled the seam preview"
        for ctrl_key in ("LEFT_CTRL", "RIGHT_CTRL"):
            event(ctrl_key, "PRESS", b, ctrl=True)
            yield 0.2
            with context.temp_override(window=window, area=area, region=region):
                assert seam.cursor_ctrl_held(context), "Ctrl press did not enable preview"
            event(ctrl_key, "RELEASE", b, ctrl=False)
            yield 0.2
            with context.temp_override(window=window, area=area, region=region):
                assert not seam.cursor_ctrl_held(context), "Ctrl release left preview active"
    lo = (min(a[0], b[0]) - 20, min(a[1], b[1]) - 20)
    hi = (max(a[0], b[0]) + 20, max(a[1], b[1]) + 20)
    event("MOUSEMOVE", "NOTHING", lo)
    event("LEFTMOUSE", "PRESS", lo)
    yield 0.1
    event("MOUSEMOVE", "NOTHING", (lo[0] + 10, lo[1] + 10))
    yield 0.2
    event("MOUSEMOVE", "NOTHING", hi)
    yield 0.2
    event("LEFTMOUSE", "RELEASE", hi)
    yield 0.3
    assert state()[0] == 0 and len(state()[1]) == 6, state()
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.ed.undo_push(message="Selection fallback verified")
    click(a)
    yield 0.4
    assert state() == (0, [(0.0, 0.0, 0.0)]), state()
    event("MOUSEMOVE", "NOTHING", b)
    yield 0.4
    assert draws and not errors, errors
    with context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=str(LOG.with_suffix(".png")))
    click(b)
    yield 0.4
    assert state() == (first_count, [(2.0, 1.0, 0.0)]), state()
    if EDGE_MODE:
        bm = bmesh.from_edit_mesh(context.active_object.data)
        bm.verts.ensure_lookup_table()
        second_count = first_count + int(not bm.edges.get((bm.verts[5], bm.verts[2])).seam)
        assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (6, 7, 2)
    # Empty clicks must preserve the endpoint and existing seams.
    click((region.x + region.width - 120, region.y + 150))
    yield 0.3
    assert state() == (first_count, [(2.0, 1.0, 0.0)]), state()
    click(c)
    yield 0.4
    assert state() == (second_count, [(2.0, 0.0, 0.0)]), state()
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()
    yield 0.4
    assert state() == (first_count, [(2.0, 1.0, 0.0)]), state()
    # Continue after undo: no stale vertex references.
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()
    yield 0.3
    assert state() == (0, [(0.0, 0.0, 0.0)]), state()
    assert len(bmesh.from_edit_mesh(context.active_object.data).faces) == 2
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.redo()
    yield 0.3
    assert state() == (first_count, [(2.0, 1.0, 0.0)]), state()
    click(c)
    yield 0.4
    assert state() == (second_count, [(2.0, 0.0, 0.0)]), state()
    event("ESC", "PRESS", c)
    event("ESC", "RELEASE", c)
    yield 0.3
    assert state() == (second_count, []), state()
    click(a)
    yield 0.3
    event("RIGHTMOUSE", "PRESS", a)
    event("RIGHTMOUSE", "RELEASE", a)
    yield 0.3
    assert state() == (second_count, []), state()
    click(a)
    yield 0.3
    event("SPACE", "PRESS", a)
    event("SPACE", "RELEASE", a)
    yield 0.3
    assert state() == (second_count, []), state()
    assert not context.screen.is_animation_playing
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    yield 0.2
    assert not errors, errors
    if EDGE_MODE:
        bm = bmesh.from_edit_mesh(context.active_object.data)
        assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (6, 7, 2)
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=tool_id)
    yield 0.2
    addon_utils.disable(ROOT.name, default_set=True)
    count = len(draws)
    event("MOUSEMOVE", "NOTHING", c)
    yield 0.3
    assert len(draws) == count, "Cursor callback remained active after disabling the addon"
    LOG.write_text("EDGE_SEAM_UI_TESTS_PASSED\n" if EDGE_MODE else "VERTEX_SEAM_UI_TESTS_PASSED\n")


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
