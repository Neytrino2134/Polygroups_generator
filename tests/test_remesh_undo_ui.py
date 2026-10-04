"""Disposable GUI integration: real engine, auto materials/UV, Undo and Redo."""
import sys
import tempfile
import time
import traceback
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / "airetopo_remesh_undo_test.log"
LOG.write_text("Starting\n")


def run():
    addon_utils.enable("quad_remesher", default_set=True)
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.operators import remesh_progress
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
        context.active_object.name = "Retopo_UndoTest"
    settings = context.scene.polygroups_model_preparation_settings
    settings.remesh_pregenerate_polygroups = True
    settings.remesh_auto_generate_seams = True
    settings.remesh_auto_unwrap_checker = True
    for source_name, result_name in (
        ("Retopo_UndoTest", "Retopo_02_UndoTest"),
        ("Retopo_02_UndoTest", "Retopo_03_UndoTest"),
    ):
        with context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.object.polygroups_checked_quad_remesh(quad_count=100) == {"FINISHED"}
        deadline = time.monotonic() + 60
        while context.scene.polygroups_remesh_status.is_running:
            assert time.monotonic() < deadline, "Remesh timed out"
            yield 0.1
        yield 0.2
        assert context.scene.polygroups_remesh_status.stage == "DONE", context.scene.polygroups_remesh_status.message
        assert remesh_progress.ACTIVE_REMESH is None
        assert context.active_object.name == result_name
        with context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.ed.undo() == {"FINISHED"}
            assert bpy.data.objects.get(result_name) is None
            source = context.active_object
            assert source.name == source_name, source.name
            assert source.select_get()
            assert not source.hide_get() and not source.hide_viewport and not source.hide_render
        yield 0.2
        with context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.ed.redo() == {"FINISHED"}
            assert context.active_object.name == result_name
            assert len(context.active_object.data.uv_layers) > 0
            assert len(context.active_object.data.materials) > 0
        yield 0.2
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.polygroups_checked_quad_remesh(quad_count=100)
        bpy.ops.object.polygroups_cancel_remesh()
    yield 0.5
    assert remesh_progress.ACTIVE_REMESH is None
    assert context.scene.polygroups_remesh_status.stage == "CANCELLED"
    LOG.write_text("REMESH_UNDO_UI_TESTS_PASSED\n")


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


