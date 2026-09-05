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
LOG = Path(tempfile.gettempdir()) / "airetopo_seam_eraser_ui.log"
LOG.write_text("Starting\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.operators import seam_eraser as eraser
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
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts[5].select_set(True)
        bm.select_history.add(bm.verts[5])
        for e in bm.edges:
            e.seam = True
        bmesh.update_edit_mesh(mesh)
        bpy.ops.view3d.view_axis(type="TOP")
        bpy.ops.wm.tool_set_by_id(name=eraser.AREA_TOOL_ID)
        props = context.workspace.tools.from_space_view3d_mode("EDIT_MESH").operator_properties("mesh.polygroups_seam_eraser")
        props.radius = 15
        bpy.ops.ed.undo_push(message="All seams")
    yield 0.6

    def position(x, y):
        from mathutils import Vector
        p = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector((x,y,0)))
        return round(p.x + region.x), round(p.y + region.y)

    def event(key, value, pos, ctrl=False):
        window.event_simulate(type=key, value=value, x=pos[0], y=pos[1], ctrl=ctrl)

    def state():
        bm = bmesh.from_edit_mesh(context.active_object.data)
        assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (6,7,2)
        return sum(e.seam for e in bm.edges), [tuple(v.co) for v in bm.verts if v.select]

    left = position(0,0.5)
    event("MOUSEMOVE", "NOTHING", left)
    event("WHEELUPMOUSE", "PRESS", left, ctrl=True)
    yield 0.2
    assert props.radius > 15, props.radius
    enlarged = props.radius
    event("WHEELDOWNMOUSE", "PRESS", left, ctrl=True)
    yield 0.2
    assert props.radius < enlarged, props.radius
    assert state()[0] == 7
    event("LEFTMOUSE", "PRESS", left)
    yield 0.3
    before = props.radius
    event("WHEELUPMOUSE", "PRESS", left, ctrl=True)
    yield 0.2
    active = next(iter(eraser.MESH_OT_polygroups_seam_eraser._active))
    assert props.radius == active.radius and active.radius > before
    event("WHEELDOWNMOUSE", "PRESS", left, ctrl=True)
    yield 0.2
    assert props.radius == active.radius and active.radius < before + 2

    event("MOUSEMOVE", "NOTHING", position(0,0.6))
    yield 0.2
    with context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=str(LOG.with_suffix(".png")))
    event("LEFTMOUSE", "RELEASE", position(0,0.6))
    yield 0.4
    assert state() == (6, [(2.,1.,0.)]), state()
    assert tuple(context.tool_settings.mesh_select_mode) == (True,False,False)
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()
    yield 0.3
    assert state()[0] == 7, state()
    event("LEFTMOUSE", "PRESS", left)
    yield 0.2
    event("ESC", "PRESS", left)
    event("ESC", "RELEASE", left)
    yield 0.3
    assert state() == (7, [(2.,1.,0.)]), state()

    with context.temp_override(window=window, area=area, region=region):
        props = context.workspace.tools.from_space_view3d_mode("EDIT_MESH").operator_properties("mesh.polygroups_seam_eraser")
        props.shape = "LASSO"
    loop = [position(x,y) for x,y in [(-0.3,-0.3),(0.3,-0.3),(0.3,1.3),(-0.3,1.3),(-0.3,-0.3)]]
    event("MOUSEMOVE", "NOTHING", loop[0])
    event("LEFTMOUSE", "PRESS", loop[0])
    yield 0.2
    for p in loop[1:]:
        event("MOUSEMOVE", "NOTHING", p)
        yield 0.15
    event("LEFTMOUSE", "RELEASE", loop[-1])
    yield 0.3
    assert state() == (6, [(2.,1.,0.)]), state()
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()
    yield 0.3
    assert state()[0] == 7, state()
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=eraser.PATH_TOOL_ID)
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.ed.undo_push(message="Path erase baseline")
    for pos in (position(0,0),position(2,1)):
        event("MOUSEMOVE", "NOTHING", pos)
        event("LEFTMOUSE", "PRESS", pos, ctrl=True)
        event("LEFTMOUSE", "RELEASE", pos, ctrl=True)
        yield 0.3
    assert state()[0] == 4, state()
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()
    yield 0.3
    assert state()[0] == 7, state()
    assert not eraser.MESH_OT_polygroups_seam_eraser._active
    addon_utils.disable(ROOT.name, default_set=True)
    LOG.write_text("SEAM_ERASER_UI_TESTS_PASSED")


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
