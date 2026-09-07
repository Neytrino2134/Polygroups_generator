"""Disposable Blender UI test for staged Apply Cutter Seams progress."""
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

import addon_utils
import bpy

bpy.context.preferences.view.show_splash = False
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / "airetopo_cutter_progress_ui.log"
LOG.write_text("Starting\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.operators import object_seam_cutter as cutter
    from polygroups_generator.core.remesh_cursor import RemeshCursor

    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        target = context.active_object
        bpy.ops.mesh.primitive_plane_add(size=4)
        cutter_object = context.active_object
        cutter_object[cutter.CUTTER_PROP] = True
        cutter_object[cutter.CUTTER_TYPE_PROP] = "PLANE"
        target.select_set(True)
        cutter_object.select_set(True)
        context.view_layer.objects.active = target

    settings = context.scene.polygroups_object_seam_cutter_settings
    settings.cutter_auto_fix_mesh = True
    settings.cutter_auto_fix_seam_check = False
    settings.hide_cutters_after_apply = False
    settings.delete_cutters_after_apply = False
    draws = []
    original_draw = RemeshCursor.draw

    def checked_draw(cursor):
        original_draw(cursor)
        draws.append((cursor.label, cursor.percent))

    RemeshCursor.draw = checked_draw
    stages = []
    progress = []
    try:
        with (
            patch.object(cutter, "_apply_cutters_to_mesh", return_value=7),
            patch.object(cutter, "_fill_open_nonmanifold_boundaries", return_value=0),
            patch.object(cutter, "_triangulate_ngons_for_autofix", return_value=0),
            patch.object(cutter, "_smart_relax_seams_for_autofix", return_value=0),
            patch.object(cutter, "play_operation_done_sound"),
        ):
            with context.temp_override(window=window, area=area, region=region):
                result = bpy.ops.object.polygroups_apply_cutter_seams()
            assert result == {"RUNNING_MODAL"}
            window.event_simulate(
                type="MOUSEMOVE", value="NOTHING",
                x=region.x + region.width // 2,
                y=region.y + region.height // 2,
            )
            for _ in range(100):
                stage = settings.cutter_apply_stage
                if not stages or stages[-1] != stage:
                    stages.append(stage)
                progress.append(settings.cutter_apply_progress)
                if not settings.cutter_apply_is_running:
                    break
                yield 0.03
    finally:
        RemeshCursor.draw = original_draw

    expected = ["BACKUP", "PREPARING", "AUTOFIX_BEFORE", "CUTTING", "AUTOFIX_AFTER",
                "FINDING_GAPS", "MERGING_ISLANDS", "WELDING",
                "RELAXING_SEAMS", "TRIANGULATING_NGONS", "FINALIZING", "DONE"]
    assert stages == expected, stages
    assert progress == sorted(progress)
    assert settings.cutter_apply_progress == 100
    assert settings.last_marked_edge_count == 7
    backup = bpy.data.objects.get("Backup_" + target.name)
    assert backup is not None
    snapshots = [
        obj for obj in bpy.data.objects
        if obj.get(cutter.CUTTER_BACKUP_SNAPSHOT_PROP)
        and obj.get(cutter.CUTTER_BACKUP_OWNER_PROP) == backup.name
    ]
    assert len(snapshots) == 1
    assert snapshots[0].get(cutter.CUTTER_ORIGINAL_NAME_PROP) == cutter_object.name
    assert draws and all(label == "Cutter" for label, _value in draws)
    addon_utils.disable(ROOT.name, default_set=True)
    LOG.write_text("CUTTER_PROGRESS_UI_TESTS_PASSED\n")


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
