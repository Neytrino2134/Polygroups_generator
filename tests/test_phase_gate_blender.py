"""Pause between Phase 1 and Phase 2 after Phase 1 errors: countdown, pause, resume."""
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase_gate as gate  # noqa: E402
from polygroups_generator.operators import import_queue  # noqa: E402

ctx = bpy.context
failures = [dict(collection='Generated.008', failed_stage='WAIT_REMESH', failed_pass=3)]
started = []

with patch.object(import_queue, 'schedule_phase2', lambda *args: started.append(args)):
    assert not gate.active()
    gate.begin(ctx.scene, ctx.view_layer, print, failures)
    assert gate.active() and not gate.paused() and 14 < gate.seconds_left() <= 15

    # Countdown running: the timer does nothing before the deadline, starts Phase 2 after it.
    assert gate._tick() == 0.5 and not started
    gate.STATE['deadline'] = time.monotonic() - 1
    assert gate._tick() is None and len(started) == 1 and not gate.active()

    # Pause keeps Phase 2 waiting until it is resumed explicitly.
    started.clear()
    gate.begin(ctx.scene, ctx.view_layer, print, failures)
    assert bpy.ops.object.polygroups_phase2_gate(action='PAUSE') == {'FINISHED'}
    assert gate.paused() and gate._tick() is None and not started
    gate.STATE['deadline'] = time.monotonic() - 100
    assert gate._tick() is None and not started and gate.paused()
    assert bpy.ops.object.polygroups_phase2_gate(action='CONTINUE') == {'FINISHED'}
    assert len(started) == 1 and not gate.active()

    # Continue Now during the countdown; Reset State clears a held gate.
    started.clear()
    gate.begin(ctx.scene, ctx.view_layer, print, failures)
    bpy.ops.object.polygroups_phase2_gate(action='CONTINUE')
    assert len(started) == 1 and not gate.active()
    gate.begin(ctx.scene, ctx.view_layer, print, failures)
    gate.pause()
    gate.clear()
    assert not gate.active()
    bpy.ops.object.polygroups_phase2_gate(action='CONTINUE')   # nothing held: harmless
    assert len(started) == 1
print('phase gate ok')
