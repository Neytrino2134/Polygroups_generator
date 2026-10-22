"""Failure cleanup and ownership tracking across the extracted queue mixin."""
from pathlib import Path
import sys
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.import_queue import ImportQueue
from polygroups_generator.operators import queue_processing

queue = ImportQueue.__new__(ImportQueue)
queue.scene = bpy.context.scene
queue.settings = queue.scene.polygroups_model_preparation_settings
for name in ('objects', 'collections', 'meshes', 'materials', 'images'):
    setattr(queue, 'owned_' + name, set())

unrelated = bpy.context.active_object
created = {}


def failed_action():
    created['mesh'] = bpy.data.meshes.new('Tracked mesh')
    created['object'] = bpy.data.objects.new('Tracked object', created['mesh'])
    created['collection'] = bpy.data.collections.new('Tracked collection')
    created['material'] = bpy.data.materials.new('Tracked material')
    created['image'] = bpy.data.images.new('Tracked image', width=2, height=2)
    raise RuntimeError('Injected action failure')


try:
    queue.tracked(failed_action)
except RuntimeError as error:
    assert str(error) == 'Injected action failure'
else:
    raise AssertionError('Action failure was swallowed')
for kind, plural in [('object', 'objects'), ('collection', 'collections'),
                     ('mesh', 'meshes'), ('material', 'materials'), ('image', 'images')]:
    assert getattr(queue, 'owned_' + plural) == {created[kind]}
assert unrelated not in queue.owned_objects and unrelated.name in bpy.data.objects

# An injected edit-mode failure must restore Object Mode and isolate shared data.
target = unrelated
other = target.copy()
bpy.context.scene.collection.objects.link(other)
shared = target.data
with patch.object(queue_processing, 'relax_seams', side_effect=RuntimeError('Injected relax failure')) as relax:
    try:
        queue.smart_relax_edges(bpy.context, target)
    except RuntimeError as error:
        assert str(error) == 'Injected relax failure'
    else:
        raise AssertionError('Relax failure was swallowed')
    assert relax.call_count == 1
assert bpy.context.mode == 'OBJECT' and bpy.context.active_object == target
assert other.data == shared and target.data != shared
assert target.data in queue.owned_meshes

addon_utils.disable(ROOT.name, default_set=False)
print('QUEUE_PROCESSING_BOUNDARY_PASSED')
