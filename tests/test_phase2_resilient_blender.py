"""Phase 2 starts despite Phase 1 failures: reads Phase 1 logs, marks unfinished collections, writes reports."""
import json
import sys
import tempfile
import time
from pathlib import Path

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import skip_marks, phase1_logs  # noqa: E402
from polygroups_generator.core.batch_report import BatchReport  # noqa: E402
from polygroups_generator.operators import phase2_pipeline as pipeline  # noqa: E402
from polygroups_generator.operators import phase2_processing as phase2  # noqa: E402
from polygroups_generator.operators.phase2_blend_export import generated_collections  # noqa: E402
from polygroups_generator.operators.batch_finalization import asset_slots  # noqa: E402

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings


def mesh(collection, name, z=0):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(-1, -1, z), (1, -1, z), (1, 1, z), (-1, 1, z)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    return obj


def source_file(path, name, retopo=(1, 2), failed=False, highpoly=True):
    col = bpy.data.collections.new(name)
    if highpoly:
        mesh(col, 'Highpoly_Generated.099', .05)
    for stage in retopo:
        mesh(col, f'Retopo_{stage:02d}_Highpoly_Generated.099')
    if failed:
        skip_marks.mark_failed_file(col, 'Quad Remesher exited without a completed result')
    bpy.data.libraries.write(str(path), {col})
    for obj in list(col.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(data)
    bpy.data.collections.remove(col)


def drive(run, limit=400):
    for _ in range(limit):
        run.step(ctx)
        if run.finished:
            return
    raise AssertionError((p.phase2_pipeline_status, p.phase2_pipeline_queue))


def quiet(kind, message):
    print(kind, message)


with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_resilient_') as directory:
    root = Path(directory)
    working = root / 'Pack.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(working))
    good1, bad, good2, broken = (root / f'Pack_Generated_00{i}.blend' for i in (1, 2, 3, 4))
    source_file(good1, 'Generated.001', retopo=(1, 2))
    source_file(bad, 'Generated.002', retopo=(1,))              # remesher stopped after pass 1
    source_file(good2, 'Generated.003', retopo=(1, 2))
    source_file(broken, 'Generated.004', retopo=(), highpoly=False)  # nothing usable inside

    # Phase 1 report in the same layout the import queue writes.
    first = BatchReport(root, [str(good1), str(bad), str(good2)])
    first.event('file_complete', dict(file='a.glb', status='success', collection='Generated.001',
                                      output_file=str(good1), input_tris=10, output_tris=5,
                                      stages=[{'stage': 'IMPORT'}], finished=time.time()))
    first.event('file_complete', dict(file='b.glb', status='failed', collection='Generated.002',
                                      output_file=str(bad), input_tris=20, error='Quad Remesher exited',
                                      failed_stage='WAIT_REMESH', failed_pass=3, traceback='trace',
                                      stages=[{'stage': 'IMPORT'}, {'stage': 'WAIT_REMESH'}],
                                      finished=time.time()))
    first.event('file_complete', dict(file='c.glb', status='success', collection='Generated.003',
                                      output_file=str(good2), input_tris=30, output_tris=6, finished=time.time()))
    first.event('finish', {'status': 'DONE'})
    # One log per file / Generated.N collection plus a compact general index and a summary.
    names = sorted(path.name for path in (first.directory / 'files').iterdir())
    assert names == ['Generated.001.json', 'Generated.002.json', 'Generated.003.json'], names
    index = json.loads((first.directory / 'files.json').read_text())
    assert [row['log'] for row in index][1] == 'files/Generated.002.json'
    assert all('stages' not in row and 'traceback' not in row for row in index)
    full = json.loads((first.directory / 'files/Generated.002.json').read_text())
    assert full['traceback'] == 'trace' and len(full['stages']) == 2
    summary = json.loads((first.directory / 'summary.json').read_text())
    assert summary['failed_files'] == 1 and summary['successful_files'] == 2
    assert [item['collection'] for item in summary['failed_collections']] == ['Generated.002']
    assert summary['failed_collections'][0]['log'] == 'files/Generated.002.json'
    assert summary['failed_collections'][0]['failed_stage'] == 'WAIT_REMESH'
    assert summary['successful_collections'] == ['Generated.001', 'Generated.003']

    failures = phase1_logs.failed_outputs(root)
    assert phase1_logs.failure_for(bad, failures)['failed_pass'] == 3
    assert phase1_logs.failure_for(good1, failures) is None
    assert phase1_logs.failure_for(bad, failures)['log'].endswith('Generated.002.json')

    # Run only the Restore pass in Import mode: nothing is baked or remeshed.
    for key in [k for k in p.bl_rna.properties.keys() if k.startswith('phase2_run_')]:
        if isinstance(getattr(p, key), bool):
            setattr(p, key, False)
    p.phase2_run_restore = True
    p.phase2_run_mode = 'IMPORT'
    p.phase2_clear_generated = False
    p.phase2_scan_subfolders = False
    run = pipeline.Phase2Pipeline(ctx, quiet)
    run.begin(ctx)
    drive(run)
    assert p.phase2_pipeline_state == 'COMPLETED', p.phase2_pipeline_status
    assert (p.phase2_done_count, p.phase2_skipped_count, p.phase2_failed_count) == (2, 1, 1), (
        p.phase2_done_count, p.phase2_skipped_count, p.phase2_failed_count)
    assert 'kept for manual work' in p.phase2_pipeline_status

    marked = [col for col in bpy.data.collections if skip_marks.is_marked(col)]
    assert len(marked) == 1 and marked[0].color_tag == 'COLOR_05'
    skipped = marked[0]
    assert 'Quad Remesher' in skipped[skip_marks.REASON_KEY]
    assert {obj.name.split('.')[0] for obj in skipped.all_objects} == {'Highpoly_Generated', 'Retopo_01_Highpoly_Generated'}
    assert all(obj.get(skip_marks.SKIP_KEY) for obj in skipped.all_objects)
    assert all(not skip_marks.is_marked(col) for col in bpy.data.collections if col is not skipped)
    assert skipped not in generated_collections(ctx.scene)
    assert skipped in generated_collections(ctx.scene, include_marked=True)

    # Deleting operators leave marked collections and meshes alone.
    assert phase2.remove_mesh_objects(list(skipped.all_objects)) == 0
    phase2.clear_generated_collections(ctx.scene)
    assert skipped.name in bpy.data.collections and len(skipped.all_objects) == 2
    assert not [col for col in bpy.data.collections if col.name.startswith('Generated.') and col is not skipped]

    # The Phase 2 report: separate folder, one log per collection, successes / skipped / failed in the summary.
    reports = sorted(path for path in (root / 'batch_reports').iterdir() if path.name.endswith('_phase2'))
    assert len(reports) == 1 and phase1_logs.phase1_runs(root) == [first.directory]
    report = reports[0]
    summary = json.loads((report / 'summary.json').read_text())
    assert summary['phase'] == 2 and summary['status'] == 'COMPLETED', summary['status']
    assert summary['total_files'] == 4 and summary['successful_files'] == 2
    assert [item['collection'] for item in summary['skipped_collections']] == ['Generated.002'], summary
    assert [item['collection'] for item in summary['failed_collections']] == ['Generated.004'], summary
    skipped_log = json.loads((report / summary['skipped_collections'][0]['log']).read_text())
    assert skipped_log['phase1_failed_pass'] == 3 and skipped_log['phase1_log'].endswith('Generated.002.json')
    assert 'Quad Remesher' in skipped_log['reason'] and skipped_log['restored_as'].startswith('Generated.')
    assert sorted(path.name for path in (report / 'files').iterdir()) == [
        'Generated.001.json', 'Generated.002.json', 'Generated.003.json', 'Generated.004.json']
    events = [json.loads(line)['event'] for line in (report / 'events.jsonl').read_text().splitlines()]
    assert events[0] == 'begin' and 'stage' in events and events[-1] == 'finish'

    # A skipped collection keeps its asset slot: Generated.003 stays the third asset.
    one, three = bpy.data.collections.new('Generated.001'), bpy.data.collections.new('Generated.003')
    holder = bpy.data.collections.new('Generated.002')
    skip_marks.mark(holder, 'x')
    assert asset_slots([(one, None, None), (three, None, None)]) == [0, 2]
    # Fixed by hand: the failed file saved again after the failure is processed like any other.
    import os
    stamped_only = root / 'Pack_Generated_005.blend'
    source_file(stamped_only, 'Generated.005', failed=True)
    later = time.time() + 1000
    for fixed in (bad, stamped_only):
        os.utime(fixed, (later, later))
    queue = phase2.Phase2Queue(ctx, [(str(bad), 'Generated.002'), (str(stamped_only), 'Generated.005')],
                               False, False, quiet)
    results = []
    queue.on_result = results.append
    queue.begin()
    for _ in range(50):
        queue.step(ctx)
        if queue.finished:
            break
    assert queue.finished and p.phase2_done_count == 2 and p.phase2_skipped_count == 0, queue.results
    assert [r['status'] for r in results] == ['success', 'success']
    assert results[0].get('repaired_after_phase1') and results[1].get('repaired_after_phase1'), results
    fixed_cols = [col for col in bpy.data.collections if col.name in {r['restored_as'] for r in results}]
    assert len(fixed_cols) == 2 and not any(skip_marks.is_marked(col) or col.get(skip_marks.FAILED_KEY)
                                            for col in fixed_cols)

    # Files edited by hand after the failure are no longer treated as failed.
    stale = {phase1_logs._key(bad): dict(failures[phase1_logs._key(bad)], finished=time.time() - 3600)}
    assert phase1_logs.failure_for(bad, stale) is None
    col = bpy.data.collections.new('Generated.009')
    skip_marks.mark_failed_file(col, 'boom')
    assert skip_marks.stamped_failure(col, time.time()) == 'boom'
    assert skip_marks.stamped_failure(col, time.time() + 3600) == ''
print('phase2 resilient ok')
