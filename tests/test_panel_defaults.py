"""Blender smoke test for the N-panel defaults and Restore Defaults action."""

from pathlib import Path
from math import radians
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
assert not model.batch_save_generated_separately
assert model.small_loose_part_metric == "BOUNDING_BOX"
assert model.small_loose_part_threshold_percent == 8.0
assert model.file_import_auto_smart_uv_project
assert model.file_import_remove_small_loose_parts
assert model.file_import_small_loose_part_metric == "BOUNDING_BOX"
assert model.file_import_small_loose_part_threshold_percent == 8.0
assert not model.file_import_automatic_processing
assert model.batch_auto_smart_uv_project
assert model.file_import_auto_unwrap_method == "SMART"
assert model.batch_auto_unwrap_method == "SMART"
assert model.batch_remesh_progress == 0
assert model.batch_expanded_stages == 0
assert abs(model.batch_first_surface_angle - radians(22)) < 1.0e-6
assert model.batch_first_uv_repair_enabled
assert model.batch_first_uv_repair_threshold == 4.0
assert model.batch_first_uv_repair_min_faces == 6
assert abs(model.batch_first_uv_repair_surface_angle - radians(45)) < 1.0e-6
assert model.batch_first_remove_small_loose_parts
assert model.batch_first_small_loose_part_metric == "BOUNDING_BOX"
assert model.batch_first_small_loose_part_threshold_percent == 8.0
assert model.batch_narrow_island_max_width_percent == 10.0
assert all(getattr(model, f"batch_stage_{stage}_enabled") for stage in (2, 3, 4, 5))
assert model.batch_narrow_island_enabled
assert model.batch_second_narrow_island_enabled
assert model.batch_second_small_islands_enabled
assert model.batch_second_narrow_island_width == 3
assert model.batch_second_narrow_island_max_width_percent == 6.0
assert model.batch_second_small_island_threshold == 5.0
assert model.batch_autobake_enabled
assert model.batch_autobake_cage_mode == "AUTO"
assert model.batch_stage_3_remesh_preset == "MID"
assert model.batch_stage_3_autofix_enabled
assert model.batch_stage_3_autofix_fin_loose
assert model.batch_stage_3_autofix_close_nonmanifold
assert model.batch_stage_3_autofix_triangulate_ngons
assert model.batch_stage_4_remesh_preset == "MID"
assert model.batch_stage_3_auto_unwrap_method == "ANGLE"
assert model.batch_stage_4_auto_unwrap_method == "ANGLE"
assert model.batch_stage_3_smart_relax_edges
assert model.batch_stage_4_smart_relax_edges
assert model.batch_small_islands_enabled
assert model.batch_small_island_threshold == 5.0
assert model.batch_small_island_protect_pinned
assert model.batch_second_small_island_protect_pinned
assert model.batch_small_island_protect_sharp
assert not model.batch_small_island_protect_materials
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
assert finalization.narrow_island_width == 5
assert finalization.narrow_island_max_width_percent == 35.0
assert finalization.narrow_island_min_area_percent == 2.0
assert finalization.narrow_island_create_edges
assert finalization.narrow_island_smart_relax
assert baking.disable_highpoly_after_bake

