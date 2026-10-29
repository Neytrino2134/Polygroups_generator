"""Resume Selected: continue Phase 1 after the remesh pass the selected Retopo mesh finished."""
import sys
from pathlib import Path

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import import_queue  # noqa: E402
from polygroups_generator.operators.queue_storage import resume_state  # noqa: E402

ctx = bpy.context
settings = ctx.scene.polygroups_model_preparation_settings
for name in ('batch_stage_2_enabled', 'batch_stage_3_enabled', 'batch_stage_4_enabled',
             'batch_narrow_island_enabled', 'batch_second_narrow_island_enabled'):
    setattr(settings, name, True)


def mesh(collection, name):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    return obj


def select(obj):
    for item in ctx.selected_objects:
        item.select_set(False)
    obj.select_set(True)
    ctx.view_layer.objects.active = obj


col = bpy.data.collections.new('Generated.008')
ctx.scene.collection.children.link(col)
high = mesh(col, 'Highpoly_Generated.008')
first = mesh(col, 'Retopo_Highpoly_Generated.008')
second = mesh(col, 'Retopo_02_Highpoly_Generated.008')
third = mesh(col, 'Retopo_03_Highpoly_Generated.008')
first_numbered = mesh(col, 'Retopo_01_Highpoly_Generated.008')
other = bpy.data.collections.new('Other')
ctx.scene.collection.children.link(other)
stray = mesh(other, 'Retopo_Highpoly_Generated.008')   # name matches, collection has no highpoly

# Classification: Retopo_ and Retopo_01 = first pass, 02 = second, 03 = finished.
select(high);  assert resume_state(ctx) is None
select(first); state = resume_state(ctx)
assert state['level'] == 1 and not state['finished'] and state['collection'] == col
select(first_numbered); assert resume_state(ctx)['level'] == 1
select(second); assert resume_state(ctx)['level'] == 2 and not resume_state(ctx)['finished']
select(third); assert resume_state(ctx)['finished']
select(stray); assert resume_state(ctx) is None

# Finished (Retopo_03) is refused, even when Phase 2 is enabled.
settings.batch_phase2_enabled = True
select(third)
assert bpy.ops.object.polygroups_batch_import('EXEC_DEFAULT', use_file_selection=False,
                                              resume_selected=True) == {'CANCELLED'}
select(high)   # not a Retopo mesh: an error is reported
try:
    bpy.ops.object.polygroups_batch_import('EXEC_DEFAULT', use_file_selection=False, resume_selected=True)
    raise AssertionError('Highpoly accepted')
except RuntimeError:
    pass


def prepared(obj):
    select(obj)
    info = resume_state(ctx)
    queue = import_queue.ImportQueue(ctx, [col.name], False, lambda *args: None,
                                     redo_collection=col, resume=info)
    queue.file_record = {}
    queue.prepare_resume(ctx)
    return queue


# Retopo_ / Retopo_01 resume at 3. Narrow Island Splitter and still run passes 5 and 8.
queue = prepared(first)
assert queue.stage == 'NARROW_SPLIT' and [p[0] for p in queue.passes] == [3, 4], (queue.stage, queue.passes)
assert queue.pass_sources == [first] and not queue.second_cleanup_done
assert second.name.startswith('__PolygroupsRedoBackup') and third.name.startswith('__PolygroupsRedoBackup')
queue.restore_redo_backup()
assert second.name == 'Retopo_02_Highpoly_Generated.008'
# Retopo_02 resumes at 6. Narrow Island Splitter and only runs pass 8; later results are rebuilt.
queue = prepared(second)
assert queue.stage == 'SECOND_NARROW_SPLIT' and [p[0] for p in queue.passes] == [4], (queue.stage, queue.passes)
assert queue.second_cleanup_done and queue.pass_sources == [second]
assert third.name.startswith('__PolygroupsRedoBackup') and second.name == 'Retopo_02_Highpoly_Generated.008'
queue.restore_redo_backup()
assert third.name == 'Retopo_03_Highpoly_Generated.008'

# After the last remesh pass the run ends at stage 8: no packing, bake or finalization, no Phase 2.
queue = prepared(second)
queue.pass_index = len(queue.passes)
queue.stage = 'PASS_SETUP'
queue.advance(ctx)
assert queue.stage == 'COMPLETE', queue.stage
print('resume selected ok')
