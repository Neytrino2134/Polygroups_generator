"""Interactive Blender regression for the Small Islands Merger toolbar tool."""
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
LOG = Path(tempfile.gettempdir()) / "airetopo_small_islands_tool_ui.log"
LOG.write_text("Starting\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        mesh = bpy.data.meshes.new("Small Islands Gesture Strip")
        mesh.from_pydata(
            [(x, y, 0) for x in (0, 2, 2.1, 4.1) for y in (0, 1)], [],
            [(0, 2, 3, 1), (2, 4, 5, 3), (4, 6, 7, 5)],
        )
        obj = bpy.data.objects.new(mesh.name, mesh)
        context.collection.objects.link(obj)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(mesh)
        for edge in bm.edges:
            edge.seam = edge.is_manifold
        bmesh.update_edit_mesh(mesh)
        bpy.ops.view3d.view_axis(type="TOP")
        settings = context.scene.polygroups_generator_settings
        settings.small_island_threshold = 10.0
        settings.small_island_protect_sharp = False
        settings.small_island_protect_pinned = False
        settings.small_islands_merger_shape = "BOX"
        bpy.ops.wm.tool_set_by_id(name="polygroups_generator.small_islands_merger_tool")
    yield 0.6

    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    center = obj.matrix_world @ bm.faces[1].calc_center_median()
    point = location_3d_to_region_2d(region, area.spaces.active.region_3d, center)
    point = (round(point.x + region.x), round(point.y + region.y))
    lo, hi = (point[0] - 15, point[1] - 30), (point[0] + 15, point[1] + 30)
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=lo[0], y=lo[1])
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=lo[0], y=lo[1])
    yield 0.2
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=hi[0], y=hi[1])
    yield 0.2
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=hi[0], y=hi[1])
    yield 0.5
    bm = bmesh.from_edit_mesh(mesh)
    assert sum(edge.seam for edge in bm.edges) == 1, sum(edge.seam for edge in bm.edges)
    assert settings.small_islands_merger_shape == "BOX"
    settings.small_islands_merger_shape = "LASSO"
    assert settings.small_islands_merger_shape == "LASSO"
    settings.small_islands_merger_shape = "CIRCLE"
    assert settings.small_islands_merger_shape == "CIRCLE"

    # New Select chooses one linked island; Shift-click adds another complete
    # linked island without changing the stored selection mode.
    settings.island_selector_shape = "TWEAK"
    settings.island_selector_selection_mode = "NEW"
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.wm.tool_set_by_id(name="polygroups_generator.island_selector_tool")
    yield 0.3
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    face_points = []
    for face in (bm.faces[0], bm.faces[2]):
        screen = location_3d_to_region_2d(
            region, area.spaces.active.region_3d,
            obj.matrix_world @ face.calc_center_median(),
        )
        face_points.append((round(screen.x + region.x), round(screen.y + region.y)))
    first, second = face_points
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=first[0], y=first[1])
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=first[0], y=first[1])
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=first[0], y=first[1])
    yield 0.3
    first_count = sum(face.select for face in bmesh.from_edit_mesh(mesh).faces)
    assert 0 < first_count < 3, first_count
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=second[0], y=second[1], shift=True)
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=second[0], y=second[1], shift=True)
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=second[0], y=second[1], shift=True)
    yield 0.3
    assert sum(face.select for face in bmesh.from_edit_mesh(mesh).faces) == 3
    assert settings.island_selector_selection_mode == "NEW"
    LOG.write_text("SMALL_ISLANDS_TOOL_UI_PASSED\n")


steps = run()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
bpy.app.timers.register(tick, first_interval=1.0)
