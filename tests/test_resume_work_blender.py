"""Resume Work: skip as many folder files as the open blend holds Generated.N collections."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import batch_import

files = [f'D:/pack/{index:02d}.fbx' for index in range(1, 28)]


def add(*numbers):
    for number in numbers:
        bpy.context.scene.collection.children.link(bpy.data.collections.new(f'Generated.{number:03d}'))


try:
    batch_import.resume_files(files)
    raise AssertionError('empty file has nothing to resume')
except RuntimeError as error:
    assert 'nothing to resume' in str(error)

add(*range(1, 18))
assert batch_import.completed_generated_count() == (17, [])
done, rest = batch_import.resume_files(files)
assert done == 17 and rest == files[17:] and rest[0].endswith('18.fbx') and len(rest) == 10

# A hole in the numbering would be reused by the next import and break the file order.
bpy.data.collections.remove(bpy.data.collections['Generated.005'])
assert batch_import.completed_generated_count() == (17, [5])
try:
    batch_import.resume_files(files)
    raise AssertionError('gap must be refused')
except RuntimeError as error:
    assert 'Generated.005' in str(error)
add(5)
add(*range(18, 28))
try:
    batch_import.resume_files(files)
    raise AssertionError('everything is imported')
except RuntimeError as error:
    assert 'already imported' in str(error)
assert 'resume_work' in bpy.ops.object.polygroups_batch_import.get_rna_type().properties.keys()
print('resume work ok')
