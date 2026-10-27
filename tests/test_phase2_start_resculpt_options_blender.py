"""Start Phase 2 master switch forwards its resculpting options to the queue."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator.operators import phase2_pipeline_stages as stages
from polygroups_generator.operators import phase2_processing as phase

context = bpy.context
p = context.scene.polygroups_model_preparation_settings
assert all(getattr(p, name) for name in (
    'phase2_run_resculpt_retopo01', 'phase2_run_high_remesh',
    'phase2_run_repair_resculpt', 'phase2_run_bake_resculpt'))
p.phase2_show_start = True
panel = capture(context, 1)
assert not panel.errors, panel.errors
properties = {binding[2] for binding in panel.bindings.values() if binding[0] == 'property'}
assert {'phase2_run_resculpt_retopo01', 'phase2_run_high_remesh',
        'phase2_run_repair_resculpt', 'phase2_run_bake_resculpt'} <= properties


class Queue:
    def __init__(self, _context, _entries, auto_bake, _repair, _report):
        self.auto_bake = auto_bake
        self.finished = False
        self.index = 0
        self.stage = 'RESTORE'
        self.results = []

    def begin(self):
        self.settings_at_start = {name: getattr(p, name) for name in (
            'phase2_auto_bake', 'phase2_mesh_auto_repair', 'phase2_repack_after_repair',
            'phase2_resculpt_retopo01', 'phase2_high_remesh_before_resculpting',
            'phase2_repair_after_resculpt', 'phase2_autobake_retopo01')}

    def step(self, _context):
        self.finished = True
        self.index = 1
        self.results = [(('mock.blend', 'Generated.001'), '')]

    def finish(self, stopped=False):
        self.finished = True


def run(mode, master, high=True, repair=True, bake=True):
    p.phase2_run_mode = mode
    p.phase2_run_resculpt_retopo01 = master
    p.phase2_run_high_remesh = high
    p.phase2_run_repair_resculpt = repair
    p.phase2_run_bake_resculpt = bake
    p.phase2_clear_generated = False
    runner = SimpleNamespace(settings=p, report=lambda *_: None,
                             override=lambda owner, name, value: setattr(owner, name, value),
                             detail=lambda *_: None)
    queues = []

    def make_queue(*args):
        queue = Queue(*args)
        queues.append(queue)
        return queue

    with patch.object(phase, 'scan', return_value=[('mock.blend', 'Generated.001')]), \
         patch.object(phase, 'Phase2Queue', side_effect=make_queue):
        list(stages.restore(runner, context))
    return queues[0]


queue = run('RESCULPT', True)
assert queue.auto_bake
assert all(queue.settings_at_start.values()), queue.settings_at_start
queue = run('REBAKE', True, high=False, repair=True, bake=False)
assert queue.settings_at_start['phase2_resculpt_retopo01']
assert not queue.settings_at_start['phase2_high_remesh_before_resculpting']
assert queue.settings_at_start['phase2_repair_after_resculpt']
assert not queue.settings_at_start['phase2_autobake_retopo01']
queue = run('REBAKE', False)
assert queue.auto_bake and not queue.settings_at_start['phase2_resculpt_retopo01']
assert not any(queue.settings_at_start[name] for name in (
    'phase2_high_remesh_before_resculpting', 'phase2_repair_after_resculpt',
    'phase2_autobake_retopo01'))
queue = run('IMPORT', True)
assert not queue.auto_bake and not any(queue.settings_at_start.values())
print('PHASE2_START_RESCULPT_OPTIONS_OK', flush=True)
