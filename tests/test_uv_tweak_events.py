"""Run with --enable-event-simulate; exercise actual UV toolbar mouse events."""
import sys
import traceback
import tempfile
from pathlib import Path
import bpy
import bmesh
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / "uv_tweak_events.log"

def run():
    addon_utils.enable(ROOT.name, default_set=False)
    from polygroups_generator.uv_seam_overlay import _SNAPSHOTS
    from polygroups_generator.operators.uv_seam_path import _ANCHORS
    c = bpy.context
    w = c.window
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("UVTest")
    mesh.from_pydata([(x,y,0) for x in range(3) for y in range(3)], [],
                    [(x*3+y,(x+1)*3+y,(x+1)*3+y+1,x*3+y+1) for x in range(2) for y in range(2)])
    uv = mesh.uv_layers.new()
    for p in mesh.polygons:
        for i in p.loop_indices:
            v = mesh.vertices[mesh.loops[i].vertex_index]
            uv.data[i].uv = (0.2+v.co.x*0.3, 0.2+v.co.y*0.3)
    obj = bpy.data.objects.new("UVTest",mesh)
    c.collection.objects.link(obj)
    obj.select_set(True)
    c.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    c.scene.tool_settings.use_uv_select_sync=False
    c.scene.tool_settings.uv_select_mode="VERTEX"
    c.scene.polygroups_seam_preparation_settings.show_seams_uv_editor = False
    area=next(a for a in w.screen.areas if a.type=="VIEW_3D")
    area.type="IMAGE_EDITOR"
    area.ui_type="UV"
    area.spaces.active.image=bpy.data.images.new("Test", width=1000,height=1000)
    yield 0.5
    region=next(r for r in area.regions if r.type=="WINDOW")
    with c.temp_override(window=w,area=area,region=region):
        bpy.ops.image.view_all(fit_view=True)
        bpy.ops.wm.polygroups_activate_uv_seam_path()
        assert c.scene.tool_settings.uv_select_mode == "VERTEX"
        assert c.scene.polygroups_seam_preparation_settings.show_seams_uv_editor
        bpy.ops.uv.select_all(action="DESELECT")
    yield 0.5
    def click(x,y,ctrl=False,shift=False):
        px,py=region.view2d.view_to_region(x,y,clip=False)
        assert px != -2147483648,(px,py)
        px+=region.x
        py+=region.y
        w.event_simulate(type="MOUSEMOVE",value="NOTHING",x=px,y=py,ctrl=ctrl,shift=shift)
        w.event_simulate(type="LEFTMOUSE",value="PRESS",x=px,y=py,ctrl=ctrl,shift=shift)
        w.event_simulate(type="LEFTMOUSE",value="RELEASE",x=px,y=py,ctrl=ctrl,shift=shift)
    px,py=region.view2d.view_to_region(0.5,0.2,clip=False)
    w.event_simulate(type="MOUSEMOVE",value="NOTHING",x=px+region.x,y=py+region.y)
    yield 0.3
    click(0.5,0.2)
    yield 0.3
    assert _ANCHORS, "Plain click did not set the path anchor"
    assert c.scene.tool_settings.uv_select_mode == "VERTEX"
    click(0.5,0.8,True)
    yield 0.5
    bm=bmesh.from_edit_mesh(mesh)
    assert sum(edge.seam for edge in bm.edges) == 2
    # A plain click replaces the continuation anchor.
    click(0.2,0.5)
    yield 0.3
    bm=bmesh.from_edit_mesh(mesh)
    assert sum(edge.seam for edge in bm.edges) == 2
    click(0.5,0.5,True)
    yield 0.5
    bm=bmesh.from_edit_mesh(mesh)
    seams=[e for e in bm.edges if e.seam]
    assert len(seams)==3,[(e.index,e.seam) for e in bm.edges]
    assert not c.scene.tool_settings.use_uv_select_sync
    assert all(f.select for f in bm.faces)
    bm=bmesh.from_edit_mesh(mesh)
    layer=bm.loops.layers.uv.active
    for edge in bm.edges:
        if edge.seam and edge.is_manifold:
            assert any(
                len({tuple(l[layer].uv) for f in edge.link_faces for l in f.loops if l.vert==v})>1
                for v in edge.verts
            ), "Rip did not detach either side"
    yield 0.4
    assert _SNAPSHOTS.get(w.as_pointer()), "Overlay did not capture marked UV seams"
    # Modal UV movement must not read the edit BMesh in the draw callback.
    for confirm in (True, False, True):
        with c.temp_override(window=w, area=area, region=region):
            bpy.ops.transform.translate("INVOKE_DEFAULT")
        yield 0.3
        assert not _SNAPSHOTS, "Overlay read edit data during modal movement"
        px,py=region.view2d.view_to_region(0.55,0.75,clip=False)
        w.event_simulate(type="MOUSEMOVE", value="NOTHING", x=px+region.x, y=py+region.y)
        yield 0.3
        key="LEFTMOUSE" if confirm else "ESC"
        w.event_simulate(type=key, value="PRESS", x=px+region.x, y=py+region.y)
        w.event_simulate(type=key, value="RELEASE", x=px+region.x, y=py+region.y)
        yield 0.4
        assert _SNAPSHOTS.get(w.as_pointer()), "Overlay did not resume after transform"
    px,py=region.view2d.view_to_region(0.5,0.5,clip=False)
    w.event_simulate(type="RIGHTMOUSE",value="PRESS",x=px+region.x,y=py+region.y)
    w.event_simulate(type="RIGHTMOUSE",value="RELEASE",x=px+region.x,y=py+region.y)
    yield 0.3
    active=w.workspace.tools.from_space_image_mode("UV",create=False)
    assert active.idname == "builtin.select_box", active.idname
    LOG.write_text("UV_SEAM_PATH_UI_OK; UV_OVERLAY_MODAL_TRANSFORMS_OK")

steps=run()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
bpy.app.timers.register(tick,first_interval=1)
