"""Autosave section lists every .blendAutosaveN and previous version .blendN of the open file."""
import sys
import tempfile
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator import custom_autosave as ca  # noqa: E402

assert ca.saved_versions('') == []
with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_versions_') as directory:
    base = Path(directory)
    work = base / 'Rock [1].blend'
    work.write_bytes(b'x')
    for name in ('Rock [1].blendAutosave1', 'Rock [1].blendAutosave3', 'Rock [1].blend1', 'Rock [1].blend2'):
        (base / name).write_bytes(b'data')
    (base / 'Rock [1].blendAutosave2').write_bytes(b'')       # empty files are ignored
    (base / 'Rock [1].blend.txt').write_bytes(b'data')
    (base / 'Other.blend1').write_bytes(b'data')
    entries = ca.saved_versions(str(work))
    assert [(e['kind'], e['number']) for e in entries] == [
        ('AUTOSAVE', 1), ('AUTOSAVE', 3), ('VERSION', 1), ('VERSION', 2)], entries
    # Recovery of a previous version keeps the original name, so it can be saved back.
    version = base / 'Rock [1].blend2'
    assert ca._original_path_for_autosave(version).name == 'Rock [1].blend'
    assert ca._original_path_for_autosave(base / 'Rock [1].blendAutosave3').name == 'Rock [1].blend'
    assert ca._restored_path_for_autosave(version).name.startswith('Rock [1]_restored_')
print('saved versions ok')
