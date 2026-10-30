"""Delete Generated.N Collections: removed only after their own blend export succeeded; kept for ZBrush."""
import sys, tempfile
from pathlib import Path
from types import SimpleNamespace
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_pipeline_stages as stages
from polygroups_generator.operators import phase2_start_dialog as dialog
ctx = bpy.context; p = ctx.scene.polygroups_model_preparation_settings
assert p.phase2_blend_delete_generated  # on by default
p.phase2_blend_delete_generated = False
dialog.apply_start_preset(p, 'UNREAL')
assert p.phase2_blend_delete_generated  # Start Phase 2 presets turn it on


def scene_setup():
    for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections): bpy.data.collections.remove(col)
    for name in ('Stone_01_01_Collection', 'Generated.001', 'Generated.002'):
        col = bpy.data.collections.new(name); ctx.scene.collection.children.link(col)
        mesh = bpy.data.meshes.new(name); mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        obj_name = 'SM_Stone_01_01_MID' if name.endswith('_Collection') else 'Resculpting_01_Highpoly_' + name
        col.objects.link(bpy.data.objects.new(obj_name, mesh))


def run_stage(plan_keys):
    run = SimpleNamespace(settings=p, plan=[(key, key, None, None) for key in plan_keys])
    list(stages.export_blend(run, ctx))


with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_blend_delete_') as directory:
    root = Path(directory)
    p.phase2_blend_export_generated = True
    scene_setup()
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Pack.blend'))
    # Manual Export Blend Files.
    assert bpy.ops.object.polygroups_phase2_export_blend() == {'FINISHED'}, p.phase2_blend_export_status
    names = sorted(f.name for f in (root / '!Blend').glob('*.blend'))
    assert names == ['Generated.001.blend', 'Generated.002.blend', 'Stone_01_01.blend'], names
    assert set(bpy.data.collections.keys()) == {'Stone_01_01_Collection'}
    assert 'deleted 2 Generated.N' in p.phase2_blend_export_status
    assert not [o for o in bpy.data.objects if o.name.startswith('Resculpting_')]
    # Option off keeps them.
    scene_setup(); p.phase2_blend_delete_generated = False
    assert bpy.ops.object.polygroups_phase2_export_blend() == {'FINISHED'}
    assert {'Generated.001', 'Generated.002'} <= set(bpy.data.collections.keys())
    p.phase2_blend_delete_generated = True
    # Start Phase 2 Export Blend stage deletes them, unless Export ZBrush still follows.
    scene_setup(); run_stage(['RESTORE', 'BLEND', 'RENDER'])
    assert set(bpy.data.collections.keys()) == {'Stone_01_01_Collection'}
    scene_setup(); run_stage(['RESTORE', 'BLEND', 'ZBRUSH', 'CLEANUP'])
    assert {'Generated.001', 'Generated.002'} <= set(bpy.data.collections.keys())
print('PHASE2_BLEND_DELETE_GENERATED_OK')
