"""Interactive regression for Face Selector click, Ctrl-click, and Shift gesture."""

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
LOG = Path(tempfile.gettempdir()) / "airetopo_face_selector_ui.log"
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
        mesh = bpy.data.meshes.new("Face Selector Strip")
        vertices = [(x, y, 0) for x in range(8) for y in (0, 1)]
        faces = [(2 * x, 2 * (x + 1), 2 * (x + 1) + 1, 2 * x + 1)
                 for x in range(7)]
        mesh.from_pydata(vertices, [], faces)
        obj = bpy.data.objects.new(mesh.name, mesh)
        context.collection.objects.link(obj)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.view3d.view_axis(type="TOP")
        bpy.ops.view3d.view_selected(use_all_regions=False)
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.wm.tool_set_by_id(name="polygroups_generator.face_selector_tool")
    yield 0.6

    def face_point(index):
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        point = location_3d_to_region_2d(
            region,
            area.spaces.active.region_3d,
            obj.matrix_world @ bm.faces[index].calc_center_median(),
        )
        return round(point.x + region.x), round(point.y + region.y)

    def selected():
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        return {face.index for face in bm.faces if face.select}

    def click(point, ctrl=False):
        window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=point[0], y=point[1], ctrl=ctrl)
        window.event_simulate(type="LEFTMOUSE", value="PRESS", x=point[0], y=point[1], ctrl=ctrl)
        window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=point[0], y=point[1], ctrl=ctrl)

    middle = face_point(3)
    click(middle)
    yield 0.3
    assert selected() == {2, 3, 4}, selected()
    click(middle)
    yield 0.3
    assert selected() == {1, 2, 3, 4, 5}, selected()
    click(middle, ctrl=True)
    yield 0.3
    assert selected() == {2, 3, 4}, selected()

    # Shift temporarily changes the tool to the configured additive gesture.
    settings = context.scene.polygroups_generator_settings
    settings.face_selector_shift_shape = "BOX"
    target = face_point(0)
    lo = (target[0] - 12, target[1] - 18)
    hi = (target[0] + 12, target[1] + 18)
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=lo[0], y=lo[1], shift=True)
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=lo[0], y=lo[1], shift=True)
    yield 0.1
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=hi[0], y=hi[1], shift=True)
    yield 0.1
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=hi[0], y=hi[1], shift=True)
    yield 0.3
    assert {2, 3, 4}.issubset(selected()) and 0 in selected(), selected()

    def select_baseline():
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            face.select_set(face.index == 6)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    settings.face_selector_shift_shape = "CIRCLE"
    select_baseline()
    circle = face_point(0)
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=circle[0], y=circle[1], shift=True)
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=circle[0], y=circle[1], shift=True)
    yield 0.1
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=circle[0], y=circle[1], shift=True)
    yield 0.3
    assert 6 in selected() and 0 in selected(), selected()

    settings.face_selector_shift_shape = "LASSO"
    select_baseline()
    center = face_point(0)
    points = [
        (center[0] - 15, center[1] - 20),
        (center[0] + 15, center[1] - 20),
        (center[0] + 15, center[1] + 20),
        (center[0] - 15, center[1] + 20),
    ]
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=points[0][0], y=points[0][1], shift=True)
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=points[0][0], y=points[0][1], shift=True)
    for point in points[1:]:
        yield 0.05
        window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=point[0], y=point[1], shift=True)
    yield 0.05
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=points[-1][0], y=points[-1][1], shift=True)
    yield 0.3
    assert 6 in selected() and 0 in selected(), selected()
    assert context.tool_settings.mesh_select_mode[:] == (False, False, True)
    LOG.write_text("FACE_SELECTOR_UI_PASSED\n")


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
