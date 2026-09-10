"""Blender smoke test for the N-panel defaults and Restore Defaults action."""

from pathlib import Path
import sys

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

scene = bpy.context.scene
model = scene.polygroups_model_preparation_settings
seams = scene.polygroups_seam_preparation_settings
generator = scene.polygroups_generator_settings
finalization = scene.polygroups_seam_finalization_settings
baking = scene.polygroups_baking_settings

assert model.file_import_separate_collections
assert model.batch_separate_collections
assert model.batch_include_subfolders
assert model.file_import_auto_smart_uv_project
assert model.batch_auto_smart_uv_project
assert model.remesh_auto_unwrap_checker
assert seams.smart_seam_create_edges
assert seams.smart_seam_auto_relax
assert seams.seam_relax_mode == "SMART"
assert seams.seam_relax_iterations == 2
assert generator.checker_scale == 80.0
assert abs(finalization.checker_overlay_opacity - 0.1) < 1.0e-6
assert baking.disable_highpoly_after_bake

model.file_import_auto_remesh = False
assert not model.file_import_auto_smart_uv_project
model.file_import_auto_remesh = True
assert not model.file_import_auto_smart_uv_project
model.file_import_separate_collections = False
model.batch_include_subfolders = False
seams.smart_seam_auto_relax = False
seams.seam_relax_iterations = 9
generator.checker_scale = 12.0
finalization.checker_overlay_opacity = 0.7
baking.disable_highpoly_after_bake = False
assert bpy.ops.object.airetopo_restore_panel_defaults() == {"FINISHED"}
assert model.file_import_separate_collections
assert model.batch_include_subfolders
assert model.file_import_auto_remesh
assert model.file_import_auto_smart_uv_project
assert seams.smart_seam_auto_relax
assert seams.seam_relax_iterations == 2
assert generator.checker_scale == 80.0
assert abs(finalization.checker_overlay_opacity - 0.1) < 1.0e-6
assert baking.disable_highpoly_after_bake

addon_utils.disable(ROOT.name, default_set=True)
print("PANEL_DEFAULTS_OK", flush=True)