model.file_import_auto_remesh = False
assert not model.file_import_auto_smart_uv_project
model.file_import_auto_remesh = True
assert not model.file_import_auto_smart_uv_project
model.file_import_auto_unwrap_method = "CLASSIC"
model.file_import_automatic_processing = True
model.batch_import_mode = "PAUSE_EACH"
model.batch_expanded_stages = 1023
model.batch_first_surface_angle = radians(40)
model.batch_first_uv_repair_enabled = False
model.batch_first_uv_repair_threshold = 9.0
model.batch_first_uv_repair_min_faces = 12
model.batch_first_uv_repair_surface_angle = radians(30)
model.batch_narrow_island_max_width_percent = 20.0
model.batch_stage_4_enabled = False
model.batch_stage_3_remesh_preset = "HIGH"
model.batch_stage_3_autofix_enabled = False
model.batch_stage_3_autofix_fin_loose = False
model.batch_stage_3_autofix_close_nonmanifold = False
model.batch_stage_3_autofix_triangulate_ngons = False
model.batch_stage_4_remesh_preset = "MID"
model.batch_stage_3_auto_unwrap_method = "SMART"
model.batch_stage_4_auto_unwrap_method = "SMART"
model.batch_stage_3_smart_relax_edges = False
model.batch_stage_4_smart_relax_edges = True
model.batch_narrow_island_enabled = False
model.batch_second_narrow_island_enabled = False
model.batch_second_small_islands_enabled = False
model.batch_second_narrow_island_width = 9
model.batch_second_narrow_island_max_width_percent = 20.0
model.batch_second_small_island_threshold = 12.0
model.batch_autobake_enabled = True
model.batch_autobake_cage_mode = "SMART"
model.batch_small_islands_enabled = False
model.batch_small_island_threshold = 12.0
model.batch_small_island_protect_sharp = False
model.file_import_separate_collections = False
model.batch_include_subfolders = False
seams.smart_seam_auto_relax = False
seams.seam_relax_iterations = 9
generator.checker_scale = 12.0
finalization.checker_overlay_opacity = 0.7
finalization.narrow_island_source = 'MESH'
finalization.narrow_island_width = 5
finalization.narrow_island_max_width_percent = 60.0
finalization.narrow_island_min_area_percent = 3.0
finalization.narrow_island_smart_relax = False
finalization.narrow_island_create_edges = False
baking.disable_highpoly_after_bake = False
assert bpy.ops.object.airetopo_restore_panel_defaults() == {"FINISHED"}
assert model.file_import_separate_collections
assert model.batch_include_subfolders
assert model.file_import_auto_remesh
assert model.file_import_auto_smart_uv_project
assert not model.file_import_automatic_processing
assert model.file_import_auto_unwrap_method == "SMART"
assert model.batch_import_mode == "AUTO"
assert model.batch_expanded_stages == 0
assert abs(model.batch_first_surface_angle - radians(22)) < 1.0e-6
assert model.batch_first_uv_repair_enabled
assert model.batch_first_uv_repair_threshold == 4.0
assert model.batch_first_uv_repair_min_faces == 6
assert abs(model.batch_first_uv_repair_surface_angle - radians(45)) < 1.0e-6
assert model.batch_narrow_island_max_width_percent == 10.0
assert model.batch_stage_4_enabled
assert model.batch_stage_3_remesh_preset == "MID"
assert model.batch_stage_3_autofix_enabled
assert model.batch_stage_3_autofix_fin_loose
assert model.batch_stage_3_autofix_close_nonmanifold
assert model.batch_stage_3_autofix_triangulate_ngons
assert model.batch_stage_4_remesh_preset == "MID"
assert model.batch_stage_3_auto_unwrap_method == "ANGLE"
assert model.batch_stage_4_auto_unwrap_method == "ANGLE"
assert model.batch_stage_3_smart_relax_edges
assert model.batch_stage_4_smart_relax_edges
assert model.batch_narrow_island_enabled
assert model.batch_second_narrow_island_enabled
assert model.batch_second_small_islands_enabled
assert model.batch_second_narrow_island_width == 3
assert model.batch_second_narrow_island_max_width_percent == 6.0
assert model.batch_second_small_island_threshold == 5.0
assert model.batch_autobake_enabled
assert model.batch_autobake_cage_mode == "AUTO"
assert model.batch_small_islands_enabled
assert model.batch_small_island_threshold == 5.0
for stage in range(1, 11):
    assert bpy.ops.object.polygroups_toggle_batch_stage(stage=stage) == {"FINISHED"}
assert model.batch_expanded_stages == 1023
for stage in range(1, 11):
    assert bpy.ops.object.polygroups_toggle_batch_stage(stage=stage) == {"FINISHED"}
assert model.batch_expanded_stages == 0
assert model.batch_stage_2_enabled and model.batch_stage_5_enabled
assert model.batch_small_island_protect_sharp
assert seams.smart_seam_auto_relax
assert seams.seam_relax_iterations == 2
assert generator.checker_scale == 80.0
assert abs(finalization.checker_overlay_opacity - 0.1) < 1.0e-6
assert finalization.narrow_island_source == 'UV'
assert finalization.narrow_island_width == 5
assert finalization.narrow_island_max_width_percent == 35.0
assert finalization.narrow_island_min_area_percent == 2.0
assert finalization.narrow_island_create_edges
assert finalization.narrow_island_smart_relax
assert baking.disable_highpoly_after_bake

addon_utils.disable(ROOT.name, default_set=True)
print("PANEL_DEFAULTS_OK", flush=True)
