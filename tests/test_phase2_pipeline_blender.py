"""Coordinator contracts and real restore -> LOD -> GLB/FBX/Blend -> OBJ -> cleanup -> render."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_pipeline as pipeline
from polygroups_generator.operators import phase2_pipeline_stages as stages
from polygroups_generator.operators import phase2_zbrush_export as zbrush
from polygroups_generator.operators import auto_render as auto
from polygroups_generator.core import zbrush_export as zb

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings
s = ctx.scene.polygroups_mesh_finalization_settings

def reports(kind, message):
    print(kind, message)

def drive(run, limit=150):
    for _ in range(limit):
        run.step(ctx)
        if run.finished:
            return
    raise AssertionError((p.phase2_pipeline_status, p.phase2_pipeline_queue))

with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_pipeline_') as directory:
    root = Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    events = []
    def first(run, context):
        try:
            events.append('first-start')
            yield .2, 'in-flight operation', False
            events.append('first-item')
            yield .6, 'first item done', True
            events.append('first-rest')
            yield 1, 'first done', True
        finally:
            events.append('first-close')
    def second(run, context):
        events.append('second-start')
        yield 1, 'second done', True
    plan = [('A', 'First', 'phase2_run_restore', first), ('B', 'Second', 'phase2_run_restore', second)]
    with patch.object(stages, 'STAGES', plan):
        run = pipeline.Phase2Pipeline(ctx, reports); run.begin(ctx)
        assert not bpy.ops.object.polygroups_start_phase2.poll()
        assert not bpy.ops.object.polygroups_phase2_scan.poll()
        run.step(ctx); run.control('PAUSE'); run.step(ctx)
        assert run.paused and events == ['first-start', 'first-item']
        run.step(ctx); assert events == ['first-start', 'first-item']
        run.control('RESUME'); drive(run)
        assert p.phase2_pipeline_state == 'COMPLETED' and p.phase2_pipeline_progress == 100
        assert events == ['first-start', 'first-item', 'first-rest', 'first-close', 'second-start']
        events.clear()
        run = pipeline.Phase2Pipeline(ctx, reports); run.begin(ctx)
        run.step(ctx); run.control('STOP_STAGE'); drive(run)
        assert p.phase2_pipeline_state == 'STOPPED' and 'second-start' not in events
        assert json.loads(p.phase2_pipeline_queue)[0]['state'] == 'DONE'
        events.clear()
        run = pipeline.Phase2Pipeline(ctx, reports); run.begin(ctx)
        run.step(ctx); run.control('STOP_NOW')
        with patch.object(run, 'busy', return_value=True):
            run.step(ctx); assert not run.finished
        run.step(ctx)
        assert run.finished and events == ['first-start', 'first-close']
        events.clear()
        def fail(run, context):
            run.override(p, 'phase2_auto_bake', False)
            yield .1, 'before failure', False
            raise RuntimeError('Injected stage failure')
        old = p.phase2_auto_bake
        run = pipeline.Phase2Pipeline(ctx, reports)
        run.plan[0] = ('A', 'First', 'phase2_run_restore', fail)
        run.begin(ctx); drive(run)
        assert p.phase2_pipeline_state == 'FAILED' and 'second-start' not in events
        assert p.phase2_auto_bake == old and pipeline.ACTIVE_PIPELINE is None

    # Coordinator must not admit cleanup on stale, incomplete or failed ZBrush results.
    zbroot = root / 'ZBResultContracts'
    p.phase2_zbrush_directory = str(zbroot)
    asset = zb.asset_record('Generated.999', 'Resculpting_01_Highpoly_Generated.999',
                            [{'level': 0, 'faces': 1, 'verts': 4}], 0)
    admitted = []
    def after_zbrush(run, context):
        admitted.append('cleanup')
        yield 1, 'cleanup', True
    contract_plan = [('ZBRUSH', 'ZBrush', 'phase2_run_zbrush', stages.zbrush),
                     ('CLEANUP', 'Cleanup', 'phase2_run_cleanup', after_zbrush)]
    with patch.object(stages, 'STAGES', contract_plan), \
         patch.object(zbrush, 'batch_candidates', return_value=[('Generated.999', None)]), \
         patch.object(zbrush, 'export_candidates', return_value=[asset]), \
         patch.object(zbrush, 'launch_zbrush', return_value='ZBrush started'):
        run = pipeline.Phase2Pipeline(ctx, reports); run.begin(ctx)
        run.step(ctx); run.step(ctx)
        job_id = json.loads((zbroot / 'job.json').read_text())['job_id']
        def zbresult(job_id, finished, ok=True):
            (zbroot / zb.RESULT_NAME).write_text(json.dumps(dict(job_id=job_id, finished=finished,
                assets=[dict(name=asset['name'], ztl=asset['ztl'], ok=ok, error='Injected ZBrush failure')])) )
        zbresult('stale', True)
        run.step(ctx); assert not admitted and not run.finished
        zbresult(job_id, False)
        run.step(ctx); assert not admitted and not run.finished
        zbresult(job_id, True, False)
        drive(run)
        assert p.phase2_pipeline_state == 'FAILED' and not admitted
    p.phase2_zbrush_directory = ''

    # The actual ZBrush job class honors pause/resume/stop between complete assets.
    from polygroups_generator.core import zbrush_job
    jobroot = root / 'ZBrushControl'; jobroot.mkdir()
    manifest = dict(job_id='control-test', build='AUTO', assets=[dict(name='A'), dict(name='B')])
    job = zbrush_job.Job(None, str(jobroot), manifest)
    control = jobroot / 'job_control.json'
    control.write_text(json.dumps(dict(job_id='control-test', action='PAUSE')))
    def release(_):
        assert json.loads((jobroot / zb.RESULT_NAME).read_text())['paused']
        control.write_text(json.dumps(dict(job_id='control-test', action='RESUME')))
    with patch.object(zbrush_job.time, 'sleep', side_effect=release):
        assert job.wait_control() and not job.paused
    def process(asset):
        job.results.append(dict(name=asset['name'], ok=True))
        control.write_text(json.dumps(dict(job_id='control-test', action='STOP')))
    job.process = process
    job.run()
    result = json.loads((jobroot / zb.RESULT_NAME).read_text())
    assert result['finished'] and result['cancelled'] and len(result['assets']) == 1

    # Real native scene and separate-file restore. No child stage is mocked.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    sources = []
    for index in (1, 2):
        col = bpy.data.collections.new(f'Generated.{index:03d}')
        ctx.scene.collection.children.link(col)
        for prefix in ('Retopo_12_Highpoly_', 'Resculpting_01_Highpoly_'):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4)
            obj = ctx.object; obj.name = prefix + col.name
            for prev in list(obj.users_collection):
                prev.objects.unlink(obj)
            col.objects.link(obj)
            if prefix.startswith('Resculpting'):
                mod = obj.modifiers.new('PolyGroups Multires', 'MULTIRES')
                bpy.ops.object.multires_subdivide(modifier=mod.name, mode='CATMULL_CLARK')
                mod.show_viewport = mod.show_render = False
                obj.hide_viewport = obj.hide_render = True
        sources.append(col)
    bpy.data.libraries.write(str(root / 'Separated.blend'), set(sources))
    for col in sources:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    p.phase2_run_mode = 'IMPORT'; p.phase2_run_mid = False
    p.phase2_blend_export_generated = True
    p.phase2_export_glb = p.phase2_export_fbx = True
    p.phase2_auto_textures = p.phase2_auto_multiview = p.phase2_auto_freestyle = False
    p.phase2_auto_mv_hero = False
    s.smart_lods_count = 2
    s.smart_lods_target_1 = 60; s.smart_lods_target_2 = 30
    s.unreal_lod_asset_name = 'Pipeline'; s.unreal_lod_name_index = '01'; s.unreal_lod_version_index = '01'
    s.unreal_lod_copy_textures = False; s.unreal_lod_prepare_materials = False
    p.phase2_final_cleanup_generated = True  # Must be delayed until after ZTL export.
    r = ctx.scene.polygroups_render_settings
    r.output_directory = str(root / 'Renders')
    r.max_samples = 1; r.skip_existing = False; r.overwrite_existing = True
    real_configure = auto.configure_auto_render
    def small_render(context):
        real_configure(context)
        context.scene.render.resolution_x = context.scene.render.resolution_y = 32
        context.scene.render.resolution_percentage = 100
        context.scene.cycles.samples = 1
    def fake_zbrush(settings, folder):
        manifest = json.loads((folder / zb.MANIFEST_NAME).read_text())
        assert all(bpy.data.collections.get(a['name']) for a in manifest['assets'])
        assert len(list((root / '!Blend').glob('Generated.*.blend'))) == 2
        records = []
        for asset in manifest['assets']:
            path = folder / asset['ztl']; path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'Test ZTL result')
            records.append(dict(name=asset['name'], ztl=asset['ztl'], ok=True))
        (folder / zb.RESULT_NAME).write_text(json.dumps(dict(job_id=manifest['job_id'], finished=True, assets=records)))
        return 'ZBrush started'
    with patch.object(zbrush, 'launch_zbrush', side_effect=fake_zbrush), \
         patch.object(auto, 'configure_auto_render', side_effect=small_render), \
         patch('polygroups_generator.operators.zbrush_cleanup.focus_blender'):
        assert bpy.ops.object.polygroups_start_phase2() == {'FINISHED'}, p.phase2_pipeline_status
    assert p.phase2_pipeline_state == 'COMPLETED', p.phase2_pipeline_status
    assert p.phase2_pipeline_done == p.phase2_pipeline_total == 7
    assert all(row['state'] == 'DONE' for row in json.loads(p.phase2_pipeline_queue))
    assert len(json.loads(p.phase2_pipeline_collection_times)) == 2
    assert not any(col.name.startswith('Generated.') for col in ctx.scene.collection.children_recursive)
    assert not (root / '!ZBrush' / 'Mesh').exists()
    assert len(list((root / '!ZBrush' / 'ZTL').glob('*.ztl'))) == 2
    assert list((root / '!Unreal').rglob('*.glb')) and list((root / '!Unreal').rglob('*.fbx'))
    assert len(list((root / '!Blend').glob('*.blend'))) == 4
    assert len(list((root / 'Renders').rglob('*.png'))) >= 4
    assert p.phase2_final_cleanup_generated and not p.phase2_auto_transparent
    assert pipeline.ACTIVE_PIPELINE is None
    from polygroups_generator.custom_ui.schema import capture
    assert not capture(ctx, 1).errors
print('PHASE2_COORDINATOR_CONTROLS_AND_NATIVE_PIPELINE_PASSED')
