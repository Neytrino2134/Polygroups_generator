"""Unity panel loading plus real popup RNA callbacks; run in a factory GUI process."""
from pathlib import Path
from tempfile import mkdtemp
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
from polygroups_generator.operators import unity_export_workflow as workflow
from polygroups_generator.custom_ui.schema import capture

assert workflow.unity_name_from_filepath('Tree_With_Name_16_01.blend') == ('Tree_With_Name', '16', '01')
assert workflow.unity_name_from_filepath('Tree_16_A_09.blend') == ('Tree', '16', 'A_09')
assert workflow.unity_name_from_filepath('Tree.blend') == ('Tree', '00', '01')
assert workflow.unity_name_from_filepath('Tree_16_01.LOD2.blend') == ('Tree', '16', '01')
assert workflow.step_naming_index('99', 1, True) == '99'
assert workflow.step_naming_index('00', -1, True) == '00'
assert workflow.step_naming_index('A_09', 1) == 'A_10'

captured = []
cls = workflow.OBJECT_OT_polygroups_prepare_and_export_unity
original_invoke = cls.invoke
def invoke(self, context, event):
    captured.append(self)
    return original_invoke(self, context, event)
cls.invoke = invoke
addon_utils.enable(ROOT.name, default_set=True)
directory = Path(mkdtemp(prefix='airetopo-unity-name-'))
bpy.ops.wm.save_as_mainfile(filepath=str(directory/'Tree_With_Name_16_A_09.blend'))
settings = bpy.context.scene.polygroups_mesh_finalization_settings
assert bpy.ops.object.polygroups_unity_load_from_file() == {'FINISHED'}
assert (settings.unity_asset_name, settings.unity_name_index, settings.unity_asset_index) == ('Tree_With_Name', '16', 'A_09')
model = capture(bpy.context, 11)
assert not model.errors, model.errors
assert sum(b[0] == 'operator' and b[1] == 'object.polygroups_unity_load_from_file' for b in model.bindings.values()) == 2


def verify_dialog():
    op = captured[-1]
    op.asset_name, op.name_index, op.version_index = 'Changed', '00', '01'
    op.load_from_file = True
    assert not op.load_from_file
    assert (op.asset_name, op.name_index, op.version_index) == ('Tree_With_Name', '16', 'A_09')
    assert (settings.unity_asset_name, settings.unity_name_index, settings.unity_asset_index) == ('Tree_With_Name', '16', 'A_09')
    op.name_index_increase = True
    assert op.name_index == '17' and not op.name_index_increase
    assert settings.unity_name_index == '16', 'Popup edits must remain local until Start'
    op.name_index_decrease = True
    assert op.name_index == '16' and not op.name_index_decrease
    op.version_index_increase = True
    assert op.version_index == 'A_10' and not op.version_index_increase
    op.version_index_decrease = True
    assert op.version_index == 'A_09' and not op.version_index_decrease
    op.name_index = '00'
    op.name_index_decrease = True
    assert op.name_index == '00'
    op.name_index = '99'
    op.name_index_increase = True
    assert op.name_index == '99'
    op.load_from_file = True
    def screenshot():
        bpy.ops.screen.screenshot(filepath=str(directory/'unity-name-dialog.png'))
        print('UNITY_FILENAME_CONTROLS_TESTS_PASSED', directory)
        bpy.ops.wm.quit_blender()
    bpy.app.timers.register(screenshot, first_interval=.5)


def open_dialog():
    assert bpy.ops.object.polygroups_prepare_and_export_unity('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    bpy.app.timers.register(verify_dialog, first_interval=.5)


bpy.app.timers.register(open_dialog, first_interval=1)
