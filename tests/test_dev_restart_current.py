from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
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
    saved_bytes = source.read_bytes()
    bpy.context.active_object.location.x = 456
    with patch.object(dev_restart.subprocess, 'Popen') as launch, patch.object(bpy.app.timers, 'register'), patch.object(dev_restart, 'restart_directory', return_value=Path(directory)):
        result = dev_restart.WM_OT_airetopo_dev_restart_without_saving.execute(Runner(), bpy.context)
        assert result == {'FINISHED'}
        assert launch.call_args.args[0][1] == str(source)
        assert source.read_bytes() == saved_bytes
    bpy.ops.wm.open_mainfile(filepath=str(source))
    assert bpy.context.active_object.location.x == 123
bpy.ops.wm.read_factory_settings(use_empty=True)
empty_context = SimpleNamespace(
    scene=SimpleNamespace(
        polygroups_model_preparation_settings=SimpleNamespace(batch_is_running=False),
        polygroups_remesh_status=SimpleNamespace(is_running=False),
    ),
    object=None,
    objects_in_mode=(),
)
with tempfile.TemporaryDirectory() as directory:
    restart_root = Path(directory)
    with patch.object(dev_restart.subprocess, 'Popen') as launch, patch.object(bpy.app.timers, 'register'), patch.object(dev_restart, 'restart_directory', return_value=restart_root):
        result = dev_restart.WM_OT_airetopo_dev_restart_current.execute(Runner(), empty_context)
        assert result == {'FINISHED'}
        temporary_file = Path(bpy.data.filepath)
        assert temporary_file.parent == restart_root
        assert temporary_file.name.startswith('restart_')
        assert temporary_file.suffix == '.blend'
        assert temporary_file.is_file()
        assert launch.call_args.args[0][1] == str(temporary_file)

bpy.ops.wm.read_factory_settings(use_empty=True)
with tempfile.TemporaryDirectory() as directory:
    with patch.object(dev_restart.subprocess, 'Popen') as launch, patch.object(bpy.app.timers, 'register'), patch.object(dev_restart, 'restart_directory', return_value=Path(directory)):
        result = dev_restart.WM_OT_airetopo_dev_restart_without_saving.execute(Runner(), empty_context)
        assert result == {'FINISHED'}
        assert not bpy.data.filepath
        command = launch.call_args.args[0]
        assert command[0] == bpy.app.binary_path
        assert command[1] == '--python-expr'
print('CURRENT FILE RESTART PASSED')
