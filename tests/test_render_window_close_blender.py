"""Render windows are closed after renders; the helper is inert in background mode and the render paths call it."""
import sys
from pathlib import Path
from unittest.mock import patch
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import render_window  # noqa: E402
from polygroups_generator.operators import render_queue  # noqa: E402

assert bpy.app.background and render_window.close_render_windows() == 0

calls = []
with patch.object(render_window, 'close_render_windows', lambda: calls.append(1)), \
     patch.object(render_queue, '_render_current_job_steps', lambda *a: iter([{'write_still': True}])), \
     patch.object(render_queue.bpy.ops.render, 'render', lambda **kw: {'FINISHED'}):
    render_queue._render_current_job(bpy.context, None, {})
assert calls == [1], calls
print('render window close ok')
