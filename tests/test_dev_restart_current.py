from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import bpy
import addon_utils
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)
from polygroups_generator.operators import dev_restart

class Runner:
    save_current = True
    report = lambda self, level, message: None

with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'current.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(source))
    bpy.context.active_object.location.x = 123
    with patch.object(dev_restart.subprocess, 'Popen') as launch, patch.object(bpy.app.timers, 'register'), patch.object(dev_restart, 'restart_directory', return_value=Path(directory)):
        result = dev_restart.WM_OT_airetopo_dev_restart.execute(Runner(), bpy.context)
        assert result == {'FINISHED'}
        assert launch.call_args.args[0][1] == str(source)
        assert bpy.data.filepath == str(source)
        assert not list(Path(directory).glob('restart_*.blend'))
    dev_restart.WM_OT_airetopo_dev_restart._pending = False
    bpy.ops.wm.open_mainfile(filepath=str(source))
    assert bpy.context.active_object.location.x == 123
bpy.ops.wm.read_factory_settings(use_empty=True)
assert dev_restart.WM_OT_airetopo_dev_restart.execute(Runner(), bpy.context) == {'CANCELLED'}
print('CURRENT FILE RESTART PASSED')
