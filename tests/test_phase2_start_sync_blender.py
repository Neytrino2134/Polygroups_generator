"""Start Phase 2 settings stay in sync with Restore / Finalization / Render; presets, defaults, Retopo_01 keep, dialog."""
import sys
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_processing as processing  # noqa: E402
from polygroups_generator.operators import phase2_start_dialog as dialog  # noqa: E402
from polygroups_generator.operators.phase2_pipeline_stages import selected_stages  # noqa: E402

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings

# Defaults requested for Phase 2.
assert p.phase2_autosave and p.phase2_export_fbx and not p.phase2_export_glb
assert p.phase2_blend_export_generated and p.phase2_blend_export_highpoly and p.phase2_blend_export_retopo01
assert p.phase2_zbrush_cleanup_on_success and p.phase2_run_cleanup
assert p.phase2_auto_skip_scene and not p.phase2_run_zbrush

# Pairs follow each other in both directions.
pairs = (('phase2_run_mid', 'phase2_mid_remesh'), ('phase2_run_resculpt_retopo01', 'phase2_resculpt_retopo01'),
         ('phase2_run_high_remesh', 'phase2_high_remesh_before_resculpting'),
         ('phase2_run_repair_resculpt', 'phase2_repair_after_resculpt'),
         ('phase2_run_bake_resculpt', 'phase2_autobake_retopo01'),
         ('phase2_run_cleanup', 'phase2_zbrush_cleanup_on_success'), ('phase2_run_transparent', 'phase2_auto_transparent'))
for run_name, manual_name in pairs:
    for value in (True, False):
        setattr(p, run_name, value)
        assert getattr(p, manual_name) == value, (run_name, value)
        setattr(p, manual_name, not value)
        assert getattr(p, run_name) == (not value), (manual_name, value)
p.phase2_run_mode = 'IMPORT'
assert not p.phase2_auto_bake
p.phase2_auto_bake = True
assert p.phase2_run_mode == 'REBAKE'
p.phase2_auto_bake = False
assert p.phase2_run_mode == 'IMPORT'
p.phase2_run_engine = 'UNITY'
assert p.phase2_export_engine == p.phase2_final_rename_engine == 'UNITY' and p.phase2_final_lod_engine == 'UNITY'
p.phase2_export_engine = 'FAB'
assert p.phase2_run_engine == 'FAB' and p.phase2_final_rename_engine == 'FAB'
p.phase2_run_prepare = False
assert not p.phase2_final_lods and not p.phase2_final_rename
p.phase2_final_lods = True
assert p.phase2_run_prepare
p.phase2_run_prepare = True

# Import + Rebake preset turns MID Remesh on.
p.phase2_mid_remesh = False
assert bpy.ops.object.polygroups_phase2_processing_preset(preset='REBAKE') == {'FINISHED'}
assert p.phase2_mid_remesh and p.phase2_run_mid and p.phase2_auto_bake

# Presets.
assert bpy.ops.object.polygroups_phase2_start_preset(preset='UNREAL') == {'FINISHED'}
assert dialog.active_start_preset(p) == 'UNREAL'
assert not any(getattr(p, name) for name in dialog.HIGHPOLY_OPTIONS)
assert not p.phase2_run_zbrush and not p.phase2_run_cleanup and not p.phase2_resculpt_retopo01
assert p.phase2_run_mid and p.phase2_run_blend and p.phase2_run_export and p.phase2_run_render
assert p.phase2_export_fbx and not p.phase2_export_glb and p.phase2_auto_skip_scene
keys = [entry[0] for entry in selected_stages(p)]
assert 'ZBRUSH' not in keys and 'CLEANUP' not in keys and {'RESTORE', 'PREPARE', 'EXPORT', 'BLEND', 'RENDER'} <= set(keys), keys
assert bpy.ops.object.polygroups_phase2_start_preset(preset='UNREAL_ZBRUSH') == {'FINISHED'}
assert dialog.active_start_preset(p) == 'UNREAL_ZBRUSH'
assert all(getattr(p, name) for name in dialog.HIGHPOLY_OPTIONS)
assert p.phase2_resculpt_retopo01 and p.phase2_autobake_retopo01 and p.phase2_run_zbrush and p.phase2_run_cleanup
keys = [entry[0] for entry in selected_stages(p)]
assert 'ZBRUSH' in keys and 'CLEANUP' in keys
# Return to Blender and Cleanup belongs to Export ZBrush.
p.phase2_run_zbrush = False
assert 'CLEANUP' not in [entry[0] for entry in selected_stages(p)]

# Retopo_01 stays next to Highpoly_Generated.N when Resculpting_01 is not made.
collection = bpy.data.collections.new('Generated.1')
ctx.scene.collection.children.link(collection)
p.phase2_blend_export_generated = p.phase2_blend_export_highpoly = p.phase2_blend_export_retopo01 = True
p.phase2_resculpt_retopo01 = False
assert processing.keep_retopo01_for_blend(p, collection)
p.phase2_blend_export_retopo01 = False
assert not processing.keep_retopo01_for_blend(p, collection)
p.phase2_blend_export_retopo01 = True
p.phase2_blend_export_highpoly = False
assert not processing.keep_retopo01_for_blend(p, collection)
p.phase2_blend_export_highpoly = True
p.phase2_resculpt_retopo01 = True
assert processing.keep_retopo01_for_blend(p, collection)  # no Resculpting_01 in the collection yet
mesh = bpy.data.meshes.new('Resculpting_01_Mesh')
collection.objects.link(bpy.data.objects.new('Resculpting_01_Highpoly_Generated.1', mesh))
assert not processing.keep_retopo01_for_blend(p, collection)

# The confirmation dialog edits the same asset fields the pipeline reads.
p.phase2_run_engine = 'FAB'
assert dialog.asset_fields(p)[0] == 'unreal_lod_asset_name'
p.phase2_run_engine = 'UNITY'
assert dialog.asset_fields(p)[0] == 'unity_asset_name'
assert hasattr(bpy.types, 'OBJECT_OT_polygroups_phase2_confirm_start')
print('phase2 start sync ok')
