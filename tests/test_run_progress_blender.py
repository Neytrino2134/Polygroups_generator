"""Phase 1 / Phase 2 / combined status text, previous collection time and ETA estimates."""
import json
import sys
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import run_progress as rp  # noqa: E402
from polygroups_generator.core.phase2_progress import PipelineOverlay  # noqa: E402
from polygroups_generator.operators import phase2_pipeline as pipeline  # noqa: E402

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings

# Estimates.
assert rp.collection_estimate([], 0, 20, 5) == (0.0, 0.0, -1.0)
previous, average, remaining = rp.collection_estimate([dict(seconds=60), dict(seconds=80)], 2, 20, 30)
assert (previous, average) == (80, 70) and remaining == 70 * 18 - 30
assert rp.collection_estimate([dict(seconds=10)], 5, 5, 99)[2] == 0
assert rp.fraction_estimate(0.0, 50) == -1 and rp.fraction_estimate(0.5, 100) == 100
assert rp.duration(3725) == '01:02:05'

# Phase 2 status lines, fed by the pipeline publish.
run = pipeline.Phase2Pipeline(ctx, lambda *a: None)
run.begin(ctx)
p.phase2_pipeline_collection_index, p.phase2_pipeline_collection_total = 7, 20
p.phase2_pipeline_collection_times = json.dumps([dict(collection='Generated.001', seconds=60),
                                                 dict(collection='Generated.002', seconds=80)])
p.phase2_pipeline_collection_seconds = 20
run.publish(ctx)
assert p.phase2_pipeline_stage_label == 'Restore and Processing'
assert p.phase2_pipeline_prev_seconds == 80 and p.phase2_pipeline_avg_seconds == 70
assert abs(p.phase2_pipeline_stage_eta - (70 * 13 - 20)) < 1e-6
text = '\n'.join(rp.phase2_lines(p))
assert 'Phase 2 | Stages 0/' in text and 'Previous collection 00:01:20' in text and 'Pass ETA 00:14:50' in text, text
assert rp.active_lines(p) == rp.phase2_lines(p)
# Later passes estimate from their own progress.
run.index, run.fraction = 1, 0.0
run.stage_started -= 100
run.publish(ctx)
assert p.phase2_pipeline_prev_seconds == 0 and p.phase2_pipeline_stage_eta == -1
run.fraction = 0.5
run.publish(ctx)
assert 99 < p.phase2_pipeline_stage_eta < 101

# Phase 1 lines and the combined run.
rp.end_combined()
run.finish(ctx, 'STOPPED')
assert not rp.COMBINED['active']
p.batch_is_running = True
p.batch_total_count, p.batch_imported_count, p.batch_import_progress = 12, 3, 25
p.batch_elapsed_seconds, p.batch_current_seconds, p.batch_average_seconds, p.batch_eta_seconds = 600, 30, 200, 1800
lines = rp.phase1_lines(p)
assert lines[0] == 'Phase 1 | Stages 3/12 | 25.0%', lines
assert 'Phase 1 ETA 00:30:00' in lines and rp.active_lines(p)[0] == lines[0]
rp.begin_combined()
combo = rp.active_lines(p)
assert combo[0].startswith('Phase 1 + 2 | 12.5% | Now: Phase 1'), combo
assert 'Phase 1 00:10:00' in combo[1] and 'Phase 2 00:00:00' in combo[1]
p.batch_is_running = False
rp.finish_phase1(900)
p.phase2_pipeline_running = True
p.phase2_pipeline_progress, p.phase2_pipeline_elapsed = 40, 300
overall, one, two = rp.combined_numbers(p)
assert (overall, one, two) == (70.0, 900, 300), (overall, one, two)
assert 'Total 00:20:00' in rp.combined_lines(p)[1] and 'Now: Phase 2' in rp.combined_lines(p)[0]
p.phase2_pipeline_running = False
rp.end_combined()
assert rp.active_lines(p) == []

# One shared draw handler regardless of how many runs hold the overlay.
first, second = PipelineOverlay(ctx), PipelineOverlay(ctx)
assert PipelineOverlay._users == 2
first.close(); first.close()
assert PipelineOverlay._users == 1
second.close()
assert PipelineOverlay._users == 0 and PipelineOverlay._handle is None
print('run progress ok')
