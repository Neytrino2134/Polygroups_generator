"""Read the Phase 1 batch reports to learn which Generated.N files did not finish."""
import json
import os
from pathlib import Path

from .batch_report import FAILURE_STATUSES, FOLDER

# The failed file is written before its record is finished, so any later save is a manual fix.
# Only clock jitter (network drives, sync tools) needs a margin.
REPAIR_GRACE_SECONDS = 5.0


def _key(path):
    return os.path.normcase(os.path.realpath(str(path)))


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def phase1_runs(directory):
    """Phase 1 run folders oldest first (Phase 2 reports end with ``_phase2``)."""
    root = Path(directory) / FOLDER
    if not root.is_dir():
        return []
    return sorted(run for run in root.iterdir() if run.is_dir() and not run.name.endswith('_phase2'))


def failed_outputs(directory):
    """Map each output blend whose latest Phase 1 record is unfinished to that record.

    Later runs override earlier ones, so a file re-imported successfully drops out.
    Each value holds ``reason``, ``status``, ``failed_stage``, ``failed_pass`` and the
    absolute ``log`` path of the per-file report."""
    result = {}
    for run in phase1_runs(directory):
        rows = _json(run / 'files.json')
        if not isinstance(rows, list):
            continue
        for row in rows:
            output = row.get('output_file')
            if not output:
                continue
            key = _key(output)
            if row.get('status') in FAILURE_STATUSES:
                result[key] = dict(
                    reason=row.get('error') or f"Phase 1 {row.get('status')}",
                    status=row.get('status'), failed_stage=row.get('failed_stage'),
                    failed_pass=row.get('failed_pass'), finished=row.get('finished') or 0,
                    log=str(run / row['log']) if row.get('log') else str(run / 'files.json'),
                    output_file=output)
            else:
                result.pop(key, None)
    return result


def has_record(path, failures):
    """True when Phase 1 logged this file as unfinished, even if it was fixed since."""
    return _key(path) in failures


def failure_for(path, failures):
    """The unfinished Phase 1 record for a Generated.N blend, ignoring files edited since."""
    record = failures.get(_key(path))
    if record is None:
        return None
    try:
        modified = os.path.getmtime(path)
    except OSError:
        return record
    if record['finished'] and modified > record['finished'] + REPAIR_GRACE_SECONDS:
        return None
    return record
