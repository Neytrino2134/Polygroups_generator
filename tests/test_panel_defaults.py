"""Blender smoke test for the N-panel defaults and Restore Defaults action."""

from pathlib import Path
import sys

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

window_keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.get("Window")
global_collection_keys = {
    item.type: item.properties.action
    for item in window_keymap.keymap_items
    if item.idname == "object.polygroups_generated_collection" and item.ctrl
}
assert global_collection_keys["EQUAL"] == "NEXT"
assert global_collection_keys["MINUS"] == "PREVIOUS"

scene = bpy.context.scene
model = scene.polygroups_model_preparation_settings
seams = scene.polygroups_seam_preparation_settings
generator = scene.polygroups_generator_settings
finalization = scene.polygroups_seam_finalization_settings
baking = scene.polygroups_baking_settings

assert model.file_import_separate_collections
assert model.batch_separate_collections
assert model.batch_include_subfolders
assert not model.batch_auto_save
assert model.batch_auto_save_interval == 5
assert model.file_import_auto_smart_uv_project
assert model.batch_auto_smart_uv_project
assert model.file_import_auto_unwrap_method == "SMART"
assert model.batch_auto_unwrap_method == "SMART"
assert model.batch_remesh_progress == 0
assert all(getattr(model, f"batch_stage_{stage}_enabled") for stage in (2, 3, 4, 5))
assert all(getattr(model, f"batch_stage_{stage}_{option}")
           for stage in (3, 4)
           for option in ("auto_remesh", "auto_unwrap", "use_materials",
                          "prepare_polygroups", "material_seams"))
assert model.batch_import_mode == "AUTO"
assert model.remesh_auto_unwrap_checker
assert seams.smart_seam_create_edges
assert seams.smart_seam_auto_relax
assert seams.uv_seam_path_auto_rip
assert seams.seam_relax_mode == "SMART"
assert seams.seam_relax_iterations == 2
assert generator.checker_scale == 80.0
assert abs(finalization.checker_overlay_opacity - 0.1) < 1.0e-6
assert finalization.uv_seam_path_auto_unwrap
assert abs(finalization.uv_seam_path_margin - 0.01) < 1.0e-6
assert finalization.narrow_island_source == 'UV'
assert finalization.narrow_island_width == 3
assert baking.disable_highpoly_after_bake

model.file_import_auto_remesh = False
assert not model.file_import_auto_smart_uv_project
model.file_import_auto_remesh = True
assert not model.file_import_auto_smart_uv_project
model.file_import_auto_unwrap_method = "CLASSIC"
model.batch_import_mode = "PAUSE_EACH"
model.batch_stage_4_enabled = False
model.file_import_separate_collections = False
model.batch_include_subfolders = False
seams.smart_seam_auto_relax = False
seams.seam_relax_iterations = 9
generator.checker_scale = 12.0
finalization.checker_overlay_opacity = 0.7
finalization.narrow_island_source = 'MESH'
finalization.narrow_island_width = 5
baking.disable_highpoly_after_bake = False
assert bpy.ops.object.airetopo_restore_panel_defaults() == {"FINISHED"}
assert model.file_import_separate_collections
assert model.batch_include_subfolders
assert model.file_import_auto_remesh
assert model.file_import_auto_smart_uv_project
assert model.file_import_auto_unwrap_method == "SMART"
assert model.batch_import_mode == "AUTO"
assert model.batch_stage_4_enabled
assert seams.smart_seam_auto_relax
assert seams.seam_relax_iterations == 2
assert generator.checker_scale == 80.0
assert abs(finalization.checker_overlay_opacity - 0.1) < 1.0e-6
assert finalization.narrow_island_source == 'UV'
assert finalization.narrow_island_width == 3
assert baking.disable_highpoly_after_bake

addon_utils.disable(ROOT.name, default_set=True)
print("PANEL_DEFAULTS_OK", flush=True)
