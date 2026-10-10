"""Factory GUI acceptance: open the folder picker and capture its actual sidebar."""
from pathlib import Path
import sys
import tempfile
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
OUT = Path(tempfile.gettempdir())/'airetopo-relocation-dialog.png'
attempts = 0


def capture_dialog():
    global attempts
    attempts += 1
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'FILE_BROWSER':
                continue
            space = area.spaces.active
            op = space.active_operator
            if op is None:
                continue
            op.project_name = 'Tree'
            op.name_index = '16'
            op.version_index = '01'
            op.put_in_subfolder = True
            with bpy.context.temp_override(window=window, area=area):
                for field in ('name_index', 'version_index'):
                    for initial, delta, expected in (('00', -1, '00'), ('09', 1, '10'),
                            ('99', 1, '100'), ('100', -1, '099'), ('001', 1, '002'), ('', 1, '01')):
                        setattr(op, field, initial)
                        assert bpy.ops.wm.airetopo_relocate_index_step(field=field, delta=delta) == {'FINISHED'}
                        assert getattr(op, field) == expected, (field, initial, delta, getattr(op, field))
                op.name_index, op.version_index = '16', '01'
            area.tag_redraw()
            def screenshot():
                with bpy.context.temp_override(window=window, area=area):
                    bpy.ops.screen.screenshot(filepath=str(OUT))
                    bpy.ops.file.cancel()
                print('PROJECT_RELOCATION_DIALOG_UI_PASSED', OUT)
                bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=.5)
            bpy.app.timers.register(screenshot, first_interval=.5)
            return None
    if attempts > 10:
        print('PROJECT_RELOCATION_DIALOG_UI_FAILED')
        bpy.ops.wm.quit_blender()
        return None
    return .5


def open_dialog():
    assert bpy.ops.wm.airetopo_relocate_project('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    bpy.app.timers.register(capture_dialog, first_interval=1)


bpy.app.timers.register(open_dialog, first_interval=1)
