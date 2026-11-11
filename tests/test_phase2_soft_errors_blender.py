"""Phase 2 keeps going after Resculpting / MID remesh errors, exports failed Generated.N to !Blend,
and Do Selected Phase 2 limits the run to one Generated.N with its own version index."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import phase2_scope, skip_marks  # noqa: E402
from polygroups_generator.operators import phase2_mid_remesh, phase2_pipeline_stages as stages  # noqa: E402
from polygroups_generator.operators import phase2_processing as phase  # noqa: E402
from polygroups_generator.operators.batch_finalization import OBJECT_OT_polygroups_batch_finalization  # noqa: E402
from polygroups_generator.operators.phase2_pipeline import selected_generated  # noqa: E402

ctx = bpy.context
scene = ctx.scene
p = scene.polygroups_model_preparation_settings
bake = scene.polygroups_baking_settings
for name in ('phase2_remove_loose_parts', 'phase2_mesh_auto_repair', 'phase2_topology_guard_highest',
             'phase2_smart_uv_repair', 'phase2_repack_after_repair', 'phase2_autobake_retopo01',
             'phase2_delete_lower_retopo', 'phase2_mid_remesh', 'phase2_resculpt_retopo01',
             'phase2_high_remesh_before_resculpting', 'phase2_repair_after_resculpt'):
    setattr(p, name, False)


def mesh_object(name, collection, x=0.0):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, 0, 0), (x + 1, 0, 0), (x + 1, 1, 0), (x, 1, 0)], [], [(0, 1, 2, 3)])
    mesh.uv_layers.new(name='UVMap')
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def generated(number):
    digits = f'{number:03d}'
    collection = bpy.data.collections.new(f'Generated.{digits}')
    scene.collection.children.link(collection)
    mesh_object(f'Highpoly_Generated.{digits}', collection, number * 3)
    for stage in (1, 2):
        mesh_object(f'Retopo_{stage:02d}_Highpoly_Generated.{digits}', collection, number * 3)
    return collection


class FakeRemesh:
    """Phase2MidRemesh stand-in: fails like Quad Remesher did for Generated.003."""
    started = aborted = 0
    fail_on = 'poll'

    def __init__(self, *_args, **_kwargs):
        self.job = SimpleNamespace(pipeline_progress=0)

    def start(self, _context):
        FakeRemesh.started += 1
        if FakeRemesh.fail_on == 'start':
            raise RuntimeError('Quad Remesher is not installed')

    def poll(self):
        raise RuntimeError('Quad Remesher exited without a completed result')

    def abort(self):
        FakeRemesh.aborted += 1


def process(collection, bake_result='DONE'):
    records = []
    queue = phase.Phase2Queue(ctx, [('', collection.name)], True, False, lambda *_: None)
    queue.on_result = records.append
    queue.start_bake = lambda _context, target=None: setattr(bake, 'bake_task_stage', bake_result)
    queue.begin()
    with patch.object(phase2_mid_remesh, 'Phase2MidRemesh', FakeRemesh):
        for _ in range(50):
            if queue.finished:
                break
            queue.step(ctx)
    assert queue.finished
    return records[0]


with tempfile.TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'rocks.blend'))
    other = generated(1)

    # 1. Quad Remesher fails in the HIGH remesh for Resculpting: the MID result is kept and finished.
    p.phase2_resculpt_retopo01 = p.phase2_high_remesh_before_resculpting = True
    third = generated(3)
    record = process(third)
    assert record['status'] == 'success' and 'error' not in record, record
    assert 'Quad Remesher exited' in record['warnings'][0] and 'RETOPO01_HIGH_REMESH_WAIT' in record['warnings'][0]
    assert FakeRemesh.aborted == 1
    assert third.color_tag == 'COLOR_05' and not skip_marks.is_marked(third)
    assert 'Quad Remesher' in third[phase2_scope.WARNING_KEY]
    assert p.phase2_done_count == 1 and p.phase2_failed_count == 0
    print('RESCULPT_ERROR_CONTINUES_OK')

    # 2. The MID remesh cannot start: the existing highest Retopo_02 is baked instead.
    p.phase2_resculpt_retopo01 = p.phase2_high_remesh_before_resculpting = False
    p.phase2_mid_remesh = True
    FakeRemesh.fail_on = 'start'
    fourth = generated(4)
    record = process(fourth)
    assert record['status'] == 'success', record
    assert 'kept Retopo_02_Highpoly_Generated.004' in record['warnings'][0], record
    assert fourth.color_tag == 'COLOR_05' and not skip_marks.is_marked(fourth)
    p.phase2_mid_remesh = False
    print('MID_ERROR_KEEPS_HIGHEST_OK')

    # 3. The MID bake itself fails: a real failure, marked and kept for manual work.
    fifth = generated(5)
    record = process(fifth, bake_result='FAILED')
    assert record['status'] == 'failed' and skip_marks.is_marked(fifth)
    print('BAKE_ERROR_STILL_FAILS_OK')

    # 4. Do Selected Phase 2: the Generated.N of the selected Retopo_XX only.
    bpy.ops.object.select_all(action='DESELECT')
    retopo = third.objects['Retopo_02_Highpoly_Generated.003']
    retopo.select_set(True)
    ctx.view_layer.objects.active = retopo
    assert selected_generated(ctx) == ['Generated.003']
    queues = []
    runner = SimpleNamespace(settings=p, report=lambda *_: None, detail=lambda *_: None,
                             override=lambda owner, name, value: setattr(owner, name, value),
                             collection_result=lambda *_: None, begin_collections=queues.append)

    class Queue:
        def __init__(self, *_args):
            self.finished, self.index, self.stage, self.results = False, 0, 'RESTORE', []

        def begin(self):
            pass

        def step(self, _context):
            self.finished, self.index = True, 1
            p.phase2_done_count, p.phase2_failed_count = 1, 0

        def finish(self, stopped=False):
            self.finished = True

    phase2_scope.begin(['Generated.003'])
    with patch.object(phase, 'scan', side_effect=AssertionError('no file scan')), \
            patch.object(phase, 'Phase2Queue', Queue):
        list(stages.restore(runner, ctx))
    assert queues == [[('', 'Generated.003')]], queues

    # Rename gives the version index from the number: Generated.003 -> _03, Generated.001 untouched.
    p.phase2_final_lods, p.phase2_final_rename = False, True
    p.phase2_final_rename_engine = 'FAB'
    p.phase2_final_cleanup_generated = False
    worker = SimpleNamespace(report=lambda *_: None, asset='Rock', name_index='07', version_index='01', prepared=[])
    list(OBJECT_OT_polygroups_batch_finalization.steps(worker, ctx))
    names = [obj.name for obj in bpy.data.objects]
    assert 'SM_Rock_07_03_MID' in names, names
    assert 'Retopo_02_Highpoly_Generated.001' in names
    stages.mark_prepared_assets(ctx, worker.prepared, lambda *_: None)
    assets = phase2_scope.SCOPE['assets']
    assert assets and all('03' in name for name in assets), assets
    for name in assets:
        assert bpy.data.collections[name].color_tag == 'COLOR_05'
    print('DO_SELECTED_SCOPE_AND_INDEX_OK')
    phase2_scope.clear()

    # 5. Export Blend writes the failed (marked) Generated.005 too and keeps it for manual work.
    p.phase2_blend_export_generated = p.phase2_blend_delete_generated = True
    run = SimpleNamespace(settings=p, plan=[])
    list(stages.export_blend(run, ctx))
    folder = Path(directory) / '!Blend'
    assert (folder / 'Generated.005.blend').is_file(), sorted(item.name for item in folder.iterdir())
    assert 'Generated.005' in bpy.data.collections
    print('FAILED_GENERATED_EXPORTED_OK')
