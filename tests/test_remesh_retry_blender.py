"""A failed Quad Remesher pass is repeated once with Quad Count +50%; a second failure goes the usual way."""
import sys
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.import_queue import ImportQueue

settings = bpy.context.scene.polygroups_model_preparation_settings
assert settings.batch_remesh_retry_enabled and settings.batch_remesh_retry_percent == 50

bpy.ops.mesh.primitive_cube_add()
source = bpy.context.object
source.hide_viewport = True


class Job:
    aborted = 0

    def abort(self):
        Job.aborted += 1


def queue(stage='WAIT_REMESH', pass_number=3, count=3000):
    q = ImportQueue.__new__(ImportQueue)
    q.settings = settings
    q.stage, q.pass_method, q.pass_number, q.pass_quad_count = stage, 'QUAD', pass_number, count
    q.index, q.mesh_index, q.pass_sources = 0, 0, [source]
    q.job = Job()
    q.file_record = {}
    q.events, q.messages = [], []
    q.write_batch_report = lambda event, data: q.events.append((event, data))
    q.report = lambda kind, text: q.messages.append(text)
    return q


settings.batch_current_file = 'statue.glb'
q = queue()
assert q.retry_remesh(RuntimeError('Quad Remesher did not report progress within 40 seconds'))
assert q.stage == 'REMESH' and q.job is None and Job.aborted == 1 and q.remesh_count_override == 4500
assert not source.hide_viewport
assert q.file_record['retries'][0]['retry_quad_count'] == 4500 and q.events[0][0] == 'remesh_retry'
assert '4500' in q.messages[0] and 'pass 3' in q.messages[0]
# The same pass of the same mesh gets only one retry.
q.stage, q.job = 'WAIT_REMESH', Job()
assert not q.retry_remesh(RuntimeError('Quad Remesher failed (1)'))
# Another pass retries on its own, from its own configured count.
q.pass_number, q.pass_quad_count, q.remesh_count_override = 4, 2000, None
q.stage = 'REMESH'
assert q.retry_remesh(RuntimeError('boom')) and q.remesh_count_override == 3000
# Not retried: other stages, a finished remesh, voxel passes, setup errors, the switch.
for change in (dict(stage='UNWRAP_PASS'), dict(pass_method='VOXEL'), dict(remesh_output_ready=True)):
    other = queue(pass_number=2)
    for name, value in change.items():
        setattr(other, name, value)
    assert not other.retry_remesh(RuntimeError('Quad Remesher failed (1)')), change
assert not queue(pass_number=2).retry_remesh(RuntimeError('Quad Remesher is not available'))
settings.batch_remesh_retry_enabled = False
assert not queue(pass_number=2).retry_remesh(RuntimeError('Quad Remesher failed (1)'))
settings.batch_remesh_retry_enabled = True
settings.batch_remesh_retry_percent = 100
assert queue(pass_number=2).retry_remesh(RuntimeError('x')) is True
print('remesh retry ok')
