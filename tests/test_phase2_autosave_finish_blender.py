"""Autosave After Finish: on by default, saves when the pipeline completes or fails, never when stopped."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_pipeline as pipeline

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings
assert p.phase2_autosave and p.phase2_autosave_after_finish

saves = []
def fake_save(**kwargs):
    saves.append(kwargs['filepath'])
    return {'FINISHED'}
proxy = SimpleNamespace(data=SimpleNamespace(filepath='D:/work/a.blend'),
                        ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=fake_save)))
run = pipeline.Phase2Pipeline.__new__(pipeline.Phase2Pipeline)
run.settings = p
run.report = lambda *args: None
with patch.object(pipeline, 'bpy', SimpleNamespace(data=proxy.data, ops=proxy.ops, context=ctx)):
    run.autosave_after_finish(ctx)
    assert saves == ['D:/work/a.blend'] and 'finished' in p.phase2_autosave_status
    # Every finished stage saves before the next one starts; the last one is left to the finish save.
    events = []
    run.log_event = lambda event, data: events.append(data['moment'])
    run.plan = [('RESTORE', 'Restore', None, None), ('PREPARE', 'Create LODs', None, None),
                ('RENDER', 'Render', None, None)]
    for index in (1, 2, 3):
        run.index = index
        run.autosave_after_stage(ctx)
    assert len(saves) == 3, saves
    assert events == ['after Restore, before Create LODs', 'after Create LODs, before Render'], events
    assert p.phase2_autosave_status == 'Autosaved after Create LODs, before Render'
    p.phase2_autosave_after_finish = False
    run.autosave_after_finish(ctx)
    run.index = 1
    run.autosave_after_stage(ctx)
    assert len(saves) == 3
print('phase2 autosave finish ok')
