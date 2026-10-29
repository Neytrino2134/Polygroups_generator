"""Status text for Phase 1, Phase 2 and the combined Phase 1 + 2 run, shared by the 3D overlay and the N panel."""
import json

# Phase 1 + 2 run: Phase 1 hands over to Phase 2 through a timer, so the combined state lives here.
COMBINED = dict(active=False, phase1_done=False, phase1_seconds=0.0)
PHASE1_WEIGHT = 0.5


def duration(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'


def begin_combined():
    COMBINED.update(active=True, phase1_done=False, phase1_seconds=0.0)


def finish_phase1(seconds):
    if COMBINED['active']:
        COMBINED.update(phase1_done=True, phase1_seconds=seconds)


def end_combined():
    COMBINED.update(active=False, phase1_done=False, phase1_seconds=0.0)


def collection_estimate(timings, index, total, current_seconds):
    """(previous, average, remaining) seconds of the Restore stage from the finished collections."""
    seconds = [item['seconds'] for item in timings]
    if not seconds:
        return 0.0, 0.0, -1.0
    average = sum(seconds) / len(seconds)
    return seconds[-1], average, max(0.0, average * max(0, total - index) - current_seconds)


def fraction_estimate(fraction, seconds):
    """Remaining seconds from the progress of the running pass; -1 while it is too early to tell."""
    if fraction < 0.02 or seconds < 1:
        return -1.0
    return seconds * (1 - fraction) / fraction


def eta_text(value):
    return 'estimating' if value < 0 else duration(value)


def phase2_running(p):
    return bool(p.phase2_pipeline_running)


def phase2_lines(p):
    stage = p.phase2_pipeline_stage_label or p.phase2_pipeline_state or 'Ready'
    lines = [f'Phase 2 | Stages {p.phase2_pipeline_done}/{p.phase2_pipeline_total} | {p.phase2_pipeline_progress:.1f}%',
             f'{stage} | {p.phase2_pipeline_stage_progress:.1f}%']
    if p.phase2_pipeline_detail:
        lines.append(f'{p.phase2_pipeline_detail}: {p.phase2_pipeline_detail_progress:.1f}%')
    if p.phase2_pipeline_status:
        lines.append(p.phase2_pipeline_status)
    lines.append(f'Total {duration(p.phase2_pipeline_elapsed)} | Pass {duration(p.phase2_pipeline_stage_seconds)}'
                 f' | Collection {duration(p.phase2_pipeline_collection_seconds)}')
    if p.phase2_pipeline_prev_seconds > 0:
        lines.append(f'Previous collection {duration(p.phase2_pipeline_prev_seconds)}'
                     f' | Average {duration(p.phase2_pipeline_avg_seconds)}')
    if p.phase2_pipeline_running:
        lines.append(f'Pass ETA {eta_text(p.phase2_pipeline_stage_eta)}')
    return lines


def phase1_lines(p):
    from ..localization import t
    import bpy
    done = p.batch_imported_count + p.batch_failed_count
    lines = [f'Phase 1 | Stages {done}/{p.batch_total_count} | {p.batch_import_progress:.1f}%']
    if p.batch_stage:
        try:
            lines.append(t(bpy.context, 'import_stage_' + p.batch_stage))
        except Exception:
            lines.append(p.batch_stage)
    if p.batch_current_file:
        lines.append(p.batch_current_file)
    lines.append(f'Total {duration(p.batch_elapsed_seconds)} | File {duration(p.batch_current_seconds)}')
    if p.batch_imported_count:
        lines.append(f'Average file {duration(p.batch_average_seconds)}')
    if p.batch_is_running:
        lines.append(f'Phase 1 ETA {eta_text(p.batch_eta_seconds)}')
    return lines


def combined_numbers(p):
    """(overall percent, phase 1 seconds, phase 2 seconds) of a combined run."""
    phase1_seconds = COMBINED['phase1_seconds'] if COMBINED['phase1_done'] else p.batch_elapsed_seconds
    phase1 = 100.0 if COMBINED['phase1_done'] else p.batch_import_progress
    phase2 = p.phase2_pipeline_progress if phase2_running(p) else 0.0
    overall = PHASE1_WEIGHT * phase1 + (1 - PHASE1_WEIGHT) * phase2
    phase2_seconds = p.phase2_pipeline_elapsed if phase2_running(p) else 0.0
    return overall, phase1_seconds, phase2_seconds


def combined_lines(p):
    overall, phase1_seconds, phase2_seconds = combined_numbers(p)
    current = 'Phase 2' if (COMBINED['phase1_done'] or phase2_running(p)) else 'Phase 1'
    return [f'Phase 1 + 2 | {overall:.1f}% | Now: {current}',
            f'Total {duration(phase1_seconds + phase2_seconds)} | Phase 1 {duration(phase1_seconds)}'
            f' | Phase 2 {duration(phase2_seconds)}']


def active_lines(p):
    """Overlay text for whatever is running now; empty when nothing is."""
    if p.batch_is_running:
        lines = phase1_lines(p)
    elif phase2_running(p):
        lines = phase2_lines(p)
    else:
        return []
    return combined_lines(p) + lines if COMBINED['active'] else lines


def parse_timings(text):
    try:
        return json.loads(text)
    except ValueError:
        return []
