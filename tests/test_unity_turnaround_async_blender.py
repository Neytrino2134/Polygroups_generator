"""Run in a Blender UI process to verify the complete modal Unity render."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
RESULT = Path(tempfile.gettempdir()) / 'polygroups_unity_async_result.json'
OUTPUT = Path(tempfile.mkdtemp(prefix='polygroups_unity_async_'))
state = {'progress': [], 'statuses': []}
started = time.monotonic()

def finish(error=None):
    from polygroups_generator.operators import turnaround_animation as ta
    settings = bpy.context.scene.polygroups_render_settings
    files = list(OUTPUT.rglob('*'))
    result = dict(state)
    result.update(error=error, status=settings.animation_status,
                  final_progress=settings.animation_progress,
                  image_count=len([p for p in files if p.suffix in {'.png', '.jpg', '.webp'}]),
                  mp4_count=len([p for p in files if p.suffix == '.mp4']),
                  selection_restored=bpy.context.active_object == state.get('source'),
                  freestyle_restored=bpy.context.scene.render.use_freestyle,
                  display_restored=bpy.context.preferences.view.render_display_type == state.get('display'),
                  task_cleared=ta._ACTIVE_RENDER_TASK is None,
                  handlers_cleared=not any(getattr(h, '__self__', None).__class__.__name__ ==
                      'OBJECT_OT_polygroups_render_unity_turnaround' for h in bpy.app.handlers.render_post))
    result.pop('source', None)
    RESULT.write_text(json.dumps(result), encoding='utf-8')
    bpy.ops.wm.quit_blender()

def check():
    settings = bpy.context.scene.polygroups_render_settings
    state['progress'].append(settings.animation_progress)
    if not state['statuses'] or state['statuses'][-1] != settings.animation_status:
        state['statuses'].append(settings.animation_status)
    if not settings.is_running:
        finish()
        return None
    if time.monotonic() - started > 120:
        finish('timeout')
        return None
    return .1

def start():
    try:
        addon_utils.enable(ROOT.name, default_set=False)
        from polygroups_generator.operators import render_queue as rq
        scene = bpy.context.scene
        bpy.ops.mesh.primitive_cube_add()
        source = bpy.context.object
        source['unity_prepared'] = True
        state['source'] = source
        scene.render.use_freestyle = True
        settings = scene.polygroups_render_settings
        settings.freestyle_edges = True
        settings.animation_frame_count = 2
        settings.render_engine = 'EEVEE'
        state['display'] = bpy.context.preferences.view.render_display_type
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with patch.object(rq, '_current_state_render_path', return_value=str(OUTPUT / 'image.png')):
            with bpy.context.temp_override(window=window, area=area, region=region):
                result = bpy.ops.object.polygroups_render_unity_turnaround('INVOKE_DEFAULT')
        assert result == {'RUNNING_MODAL'}, result
        bpy.app.timers.register(check, first_interval=.1)
    except Exception as error:
        finish(repr(error))
    return None

bpy.app.timers.register(start, first_interval=1)
