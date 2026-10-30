"""Every Phase 2 fix runs on the right mesh, in order, for both start presets.

Unreal: MID source and MID result each get loose parts, Auto Repair, Topology
Guard, Smart UV Repair and a final Auto Repair. Unreal + ZBrush additionally
fixes Retopo_01 and its HIGH remesh before Setup Resculpting; Smart UV Repair
there needs the Resculpting_01 rebake, and Topology Guard then runs only on
the HIGH result (Retopo_01 is never guarded).
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_processing as phase, phase2_mid_remesh, small_loose_parts
from polygroups_generator.operators.phase2_start_dialog import apply_start_preset

context = bpy.context
p = context.scene.polygroups_model_preparation_settings
bake = context.scene.polygroups_baking_settings
events = []
# Topology Guard is always followed by a UVPackmaster PACK.
FIX = ['loose', 'repair', 'guard', 'pack', 'uv', 'repair']


def fixture():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    col = bpy.data.collections.new('Generated.777')
    context.scene.collection.children.link(col)
    for name in ('Highpoly_Generated.777', 'Retopo_01_Highpoly_Generated.777',
                 'Retopo_12_Highpoly_Generated.777'):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        mesh.uv_layers.new()
        col.objects.link(bpy.data.objects.new(name, mesh))
    context.view_layer.update()
    return col


class FakeRemesh:
    def __init__(self, _context, owner, _report, source=None, preset='MID', result_name=None):
        self.owner, self.preset = owner, preset
        self.source = source or bpy.data.objects['Retopo_12_Highpoly_Generated.777']
        self.name = result_name or 'Retopo_13_Highpoly_Generated.777'
        self.job = SimpleNamespace(pipeline_progress=0)

    def start(self, _context):
        events.append(('remesh ' + self.preset, self.source.name))

    def poll(self):
        return True, 1.0

    def finish(self, _context):
        result = self.source.copy()
        result.data = self.source.data.copy()
        result.name = self.name
        self.owner.objects.link(result)
        return result

    def abort(self):
        pass


def record(kind):
    def operator(*_args, **_kwargs):
        events.append((kind, context.active_object.name))
        if kind == 'bake':
            bake.bake_task_is_running = False
            bake.bake_task_stage = 'DONE'
        return {'FINISHED'}
    return operator


def guard(_context, obj, *_args, **_kwargs):
    events.append(('guard', obj.name))
    return SimpleNamespace(timed_out=False, knots=0), 0, 0


def loose(obj, **_kwargs):
    events.append(('loose', obj.name))
    return {'part_count': 0}


proxy = SimpleNamespace(data=bpy.data, ops=SimpleNamespace(
    mesh=SimpleNamespace(polygroups_repair_mesh_folds=record('repair'),
                         polygroups_repair_uv_stretch=record('uv'),
                         select_all=lambda **_kwargs: {'FINISHED'}),
    object=SimpleNamespace(mode_set=lambda **_kwargs: {'FINISHED'},
                           polygroups_uvpackmaster_pack=record('pack'),
                           polygroups_setup_resculpting=record('sculpt'),
                           polygroups_checked_prepare_and_bake=record('bake'))))


def run(preset, rebake=True):
    apply_start_preset(p, preset)
    if preset == 'UNREAL_ZBRUSH':
        p.phase2_run_skip_rebake = not rebake
    # Mirror the Start Phase 2 restore overrides (no pipeline wrapper here).
    p.phase2_mid_remesh = True
    p.phase2_resculpt_retopo01 = p.phase2_high_remesh_before_resculpting = preset == 'UNREAL_ZBRUSH'
    p.phase2_keep_retopo01 = True
    col = fixture()
    events.clear()
    queue = phase.Phase2Queue(context, [('mock.blend', col.name)], True, True, lambda *_: None)
    queue.begin()
    with patch.object(phase, 'restore_collection', return_value=col), \
         patch.object(phase2_mid_remesh, 'Phase2MidRemesh', FakeRemesh), \
         patch.object(small_loose_parts, 'remove_small_loose_parts', loose), \
         patch.object(phase, 'apply_topology_guard', guard), \
         patch.object(phase, 'bpy', proxy):
        for _ in range(30):
            queue.step(context)
            if queue.finished:
                break
    assert queue.finished and queue.results[-1][1] == '', queue.results
    return [(kind, name.split('_Highpoly')[0]) for kind, name in events]


def fixes(name, kinds=FIX):
    return [(kind, name) for kind in kinds]


unreal = run('UNREAL')
assert unreal == (fixes('Retopo_12') + [('remesh MID', 'Retopo_12')] + fixes('Retopo_13')
                  + [('pack', 'Retopo_13'), ('bake', 'Retopo_13')]), unreal

zbrush = run('UNREAL_ZBRUSH', rebake=True)
primary = fixes('Retopo_12') + [('remesh MID', 'Retopo_12')] + fixes('Retopo_13') + [
    ('pack', 'Retopo_13'), ('bake', 'Retopo_13')]
assert zbrush == primary + fixes('Retopo_01', ['loose', 'repair', 'uv', 'repair']) + [
    ('remesh HIGH', 'Retopo_01')] + fixes('Resculpting_01') + [
    ('sculpt', 'Resculpting_01'), ('repair', 'Resculpting_01'),
    ('pack', 'Resculpting_01'), ('bake', 'Resculpting_01')], zbrush

no_rebake = run('UNREAL_ZBRUSH', rebake=False)
assert no_rebake == primary + fixes('Retopo_01', ['loose', 'repair']) + [
    ('remesh HIGH', 'Retopo_01')] + fixes('Resculpting_01', ['loose', 'repair']) + [
    ('sculpt', 'Resculpting_01'), ('repair', 'Resculpting_01'), ('pack', 'Resculpting_01')], no_rebake
print('PHASE2_FIX_CHAIN_OK', flush=True)
