"""Adapters for existing Phase 2 passes. Yields (fraction, status, item boundary)."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import bpy


def restore(run, context):
    from . import phase2_processing as phase
    p = run.settings
    mode = p.phase2_run_mode
    # Old scenes can still store the former RESCULPT restore mode. The new
    # switch controls resculpting independently of that saved enum value.
    rebake = mode != 'IMPORT'
    resculpt = rebake and p.phase2_run_resculpt_retopo01
    for name, value in dict(phase2_auto_bake=rebake,
            phase2_mesh_auto_repair=rebake, phase2_repack_after_repair=rebake,
            phase2_resculpt_retopo01=resculpt,
            phase2_high_remesh_before_resculpting=resculpt and p.phase2_run_high_remesh,
            phase2_repair_after_resculpt=resculpt and p.phase2_run_repair_resculpt,
            phase2_autobake_retopo01=resculpt and p.phase2_run_bake_resculpt,
            phase2_mid_remesh=p.phase2_run_mid).items():
        run.override(p, name, value)
    entries = phase.scan(context, run.report)
    if not entries:
        raise ValueError('No separated Generated collections found')
    if p.phase2_clear_generated:
        phase.clear_generated_collections(context.scene)
    queue = phase.Phase2Queue(context, entries, rebake, p.phase2_repair_artifacts, run.report)
    phase.ACTIVE_PHASE2 = queue
    queue.begin()
    started = None
    timings = []
    try:
        while not queue.finished:
            previous = queue.index
            if started is None and queue.index < len(entries):
                started = time.monotonic()
            queue.step(context)
            boundary = queue.index != previous
            now = time.monotonic()
            if started is not None:
                p.phase2_pipeline_collection_seconds = now - started
            if boundary:
                timings.append(dict(collection=entries[previous][1], seconds=round(now-started, 2)))
                p.phase2_pipeline_collection_times = json.dumps(timings)
                started = None
            if queue.results and queue.results[-1][1]:
                raise RuntimeError(queue.results[-1][1])
            bake = context.scene.polygroups_baking_settings
            progress = bake.bake_task_progress if 'BAKE' in queue.stage and bake.bake_task_is_running else 0
            detail = queue.stage
            if queue.stage in {'MID_REMESH_WAIT', 'RETOPO01_HIGH_REMESH_WAIT'}:
                detail = p.phase2_status
                progress = getattr(queue.mid_remesh.job, 'pipeline_progress', 0) * 100
            stage_order = ['RESTORE', 'MID_REMESH_WAIT', 'BAKE_START', 'BAKE_WAIT',
                           'RETOPO01_HIGH_REMESH_WAIT',
                           'RETOPO01_RESCULPT', 'RETOPO01_PREPARE', 'RETOPO01_BAKE_START', 'RETOPO01_BAKE_WAIT']
            within = (stage_order.index(queue.stage) + progress/100)/len(stage_order) if queue.stage in stage_order else 0
            run.detail(progress, detail)
            fraction = min(1, (queue.index + within) / len(entries))
            yield fraction, p.phase2_status, boundary
    finally:
        queue.finish(stopped=not queue.finished)
        if phase.ACTIVE_PHASE2 is queue:
            phase.ACTIVE_PHASE2 = None


def prepare(run, context):
    from .batch_finalization import OBJECT_OT_polygroups_batch_finalization
    from ..core.asset_names import asset_name
    p, s = run.settings, context.scene.polygroups_mesh_finalization_settings
    for name, value in dict(phase2_final_lods=True, phase2_final_rename=True,
            phase2_final_lod_engine="UNITY" if p.phase2_run_engine == "UNITY" else "UNREAL", phase2_final_rename_engine=p.phase2_run_engine,
            phase2_final_cleanup_generated=False).items():
        run.override(p, name, value)
    unity = p.phase2_run_engine == 'UNITY'
    worker = SimpleNamespace(report=run.report,
        asset=asset_name(s.unity_asset_name if unity else s.unreal_lod_asset_name),
        name_index=s.unity_name_index if unity else s.unreal_lod_name_index,
        version_index=s.unity_asset_index if unity else s.unreal_lod_version_index)
    if not worker.asset or not worker.name_index.isdigit() or not worker.version_index.isdigit():
        raise ValueError('Set an Asset Name and numeric indices in Batch Finalization')
    p.phase2_final_is_running = True
    try:
        for fraction, text in OBJECT_OT_polygroups_batch_finalization.steps(worker, context):
            run.detail(fraction*100, text)
            yield fraction, text, 'assets completed' in text
    finally:
        p.phase2_final_is_running = False


def export_prepared(run, context):
    p = run.settings
    run.override(p, 'phase2_export_engine', p.phase2_run_engine)
    yield 0, 'Exporting prepared models', False
    if 'FINISHED' not in bpy.ops.object.polygroups_phase2_export('EXEC_DEFAULT'):
        raise RuntimeError(p.phase2_export_status)
    yield 1, p.phase2_export_status, True


def export_blend(run, context):
    from .phase2_blend_export import asset_collections, generated_collections, blend_file_stem, export_collection_blend
    p = run.settings
    collections = asset_collections(context.scene)
    if p.phase2_blend_export_generated:
        collections += generated_collections(context.scene)
    if not collections:
        raise ValueError('No collections available for Blend export')
    names = [blend_file_stem(col) for col in collections]
    if len(set(name.casefold() for name in names)) != len(names):
        raise ValueError('Blend export file names collide')
    folder = Path(bpy.data.filepath).parent / '!Blend'
    folder.mkdir(exist_ok=True)
    for i, (col, name) in enumerate(zip(collections, names)):
        yield i/len(names), f'Export Blend {i+1}/{len(names)}: {name}', False
        export_collection_blend(col, str(folder / (name + '.blend')), p.phase2_blend_export_pack,
            reset_y=p.phase2_blend_export_reset_y and col.name.endswith('_Collection'))
        p.phase2_blend_export_status = f'Exported {i+1}/{len(names)} Blend files'
        yield (i+1)/len(names), p.phase2_blend_export_status, True


def zbrush(run, context):
    from . import phase2_zbrush_export as export
    from ..core import zbrush_export as zb
    p = run.settings
    candidates = export.batch_candidates(context.scene)
    if not candidates:
        raise ValueError('ZBrush requires Resculpting_01_Highpoly_Generated.N with Multires')
    root = zb.output_root(bpy.data.filepath, bpy.path.abspath(p.phase2_zbrush_directory))
    root.mkdir(parents=True, exist_ok=True)
    assets = []
    for i, candidate in enumerate(candidates):
        assets.extend(export.export_candidates(context, [candidate], root))
        yield .4*(i+1)/len(candidates), f'Exported OBJ {i+1}/{len(candidates)}', True
    export.write_job(root, assets, p.phase2_zbrush_build, bpy.data.filepath)
    manifest = json.loads((root / zb.MANIFEST_NAME).read_text(encoding='utf-8'))
    run.zbrush_job = (root, manifest['job_id'])
    status = export.launch_zbrush(p, root)
    p.phase2_zbrush_status = status
    if status != 'ZBrush started':
        raise RuntimeError(status)
    while True:
        path = root / zb.RESULT_NAME
        result = None
        try:
            result = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        if result and result.get('job_id') == manifest['job_id']:
            records = result.get('assets', [])
            if result.get('cancelled'):
                raise RuntimeError('ZBrush job stopped; inputs retained')
            if result.get('paused'):
                done = sum(item.get('ok') is True for item in records)
                yield .4 + .6*done/len(assets), f'ZBrush paused after {done}/{len(assets)} assets', True
                continue
            if any(item.get('ok') is False for item in records):
                raise RuntimeError('ZBrush failed: ' + '; '.join(item.get('error', item.get('name', '')) for item in records if not item.get('ok')))
            if result.get('finished'):
                expected = {(a['name'], a['ztl']) for a in assets}
                actual = {(a.get('name'), a.get('ztl')) for a in records}
                if len(records) != len(assets) or actual != expected or not all(a.get('ok') is True for a in records):
                    raise RuntimeError('Incomplete ZBrush result; inputs retained')
                for asset in assets:
                    target = root / asset['ztl']
                    if not target.is_file() or not target.stat().st_size:
                        raise RuntimeError('Missing ZTL: ' + asset['ztl'])
                run.zbrush_root = root
                run.zbrush_job = None
                yield 1, 'ZBrush: all ZTL files verified', True
                return
            done = sum(item.get('ok') is True for item in records)
        else:
            done = 0
        fraction = .4 + .6*done/len(assets)
        run.detail(100*done/len(assets), f'ZBrush ZTL {done}/{len(assets)}')
        yield fraction, f'Waiting for ZBrush: {done}/{len(assets)} ZTL', False


def cleanup(run, context):
    from .phase2_blend_export import generated_collections
    from .zbrush_cleanup import delete_generated, clear_mesh_folder, focus_blender
    files, folders = clear_mesh_folder(run.zbrush_root) if run.zbrush_root else (0, 0)
    cols, objects = delete_generated(generated_collections(context.scene))
    if run.zbrush_root:
        focus_blender()
    yield 1, f'Cleanup: {cols} collections / {objects} objects / {files} files / {folders} folders', True


def render(run, context):
    from .auto_render import OBJECT_OT_polygroups_phase2_auto_render
    from .phase2_pipeline_render import PipelineRenderPreview
    p = run.settings
    run.override(p, 'phase2_auto_transparent', p.phase2_run_transparent)
    worker = SimpleNamespace(stop_requested=False, _preview=PipelineRenderPreview(context, run))
    p.phase2_auto_render_running = True
    try:
        for fraction, text in OBJECT_OT_polygroups_phase2_auto_render.steps(worker, context):
            yield fraction, text, text.startswith('Auto Render')
    finally:
        worker._preview.close()
        p.phase2_auto_render_running = False


STAGES = (
    ('RESTORE', 'Restore and Processing', 'phase2_run_restore', restore),
    ('PREPARE', 'Prepare LODs / Rename', 'phase2_run_prepare', prepare),
    ('EXPORT', 'Export Prepared GLB / FBX', 'phase2_run_export', export_prepared),
    ('BLEND', 'Export Blend', 'phase2_run_blend', export_blend),
    ('ZBRUSH', 'Export ZBrush / Build ZTL', 'phase2_run_zbrush', zbrush),
    ('CLEANUP', 'Cleanup Temporary Collections / Mesh', 'phase2_run_cleanup', cleanup),
    ('RENDER', 'Auto Render', 'phase2_run_render', render),
)
