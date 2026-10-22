"""Start Import headings are real nested folds used by +/- commands."""
from pathlib import Path
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.ui_folds import section_folds, step_folds
from polygroups_generator.custom_ui.schema import capture, walk

context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
names = {'show_batch_start_autosave', 'show_batch_start_mode'}
for language in ('EN', 'RU'):
    context.preferences.addons[ROOT.name].preferences.interface_language = language
    model = capture(context, 1)
    assert not model.errors, model.errors
    start = next(n for n in walk(model.node) if n['kind'] == 'group' and n['id'].endswith('.topic_batch_3'))
    descendants = {n['id'] for n in walk(start)}
    for name in names:
        assert any(key in descendants and b[0] == 'property' and b[2] == name
                   for key, b in model.bindings.items())
    roots = section_folds(context, 1, include_sections=False)
    run = next(fold for fold in roots if fold.name == 'topic_batch_3')
    assert {fold.name for fold in run.children} == names
    run.set(False)
    run.close_children()
    assert step_folds([run], True) == 1
    assert run.opened() and not any(getattr(settings, name) for name in names)
    assert step_folds([run], True) == 2
    assert all(getattr(settings, name) for name in names)
    assert step_folds([run], False) == 2
    assert run.opened() and not any(getattr(settings, name) for name in names)
    assert step_folds([run], False) == 1 and not run.opened()
    # The actual section header commands use the same model-derived nesting.
    for root in roots:
        root.set(False)
        root.close_children()
    op = bpy.ops.object.airetopo_set_section_subsection_visibility
    assert op(section_property='show_batch_import_section', visible=True) == {'FINISHED'}
    assert run.opened() and not any(getattr(settings, name) for name in names)
    assert op(section_property='show_batch_import_section', visible=True) == {'FINISHED'}
    assert all(getattr(settings, name) for name in names)
    assert op(section_property='show_batch_import_section', visible=False) == {'FINISHED'}
    assert run.opened() and not any(getattr(settings, name) for name in names)
print('BATCH_START_FOLDS_PASSED')
