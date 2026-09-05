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
LOG = Path(tempfile.gettempdir()) / "airetopo_seam_hotkeys_ui.log"
LOG.write_text("Starting\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.wm.tool_set_by_id(name="builtin.select")
    yield 0.3

    def active():
        return context.workspace.tools.from_space_view3d_mode("EDIT_MESH").idname

    def event(key, ctrl=False):
        x, y = region.x + region.width // 2, region.y + region.height // 2
        window.event_simulate(type=key, value="PRESS", x=x, y=y, ctrl=ctrl)
        window.event_simulate(type=key, value="RELEASE", x=x, y=y, ctrl=ctrl)

    for key, ctrl, names in (
        ("D", False, ("connect_vertex_seam", "edge_seam_path", "connect_vertex_seam")),
        ("D", True, ("seam_eraser", "edge_seam_eraser", "seam_eraser")),
        ("K", False, ("knife_seam", "quick_knife_seam", "knife_seam")),
    ):
        for name in names:
            event(key, ctrl)
            yield 0.3
            assert active() == "polygroups_generator." + name + "_tool", (key, active())
        event("RIGHTMOUSE")
        yield 0.3
        assert active() == "builtin.select", active()

    # A selected anchor is the pending continuation for each path tool.
    for name in ("connect_vertex_seam", "edge_seam_path", "edge_seam_eraser"):
        with context.temp_override(window=window, area=area, region=region):
            bpy.ops.mesh.polygroups_select_seam_tool(tool_id="polygroups_generator." + name + "_tool")
            bpy.ops.mesh.select_all(action="DESELECT")
            bm = bmesh.from_edit_mesh(context.active_object.data)
            bm.verts.ensure_lookup_table()
            bm.verts[0].select_set(True)
            bmesh.update_edit_mesh(context.active_object.data)
        event("RIGHTMOUSE")
        yield 0.3
        assert active() == "polygroups_generator." + name + "_tool"
        assert not any(v.select for v in bm.verts)
        event("RIGHTMOUSE")
        yield 0.3
        assert active() == "builtin.select"
    addon_utils.disable(ROOT.name, default_set=True)
    LOG.write_text("SEAM_HOTKEYS_UI_TESTS_PASSED\n")


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
