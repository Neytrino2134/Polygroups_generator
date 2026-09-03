"""Run with Blender --factory-startup --python; exits its disposable GUI instance."""

import sys
import tempfile
import time
import traceback
from pathlib import Path

import addon_utils
import bpy

bpy.context.preferences.view.show_splash = False
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / "airetopo_remesh_ui_test.log"
LOG.write_text("Starting\n")


def log(message):
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(message + "\n")


def run():
    addon_utils.enable("quad_remesher", default_set=True)
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.operators import remesh_progress
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    area.spaces.active.show_region_ui = True
    context.scene.airetopo_panel_visibility_settings.show_remesh_section = True
    yield 0.3
    sidebar = next(region for region in area.regions if region.type == "UI")
    sidebar.active_panel_category = "AI Retopo"
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
        context.active_object.name = "Retopo_Highpoly_Generated.001"
        collection = bpy.data.collections.new("Generated.001")
        context.scene.collection.children.link(collection)
        obj = context.active_object
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)
    status = context.scene.polygroups_remesh_status
    for expected in ("Retopo_02_Highpoly_Generated.001", "Retopo_03_Highpoly_Generated.001"):
        with context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.object.polygroups_checked_quad_remesh("INVOKE_DEFAULT", quad_count=100) == {"FINISHED"}
            assert not bpy.ops.object.polygroups_run_remesh.poll()
        assert status.is_running and status.stage == "STARTING"
        deadline = time.monotonic() + 50
        while status.is_running and time.monotonic() < deadline:
            yield 0.1
        assert status.stage == "DONE", f"{status.stage}: {status.message}"
        assert status.result_name == expected, status.result_name
        assert status.polygon_count > 0 and status.progress == 100
        assert remesh_progress.ACTIVE_REMESH is None
        log(f"Completed {status.result_name}: {status.polygon_count} polygons")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.polygroups_checked_quad_remesh(quad_count=100)
        bpy.ops.object.polygroups_cancel_remesh()
    yield 0.5
    assert status.stage == "CANCELLED" and not status.is_running
    assert remesh_progress.ACTIVE_REMESH is None
    addon_utils.disable(ROOT.name, default_set=True)
    addon_utils.disable("quad_remesher", default_set=True)
    log("REMESH_UI_TESTS_PASSED")


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
