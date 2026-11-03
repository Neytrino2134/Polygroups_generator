"""Import manifest and Resume Work planning: folder order, statuses, collection / file cross-check."""
import os
import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import import_manifest as manifests
from polygroups_generator.operators import batch_import

with tempfile.TemporaryDirectory() as folder:
    work = Path(folder) / 'work'
    pack = Path(folder) / 'pack'
    work.mkdir()
    # Folders are numbered; the file names inside them say nothing about the order.
    for number, name in ((10, 'a.glb'), (2, 'zzz.glb'), (1, 'm.glb'), (3, 'b.glb')):
        (pack / str(number)).mkdir(parents=True)
        (pack / str(number) / name).write_bytes(b'x')
    blend = str(work / 'Statues.blend')
    files = batch_import.collect_import_files(str(pack), 'AUTO', True)
    assert [Path(p).parent.name for p in files] == ['1', '2', '3', '10'], files

    manifest = manifests.ImportManifest.build(blend, str(pack), files)
    assert [e['index'] for e in manifest.entries] == [1, 2, 3, 4]
    assert [e['folder'] for e in manifest.entries] == ['1', '2', '3', '10']
    assert manifest.entries[0]['file'] == '../pack/1/m.glb', manifest.entries[0]['file']
    assert all(e['status'] == 'pending' for e in manifest.entries)

    # Files 1 and 2 are completed, 3 was in process when Blender stopped, 4 has no record yet.
    manifest.update(files[0], status='completed', collection='Generated.001')
    manifest.update(files[1], status='completed', collection='Generated.002')
    manifest.update(files[2], status='in_progress', collection='Generated.003')
    assert os.path.basename(manifest.path) == 'Statues_import_manifest.json'
    loaded = manifests.ImportManifest.load(blend)
    assert [e['status'] for e in loaded.entries] == ['completed', 'completed', 'in_progress', 'pending']
    assert manifests.cached_counts(blend) == {'completed': 2, 'in_progress': 1, 'pending': 1}

    # The open blend and the separate files agree: continue with the file in process, from its start.
    plan = manifests.plan_resume(loaded, files, {1, 2, 3}, {1, 2, 3})
    assert plan.done == 2 and plan.files == files[2:] and plan.wipe == ['Generated.003'], vars(plan)

    # Generated.002 collection exists but its saved file is gone: that file is imported again as well.
    plan = manifests.plan_resume(loaded, files, {1, 2}, {1})
    assert plan.files == files[1:] and plan.wipe == ['Generated.002'] and plan.done == 1, vars(plan)
    assert any('Generated_002.blend' in note for note in plan.notes), plan.notes

    # Collection removed by hand: only that file restarts, nothing to wipe.
    plan = manifests.plan_resume(loaded, files, {1}, {1, 2})
    assert plan.files == files[1:] and plan.wipe == [] and 'Generated.002 collection' in plan.notes[0]

    # Without separate files only the collections count; a failed file is done (it is marked, not retried).
    loaded.entries[2].update(status='failed', collection='Generated.003')
    plan = manifests.plan_resume(loaded, files, {1, 2, 3}, set())
    assert plan.files == files[3:] and plan.done == 3

    # A rebuilt manifest keeps the statuses; a file added to the folder is appended as pending.
    (pack / '11').mkdir()
    (pack / '11' / 'new.glb').write_bytes(b'x')
    more = batch_import.collect_import_files(str(pack), 'AUTO', True)
    rebuilt = manifests.ImportManifest.build(blend, str(pack), more, loaded)
    assert [e['status'] for e in rebuilt.entries] == ['completed', 'completed', 'failed', 'pending', 'pending']
    assert manifests.ImportManifest.load(str(work / 'Other.blend')) is None
print('import manifest ok')
