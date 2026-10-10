"""Structured naming, narrow draw layout, nested destination and restart dispatch."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators import relocate_project as rp

assert bpy.ops.wm.airetopo_relocate_project.get_rna_type().properties['put_in_subfolder'].default is True

assert rp.split_project_name('Tree_16_01') == ('Tree', '16', '01')
assert rp.split_project_name('Tree_With_Underscores_03_12') == ('Tree_With_Underscores', '03', '12')
assert rp.split_project_name('Tree') == ('Tree', '00', '01')
assert rp.indexed_project_name('Tree', '6', '2') == 'Tree_06_02'
assert rp.indexed_project_name('Tree.blend', '16', '01') == 'Tree_16_01'
for fields in [('', '00', '01'), ('../Tree', '00', '01'), ('Tree', 'x', '01'), ('Tree', '00', '-1')]:
    try:
        rp.indexed_project_name(*fields)
    except RuntimeError:
        pass
    else:
        raise AssertionError(fields)


class DrawLayout:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
    def box(self):
        return DrawLayout(self.calls)
    def column(self, **kwargs):
        return DrawLayout(self.calls)
    def row(self, **kwargs):
        return DrawLayout(self.calls)
    def operator(self, name, **kwargs):
        self.calls.append(('operator', dict(operator=name, **kwargs)))
        return SimpleNamespace()
    def label(self, **kwargs):
        self.calls.append(('label', kwargs))
    def prop(self, owner, name, **kwargs):
        self.calls.append(('prop', dict(property=name, **kwargs)))


prefs = bpy.context.preferences.addons[ROOT.name].preferences
for language in ('EN', 'RU'):
    prefs.interface_language = language
    for nested in (False, True):
        layout = DrawLayout()
        op = SimpleNamespace(layout=layout, project_name='Tree', name_index='16', version_index='01', put_in_subfolder=nested)
        rp.WM_OT_airetopo_relocate_project.draw(op, bpy.context)
        assert any(kind == 'label' and data.get('icon') == 'FILE_TICK' for kind, data in layout.calls)
        for prop in ('project_name', 'name_index', 'version_index'):
            index = next(i for i, (kind, data) in enumerate(layout.calls) if kind == 'prop' and data['property'] == prop)
            assert layout.calls[index][1]['text'] == ''
            prior = index-1 if prop == 'project_name' else index-2
            assert layout.calls[prior][0] == 'label' and layout.calls[prior][1]['text']
        arrows = [data['icon'] for kind, data in layout.calls if kind == 'operator']
        assert arrows == ['TRIA_LEFT', 'TRIA_RIGHT', 'TRIA_LEFT', 'TRIA_RIGHT']
        assert any(kind == 'label' and data['text'] == 'Tree_16_01.blend' for kind, data in layout.calls)
        assert any(kind == 'label' and data['text'] == 'Tree_16_01_Main_Folder/' for kind, data in layout.calls) == nested

with TemporaryDirectory() as directory:
    root = Path(directory)
    original = root/'Tree_16_01.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(original))
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    selector = []
    op = SimpleNamespace()
    context = SimpleNamespace(window_manager=SimpleNamespace(fileselect_add=selector.append))
    assert rp.WM_OT_airetopo_relocate_project.invoke(op, context, None) == {'RUNNING_MODAL'}
    assert (op.project_name, op.name_index, op.version_index) == ('Tree', '16', '01')
    assert selector == [op]

    parent = root/'Existing destination'
    parent.mkdir()
    (parent/'keep.txt').write_text('untouched')
    reports = []
    op = SimpleNamespace(directory=str(parent), project_name='Tree', name_index='16', version_index='02',
        put_in_subfolder=True, report=lambda *args: reports.append(args))
    with patch.object(rp, '_execute_restart', return_value={'FINISHED'}) as restart:
        assert rp.WM_OT_airetopo_relocate_project.execute(op, bpy.context) == {'FINISHED'}
        restart.assert_called_once_with(op, bpy.context, False, use_saved_current=True)
    expected = parent/'Tree_16_02_Main_Folder'/'Tree_16_02.blend'
    assert Path(bpy.data.filepath) == expected and expected.is_file()
    assert (parent/'keep.txt').read_text() == 'untouched'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    saved_digest = hashlib.sha256(expected.read_bytes()).hexdigest()
    try:
        rp.relocate_project(str(parent), 'Tree_16_02', put_in_subfolder=True)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Occupied destination was overwritten')
    assert hashlib.sha256(expected.read_bytes()).hexdigest() == saved_digest
print('PROJECT_RELOCATION_NAMING_TESTS_PASSED')
