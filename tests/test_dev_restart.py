"""Verify recovery-copy saving and scoped cleanup without closing Blender."""
from pathlib import Path
import sys
import tempfile
import bpy
import addon_utils

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)
from polygroups_generator.operators import dev_restart

with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    source = directory / 'source.blend'
    copy = directory / 'restart_test.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(source))
    original = source.read_bytes()
    bpy.context.active_object.location.x = 42
    bpy.ops.wm.save_as_mainfile(filepath=str(copy), copy=True, relative_remap=True, check_existing=False)
    assert bpy.data.filepath == str(source)
    assert source.read_bytes() == original
    bpy.ops.wm.open_mainfile(filepath=str(copy))
    assert bpy.context.active_object.location.x == 42
    dev_restart.restart_directory = lambda: directory
    (directory / 'restart_old.blend').write_bytes(b'old')
    (directory / 'unrelated.txt').write_text('keep')
    assert dev_restart.cleanup_copies(str(copy)) == 1
    assert source.exists() and copy.exists() and (directory / 'unrelated.txt').exists()
print('DEV RECOVERY COPY AND CLEANUP PASSED')
