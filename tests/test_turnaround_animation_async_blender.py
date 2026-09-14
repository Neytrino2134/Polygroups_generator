"""Run in a Blender UI process (without --background) to test modal rendering."""
import json
import sys
import tempfile
import time
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
RESULT = Path(tempfile.gettempdir()) / "polygroups_turnaround_async_result.json"
OUTPUT = Path(tempfile.mkdtemp(prefix="polygroups_turnaround_async_"))
started_at = time.monotonic()
state = {"saw_progress_while_running": False}


def finish(message):
    RESULT.write_text(json.dumps(message), encoding="utf-8")
    bpy.ops.wm.quit_blender()
    return None


def check():
    settings = bpy.context.scene.polygroups_render_settings
    state["saw_progress_while_running"] |= (
        settings.is_running and 0 < settings.animation_progress < 100
    )
    if not settings.is_running:
        return finish({
            "status": settings.animation_status,
            "progress": settings.animation_progress,
            "saw_progress_while_running": state["saw_progress_while_running"],
            "output_exists": Path(settings.animation_last_output).is_file(),
            "display_restored": bpy.context.preferences.view.render_display_type == state["display_before"],
        })
    if time.monotonic() - started_at > 60:
        return finish({"error": "Timed out during modal render", "status": settings.animation_status})
    return 0.1


def start():
    try:
        addon_utils.enable(ROOT.name, default_set=False)
        scene = bpy.context.scene
        bpy.ops.mesh.primitive_cube_add()
        assert bpy.ops.object.polygroups_prepare_turnaround_animation() == {"FINISHED"}
        bpy.ops.object.camera_add(location=(0, -6, 2))
        camera = bpy.context.object
        camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.camera = camera
        settings = scene.polygroups_render_settings
        settings.animation_frame_count = 5
        settings.resolution_x = settings.resolution_y = 32
        settings.render_engine = "EEVEE"
        settings.animation_media_type = "VIDEO"
        settings.animation_container = "MKV"
        settings.output_directory = str(OUTPUT)
        state["display_before"] = bpy.context.preferences.view.render_display_type
        window = bpy.context.window_manager.windows[0]
        area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
        region = next(region for region in area.regions if region.type == "WINDOW")
        with bpy.context.temp_override(window=window, area=area, region=region):
            result = bpy.ops.object.polygroups_render_turnaround_animation("INVOKE_DEFAULT")
        if "RUNNING_MODAL" not in result:
            return finish({"error": f"Invoke returned {result}", "status": settings.animation_status})
        bpy.app.timers.register(check, first_interval=0.1)
    except Exception as error:
        return finish({"error": repr(error)})
    return None


bpy.app.timers.register(start, first_interval=1.0)
