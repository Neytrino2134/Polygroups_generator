from .unity_export_workflow import (OBJECT_OT_polygroups_prepare_and_export_unity, OBJECT_OT_polygroups_save_unity_export_preset, OBJECT_OT_polygroups_load_unity_export_preset, OBJECT_OT_polygroups_unity_load_from_file)
from .phase2_export import OBJECT_OT_polygroups_phase2_export
from .smart_lods import OBJECT_OT_polygroups_smart_lods_prepare
from .unity_preparation import OBJECT_OT_polygroups_unity_collection_step
from .unity_preparation import OBJECT_OT_polygroups_fix_unity_textures
from .unity_preparation import OBJECT_OT_polygroups_rename_unity_meshes
from .unity_preparation import OBJECT_OT_polygroups_render_unity_turnaround
from .unity_preparation import OBJECT_OT_polygroups_unity_random_color_tag
from .unity_preparation import OBJECT_OT_polygroups_unity_index_step, OBJECT_OT_polygroups_render_unity_assets
from .smart_lods import OBJECT_OT_polygroups_render_smart_lods
from .render_textures import CLASSES as TEXTURE_RENDER_CLASSES
from .render_selected import CLASSES as SELECTED_RENDER_CLASSES
from ..core.render_palettes import OPERATOR_CLASSES as PALETTE_OPERATOR_CLASSES, ensure_libraries, flush_library, stop_library
from .repair_uv_stretch import MESH_OT_polygroups_repair_uv_stretch, IMAGE_PT_polygroups_uv_repair
from .uv_artifacts import MESH_OT_polygroups_uv_artifact_cleanup
from .repair_mesh_folds import MESH_OT_polygroups_repair_mesh_folds
from .split_narrow_islands import (
    MESH_OT_polygroups_split_narrow_islands,
    IMAGE_PT_polygroups_narrow_islands,
)
from .seam_eraser import MESH_OT_polygroups_seam_eraser_resize
from .seam_eraser import MESH_OT_polygroups_seam_eraser, MESH_OT_polygroups_edge_seam_eraser_click
from .apply_weld import OBJECT_OT_polygroups_apply_weld
from .delete_and_fill import MESH_OT_polygroups_delete_and_fill
from .remesh_progress import OBJECT_OT_polygroups_run_remesh, OBJECT_OT_polygroups_cancel_remesh, OBJECT_OT_polygroups_remesh_step
from .generated_visibility import OBJECT_OT_polygroups_object_visibility
from .generated_visibility import OBJECT_OT_polygroups_generated_collection
from .generated_index import OBJECT_OT_polygroups_fix_all_generated_indices
from .generated_index import OBJECT_OT_polygroups_fix_selected_generated_indices
from .generated_index import OBJECT_OT_polygroups_move_to_new_generated_collection
from .ai_generation import OBJECT_OT_airetopo_generate_google_image
from .ai_generation import OBJECT_OT_airetopo_generate_openai_image
from .ai_generation import OBJECT_OT_airetopo_load_library_prompt
from .ai_generation import OBJECT_OT_airetopo_open_generated_image
from .ai_generation import OBJECT_OT_airetopo_open_prompt_library_folder
from .ai_generation import OBJECT_OT_airetopo_preview_input_image
from .ai_generation import OBJECT_OT_airetopo_refresh_prompt_library
from .ai_generation import OBJECT_OT_airetopo_save_generated_image
from .ai_generation import OBJECT_OT_airetopo_select_material_image
from .baking import OBJECT_OT_polygroups_bake_selected_to_active
from .baking import OBJECT_OT_polygroups_bake_task
from .baking import OBJECT_OT_polygroups_calculate_auto_cage
from .smart_cage import OBJECT_OT_polygroups_generate_smart_cage, OBJECT_OT_polygroups_validate_smart_cage
from .baking import OBJECT_OT_polygroups_clear_bake_temp_images
from .baking import OBJECT_OT_polygroups_merge_bake_textures
from .baking import OBJECT_OT_polygroups_prepare_and_bake
from .baking import OBJECT_OT_polygroups_prepare_highpoly_bake_materials
from .baking import OBJECT_OT_polygroups_prepare_lowpoly_bake_material
from .baking import OBJECT_OT_polygroups_save_blend_file
from .baking import OBJECT_OT_polygroups_save_blend_file_as
from .baking import OBJECT_OT_polygroups_save_bake_textures
from .baking import OBJECT_OT_polygroups_restore_textures
from .batch_import import AIRETOPO_FH_gltf
from .batch_import import OBJECT_OT_polygroups_batch_import
from .import_queue import OBJECT_OT_polygroups_import_control
from .import_queue import OBJECT_OT_polygroups_reset_import_state
from .import_queue import OBJECT_OT_polygroups_restore_separate_retopo
from .import_queue import OBJECT_OT_polygroups_batch_redo_select
from .import_queue import OBJECT_OT_polygroups_toggle_batch_stage
from .phase2_processing import CLASSES as PHASE2_CLASSES, stop_phase2
from .batch_import import OBJECT_OT_polygroups_arrange_batch_objects
from .batch_import import OBJECT_OT_polygroups_scan_import_folder
from .batch_import import OBJECT_OT_polygroups_append_generated_blends
from .batch_import import OBJECT_OT_polygroups_select_import_folder
from .check_material_textures import OBJECT_OT_polygroups_check_material_textures
from .clear_materials import OBJECT_OT_clear_polygroups_materials
from .clear_edges_seam import MESH_OT_polygroups_clear_selected_edges_seam
from .clear_edges_seam import MESH_OT_polygroups_clear_inside_edges_seam
from .connect_vertex_seam import MESH_OT_polygroups_connect_vertex_seam
from .connect_vertex_seam import MESH_OT_polygroups_seam_cursor_modifier
from .connect_vertex_seam import MESH_OT_polygroups_connect_vertex_seam_click
from .edge_seam_path import MESH_OT_polygroups_edge_seam_path, MESH_OT_polygroups_edge_seam_path_click
from .uv_seam_path import (
    IMAGE_OT_polygroups_uv_island_select,
    IMAGE_OT_polygroups_uv_vertex_select,
    IMAGE_OT_polygroups_uv_seam_path_exit,
    IMAGE_OT_polygroups_uv_seam_tool_state,
    IMAGE_OT_polygroups_uv_seam_path_click,
    WM_OT_polygroups_activate_uv_seam_path,
)
from .edge_merger import MESH_OT_polygroups_edge_merger_click
from .face_sets_to_materials import OBJECT_OT_face_sets_to_materials
from .fab_preparation import OBJECT_OT_polygroups_auto_prepare_fab_selection
from .fab_preparation import OBJECT_OT_polygroups_auto_prepare_all_generated, OBJECT_OT_polygroups_stop_fab_prepare
from .fab_preparation import OBJECT_OT_polygroups_prepare_fab_variant
from .fab_rename_existing import OBJECT_OT_polygroups_rename_existing_fab, OBJECT_OT_polygroups_fab_variant_visibility
from .unreal_lod_rename import OBJECT_OT_polygroups_unreal_lod_rename
from .unity_preparation import OBJECT_OT_polygroups_prepare_unity, OBJECT_OT_polygroups_export_unity
from .generate_polygroups import OBJECT_OT_generate_polygroups
from .generate_polygroups import OBJECT_OT_polygroups_apply_checker_material
from .generate_polygroups import OBJECT_OT_polygroups_apply_material_mode
from .knife_seam_tool import MESH_OT_polygroups_knife_seam
from .knife_seam_tool import MESH_OT_polygroups_finish_knife_seam
from .knife_seam_tool import MESH_OT_polygroups_native_knife_seam
from .mark_material_boundaries_seam import MESH_OT_polygroups_mark_material_boundaries_seam
from .mark_longitudinal_seam import MESH_OT_polygroups_mark_boundary_and_longitudinal_seam
from .mark_longitudinal_seam import MESH_OT_polygroups_mark_longitudinal_seam
from .mark_longitudinal_seam import MESH_OT_polygroups_longitudinal_seam_tool_click
from .mark_selection_boundary_seam import MESH_OT_polygroups_mark_selection_boundary_seam
from .mark_selected_edges_seam import MESH_OT_polygroups_mark_selected_edges_seam
from .mesh_checks import OBJECT_OT_polygroups_check_mesh
from .mesh_checks import OBJECT_OT_polygroups_clean_mesh
from .mesh_checks import OBJECT_OT_polygroups_create_mesh_backup
from .mesh_checks import OBJECT_OT_polygroups_delete_loose_geometry
from .mesh_checks import OBJECT_OT_polygroups_delete_thin_protrusions
from .mesh_checks import OBJECT_OT_polygroups_fill_nonmanifold
from .mesh_checks import OBJECT_OT_polygroups_fix_mesh_stage
from .mesh_checks import OBJECT_OT_polygroups_fix_mesh_normals
from .mesh_checks import OBJECT_OT_polygroups_next_mesh_check_stage
from .mesh_checks import OBJECT_OT_polygroups_scan_and_fix_all
from .mesh_checks import OBJECT_OT_polygroups_scan_mesh_stage
from .mesh_checks import OBJECT_OT_polygroups_select_thin_protrusions
from .mesh_checks import OBJECT_OT_polygroups_start_mesh_check
from .mesh_checks import OBJECT_OT_polygroups_triangulate_ngons
from .mesh_checks import OBJECT_OT_polygroups_undo_mesh_check_fix
from .mesh_checks import discard_mesh_check_backup
from .small_loose_parts import OBJECT_OT_polygroups_small_loose_parts
from .mesh_export import OBJECT_OT_polygroups_export_blend_assets
from .mesh_export import OBJECT_OT_polygroups_export_selected_gltf
from .mesh_export import OBJECT_OT_polygroups_export_selected_meshes
from .mesh_export import OBJECT_OT_polygroups_add_blend_static_collection
from .mesh_export import OBJECT_OT_polygroups_clear_blend_static_collections
from .mesh_export import OBJECT_OT_polygroups_scan_blend_assets
from .object_seam_cutter import OBJECT_OT_polygroups_apply_cutter_seams
from .object_seam_cutter import OBJECT_OT_polygroups_create_cutter_backup
from .object_seam_cutter import OBJECT_OT_polygroups_restore_cutter_backup
from .object_seam_cutter import OBJECT_OT_polygroups_auto_fix_after_cutter
from .object_seam_cutter import OBJECT_OT_polygroups_bezier_cutter_paths
from .object_seam_cutter import OBJECT_OT_polygroups_clear_cutter_planes
from .object_seam_cutter import OBJECT_OT_polygroups_convert_draw_strokes_to_cutter_paths
from .object_seam_cutter import OBJECT_OT_polygroups_copy_mirror_cutters
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_arc
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_draw
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_local_ring
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_local_contour
from .local_contour_sketch import (
    OBJECT_OT_polygroups_draw_local_contour_path,
    OBJECT_OT_polygroups_draw_local_contour_draw,
    OBJECT_OT_polygroups_local_contour_gesture,
    OBJECT_OT_polygroups_finalize_local_contour,
)
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_path
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_plane
from .cutter_grid import OBJECT_OT_polygroups_draw_cutter_grid, OBJECT_OT_polygroups_generate_cutter_grid
from .object_seam_cutter import OBJECT_OT_polygroups_join_draw_strokes
from .object_seam_cutter import OBJECT_OT_polygroups_join_cutter_paths
from .object_seam_cutter import OBJECT_OT_polygroups_select_cutter_planes
from .object_seam_cutter import OBJECT_OT_polygroups_split_object_by_cutters
from .object_seam_cutter import OBJECT_OT_polygroups_smooth_cutter_path_tilt
from .object_seam_cutter import OBJECT_OT_polygroups_smooth_cutter_paths
from .object_seam_cutter import OBJECT_OT_polygroups_tilt_cutter_path
from .object_seam_cutter import OBJECT_OT_polygroups_toggle_cyclic_cutter_paths
from .panel_visibility import OBJECT_OT_airetopo_restore_panel_defaults
from .panel_visibility import OBJECT_OT_airetopo_set_section_subsection_visibility
from .panel_visibility import OBJECT_OT_airetopo_set_all_section_visibility
from .quick_knife_seam_tool import MESH_OT_polygroups_quick_knife_seam
from .rename_objects import OBJECT_OT_polygroups_rename_objects
from .remesh_presets import OBJECT_OT_polygroups_set_quad_count_preset
from .render_queue import OBJECT_OT_polygroups_clear_multiview_render
from .render_queue import OBJECT_OT_polygroups_prepare_selected_multiview
from .render_queue import OBJECT_OT_polygroups_clear_freestyle_edges
from .render_queue import OBJECT_OT_polygroups_continue_render_queue
from .render_queue import OBJECT_OT_polygroups_mark_freestyle_edges
from .render_queue import OBJECT_OT_polygroups_render_current_state
from .render_queue import OBJECT_OT_polygroups_scan_render_queue
from .render_queue import OBJECT_OT_polygroups_render_rename_suffix
from .render_queue import OBJECT_OT_polygroups_start_render_queue
from .render_queue import OBJECT_OT_polygroups_stop_render_queue
from .render_queue import OBJECT_OT_polygroups_reset_render_state
from .render_studio import (
    RENDER_OT_polygroups_prepare_studio, RENDER_OT_polygroups_move_studio,
    RENDER_OT_polygroups_reset_studio,
    RENDER_OT_polygroups_studio_light_colors,
    RENDER_OT_polygroups_delete_studio_scenes,
)
from .render_resolution import RENDER_OT_polygroups_apply_resolution
from .turnaround_animation import OBJECT_OT_polygroups_prepare_turnaround_animation
from .turnaround_animation import OBJECT_OT_polygroups_render_turnaround_animation
from .turnaround_animation import OBJECT_OT_polygroups_render_turnaround_views
from .resculpting import OBJECT_OT_polygroups_add_multires
from .resculpting import OBJECT_OT_polygroups_add_shrinkwrap_to_highpoly
from .resculpting import OBJECT_OT_polygroups_setup_resculpting
from .select_seam_tool import MESH_OT_polygroups_select_seam_tool
from .seam_gap_detection import MESH_OT_polygroups_check_seam_gaps
from .seam_gap_detection import MESH_OT_polygroups_check_and_close_seam_gaps
from .seam_gap_detection import MESH_OT_polygroups_connect_seam_gap_pairs
from .relax_seams import MESH_OT_polygroups_relax_seams
from .safety_checks import OBJECT_OT_polygroups_checked_quad_remesh
from .safety_checks import OBJECT_OT_polygroups_checked_generate_polygroups
from .safety_checks import OBJECT_OT_polygroups_checked_prepare_and_bake
from .safety_checks import OBJECT_OT_polygroups_checked_bake_selected_to_active
from .safety_checks import OBJECT_OT_polygroups_checked_prepare_lowpoly_bake_material
from .safety_checks import OBJECT_OT_polygroups_make_lowpoly_active
from .safety_checks import OBJECT_OT_polygroups_missing_uv_bake_dialog
from .safety_checks import OBJECT_OT_polygroups_rename_and_apply_weld
from .safety_checks import OBJECT_OT_polygroups_skip_prepare_and_bake
from .safety_checks import OBJECT_OT_polygroups_skip_generate_polygroups
from .safety_checks import OBJECT_OT_polygroups_skip_quad_remesh
from .smooth_face_selection import MESH_OT_polygroups_smooth_face_selection
from .smart_decimate import (
    OBJECT_OT_polygroups_smart_decimate, OBJECT_OT_polygroups_smart_decimate_all_generated,
    OBJECT_OT_polygroups_delete_all_decimated, OBJECT_OT_polygroups_show_all_low,
)
from .sequential_jobs import OBJECT_OT_polygroups_stop_lod_job, stop_jobs
from .auto_render import OBJECT_OT_polygroups_phase2_auto_render
from .batch_finalization import OBJECT_OT_polygroups_batch_finalization
from .smart_lods import OBJECT_OT_polygroups_generate_smart_lods
from .unwrap_angle_based import OBJECT_OT_polygroups_average_islands_scale
from .unwrap_angle_based import OBJECT_OT_polygroups_smart_uv_project
from .unwrap_angle_based import OBJECT_OT_polygroups_smart_uv_unwrap
from .unwrap_angle_based import OBJECT_OT_polygroups_unwrap_angle_based
from .uvpackmaster_controls import OBJECT_OT_polygroups_uvpackmaster_pack

from .small_islands import (
    MESH_OT_polygroups_analyze_and_merge_seams,
    MESH_OT_polygroups_merge_small_islands,
)
from .small_islands_tool import MESH_OT_polygroups_small_islands_merger_gesture
from .small_islands_tool import MESH_OT_polygroups_island_selector_gesture
from .small_islands_tool import MESH_OT_polygroups_face_selector_click
from .small_islands_tool import MESH_OT_polygroups_face_selector_gesture
from .pin_edges import MESH_OT_polygroups_pin_selected_seams, MESH_OT_polygroups_unpin_selected_edges, MESH_OT_polygroups_clear_all_pins
from .smart_angle_seams import MESH_OT_polygroups_mark_smart_angle_seams
from .smart_angle_seams import MESH_OT_polygroups_smart_seams_generator_click

from .dev_restart import (
    WM_OT_airetopo_dev_cleanup,
    WM_OT_airetopo_dev_restart,
    WM_OT_airetopo_dev_restart_current,
    WM_OT_airetopo_dev_restart_without_saving,
)
from .relocate_project import WM_OT_airetopo_relocate_project, WM_OT_airetopo_relocate_index_step

from .detached_groups import WM_OT_airetopo_detach_group, WM_OT_airetopo_group_window_control

from .phase2_blend_export import OBJECT_OT_polygroups_phase2_export_blend, OBJECT_OT_polygroups_phase2_open_blend_folder

CLASSES = (
    OBJECT_OT_polygroups_phase2_export,
    OBJECT_OT_polygroups_phase2_export_blend, OBJECT_OT_polygroups_phase2_open_blend_folder,
    OBJECT_OT_polygroups_stop_lod_job, OBJECT_OT_polygroups_batch_finalization,
    OBJECT_OT_polygroups_phase2_auto_render,
    *PHASE2_CLASSES,
    WM_OT_airetopo_relocate_project,
    OBJECT_OT_polygroups_unity_load_from_file,
    WM_OT_airetopo_relocate_index_step,
    OBJECT_OT_polygroups_render_unity_turnaround,
    OBJECT_OT_polygroups_unity_index_step,
    OBJECT_OT_polygroups_unity_random_color_tag,
    OBJECT_OT_polygroups_render_unity_assets,
    OBJECT_OT_polygroups_render_smart_lods,
    *SELECTED_RENDER_CLASSES,
    *TEXTURE_RENDER_CLASSES,
    *PALETTE_OPERATOR_CLASSES,
    MESH_OT_polygroups_repair_uv_stretch,
    MESH_OT_polygroups_uv_artifact_cleanup,
    MESH_OT_polygroups_repair_mesh_folds,
    IMAGE_PT_polygroups_uv_repair,
    MESH_OT_polygroups_split_narrow_islands,
    IMAGE_PT_polygroups_narrow_islands,
    WM_OT_airetopo_detach_group,
    WM_OT_airetopo_group_window_control,
    WM_OT_airetopo_dev_restart,
    WM_OT_airetopo_dev_restart_current,
    WM_OT_airetopo_dev_restart_without_saving,
    WM_OT_airetopo_dev_cleanup,
    MESH_OT_polygroups_merge_small_islands,
    MESH_OT_polygroups_analyze_and_merge_seams,
    MESH_OT_polygroups_small_islands_merger_gesture,
    MESH_OT_polygroups_island_selector_gesture,
    MESH_OT_polygroups_face_selector_click,
    MESH_OT_polygroups_face_selector_gesture,
    MESH_OT_polygroups_edge_merger_click,
    MESH_OT_polygroups_pin_selected_seams,
    MESH_OT_polygroups_unpin_selected_edges,
    MESH_OT_polygroups_clear_all_pins,
    MESH_OT_polygroups_mark_smart_angle_seams,
    MESH_OT_polygroups_smart_seams_generator_click,
    OBJECT_OT_polygroups_run_remesh,
    OBJECT_OT_polygroups_remesh_step,
    OBJECT_OT_polygroups_cancel_remesh,
    OBJECT_OT_polygroups_apply_weld,
    OBJECT_OT_polygroups_object_visibility,
    OBJECT_OT_polygroups_generated_collection,
    OBJECT_OT_polygroups_fix_all_generated_indices,
    OBJECT_OT_polygroups_fix_selected_generated_indices,
    OBJECT_OT_polygroups_move_to_new_generated_collection,
    OBJECT_OT_polygroups_select_import_folder,
    OBJECT_OT_airetopo_generate_openai_image,
    OBJECT_OT_airetopo_generate_google_image,
    OBJECT_OT_airetopo_refresh_prompt_library,
    OBJECT_OT_airetopo_open_prompt_library_folder,
    OBJECT_OT_airetopo_load_library_prompt,
    OBJECT_OT_airetopo_select_material_image,
    OBJECT_OT_airetopo_preview_input_image,
    OBJECT_OT_airetopo_open_generated_image,
    OBJECT_OT_airetopo_save_generated_image,
    OBJECT_OT_airetopo_set_all_section_visibility,
    OBJECT_OT_airetopo_set_section_subsection_visibility,
    OBJECT_OT_airetopo_restore_panel_defaults,
    OBJECT_OT_polygroups_scan_import_folder,
    OBJECT_OT_polygroups_append_generated_blends,
    OBJECT_OT_polygroups_batch_import,
    AIRETOPO_FH_gltf,
    OBJECT_OT_polygroups_import_control,
    OBJECT_OT_polygroups_reset_import_state,
    OBJECT_OT_polygroups_restore_separate_retopo,
    OBJECT_OT_polygroups_batch_redo_select,
    OBJECT_OT_polygroups_toggle_batch_stage,
    OBJECT_OT_polygroups_arrange_batch_objects,
    OBJECT_OT_polygroups_rename_objects,
    OBJECT_OT_polygroups_check_material_textures,
    OBJECT_OT_polygroups_prepare_highpoly_bake_materials,
    OBJECT_OT_polygroups_prepare_lowpoly_bake_material,
    OBJECT_OT_polygroups_calculate_auto_cage,
    OBJECT_OT_polygroups_generate_smart_cage,
    OBJECT_OT_polygroups_validate_smart_cage,
    OBJECT_OT_polygroups_bake_selected_to_active,
    OBJECT_OT_polygroups_bake_task,
    OBJECT_OT_polygroups_prepare_and_bake,
    OBJECT_OT_polygroups_save_blend_file,
    OBJECT_OT_polygroups_save_blend_file_as,
    OBJECT_OT_polygroups_save_bake_textures,
    OBJECT_OT_polygroups_restore_textures,
    OBJECT_OT_polygroups_merge_bake_textures,
    OBJECT_OT_polygroups_clear_bake_temp_images,
    OBJECT_OT_polygroups_add_multires,
    OBJECT_OT_polygroups_add_shrinkwrap_to_highpoly,
    OBJECT_OT_polygroups_setup_resculpting,
    OBJECT_OT_polygroups_rename_and_apply_weld,
    MESH_OT_polygroups_delete_and_fill,
    OBJECT_OT_polygroups_checked_quad_remesh,
    OBJECT_OT_polygroups_checked_generate_polygroups,
    OBJECT_OT_polygroups_checked_prepare_lowpoly_bake_material,
    OBJECT_OT_polygroups_checked_prepare_and_bake,
    OBJECT_OT_polygroups_checked_bake_selected_to_active,
    OBJECT_OT_polygroups_missing_uv_bake_dialog,
    OBJECT_OT_polygroups_skip_quad_remesh,
    OBJECT_OT_polygroups_skip_generate_polygroups,
    OBJECT_OT_polygroups_skip_prepare_and_bake,
    OBJECT_OT_polygroups_make_lowpoly_active,
    OBJECT_OT_polygroups_set_quad_count_preset,
    OBJECT_OT_polygroups_render_current_state,
    OBJECT_OT_polygroups_scan_render_queue,
    OBJECT_OT_polygroups_render_rename_suffix,
    OBJECT_OT_polygroups_start_render_queue,
    OBJECT_OT_polygroups_stop_render_queue,
    OBJECT_OT_polygroups_reset_render_state,
    RENDER_OT_polygroups_apply_resolution,
    RENDER_OT_polygroups_prepare_studio,
    RENDER_OT_polygroups_move_studio,
    RENDER_OT_polygroups_reset_studio,
    RENDER_OT_polygroups_studio_light_colors,
    RENDER_OT_polygroups_delete_studio_scenes,
    OBJECT_OT_polygroups_clear_multiview_render,
    OBJECT_OT_polygroups_prepare_selected_multiview,
    OBJECT_OT_polygroups_mark_freestyle_edges,
    OBJECT_OT_polygroups_clear_freestyle_edges,
    OBJECT_OT_polygroups_continue_render_queue,
    OBJECT_OT_polygroups_prepare_turnaround_animation,
    OBJECT_OT_polygroups_render_turnaround_animation,
    OBJECT_OT_polygroups_render_turnaround_views,
    OBJECT_OT_generate_polygroups,
    OBJECT_OT_polygroups_apply_checker_material,
    OBJECT_OT_polygroups_apply_material_mode,
    MESH_OT_polygroups_mark_material_boundaries_seam,
    OBJECT_OT_polygroups_unwrap_angle_based,
    OBJECT_OT_polygroups_smart_uv_project,
    OBJECT_OT_polygroups_smart_uv_unwrap,
    OBJECT_OT_polygroups_average_islands_scale,
    OBJECT_OT_polygroups_uvpackmaster_pack,
    OBJECT_OT_face_sets_to_materials,
    OBJECT_OT_clear_polygroups_materials,
    OBJECT_OT_polygroups_prepare_fab_variant,
    OBJECT_OT_polygroups_rename_existing_fab,
    OBJECT_OT_polygroups_unreal_lod_rename,
    OBJECT_OT_polygroups_fab_variant_visibility,
    OBJECT_OT_polygroups_prepare_unity,
    OBJECT_OT_polygroups_rename_unity_meshes,
    OBJECT_OT_polygroups_fix_unity_textures,
    OBJECT_OT_polygroups_unity_collection_step,
    OBJECT_OT_polygroups_export_unity,
    OBJECT_OT_polygroups_prepare_and_export_unity,
    OBJECT_OT_polygroups_save_unity_export_preset,
    OBJECT_OT_polygroups_load_unity_export_preset,
    OBJECT_OT_polygroups_auto_prepare_fab_selection,
    OBJECT_OT_polygroups_auto_prepare_all_generated,
    OBJECT_OT_polygroups_stop_fab_prepare,
    MESH_OT_polygroups_mark_boundary_and_longitudinal_seam,
    MESH_OT_polygroups_mark_longitudinal_seam,
    MESH_OT_polygroups_longitudinal_seam_tool_click,
    MESH_OT_polygroups_mark_selected_edges_seam,
    MESH_OT_polygroups_clear_selected_edges_seam,
    MESH_OT_polygroups_clear_inside_edges_seam,
    MESH_OT_polygroups_connect_vertex_seam,
    MESH_OT_polygroups_connect_vertex_seam_click,
    MESH_OT_polygroups_seam_cursor_modifier,
    MESH_OT_polygroups_seam_eraser,
    MESH_OT_polygroups_seam_eraser_resize,
    MESH_OT_polygroups_edge_seam_eraser_click,
    MESH_OT_polygroups_edge_seam_path,
    MESH_OT_polygroups_edge_seam_path_click,
    IMAGE_OT_polygroups_uv_island_select,
    IMAGE_OT_polygroups_uv_vertex_select,
    IMAGE_OT_polygroups_uv_seam_path_exit,
    IMAGE_OT_polygroups_uv_seam_tool_state,
    IMAGE_OT_polygroups_uv_seam_path_click,
    WM_OT_polygroups_activate_uv_seam_path,
    MESH_OT_polygroups_mark_selection_boundary_seam,
    MESH_OT_polygroups_check_seam_gaps,
    MESH_OT_polygroups_check_and_close_seam_gaps,
    MESH_OT_polygroups_connect_seam_gap_pairs,
    MESH_OT_polygroups_relax_seams,
    MESH_OT_polygroups_smooth_face_selection,
    OBJECT_OT_polygroups_start_mesh_check,
    OBJECT_OT_polygroups_scan_mesh_stage,
    OBJECT_OT_polygroups_fix_mesh_stage,
    OBJECT_OT_polygroups_next_mesh_check_stage,
    OBJECT_OT_polygroups_undo_mesh_check_fix,
    OBJECT_OT_polygroups_scan_and_fix_all,
    OBJECT_OT_polygroups_check_mesh,
    OBJECT_OT_polygroups_fix_mesh_normals,
    OBJECT_OT_polygroups_triangulate_ngons,
    OBJECT_OT_polygroups_fill_nonmanifold,
    OBJECT_OT_polygroups_delete_loose_geometry,
    OBJECT_OT_polygroups_select_thin_protrusions,
    OBJECT_OT_polygroups_delete_thin_protrusions,
    OBJECT_OT_polygroups_clean_mesh,
    OBJECT_OT_polygroups_create_mesh_backup,
    OBJECT_OT_polygroups_small_loose_parts,
    OBJECT_OT_polygroups_export_selected_meshes,
    OBJECT_OT_polygroups_export_selected_gltf,
    OBJECT_OT_polygroups_scan_blend_assets,
    OBJECT_OT_polygroups_add_blend_static_collection,
    OBJECT_OT_polygroups_clear_blend_static_collections,
    OBJECT_OT_polygroups_export_blend_assets,
    MESH_OT_polygroups_knife_seam,
    MESH_OT_polygroups_finish_knife_seam,
    MESH_OT_polygroups_native_knife_seam,
    MESH_OT_polygroups_quick_knife_seam,
    MESH_OT_polygroups_select_seam_tool,
    OBJECT_OT_polygroups_smart_decimate,
    OBJECT_OT_polygroups_smart_decimate_all_generated,
    OBJECT_OT_polygroups_delete_all_decimated,
    OBJECT_OT_polygroups_show_all_low,
    OBJECT_OT_polygroups_generate_smart_lods,
    OBJECT_OT_polygroups_smart_lods_prepare,
    OBJECT_OT_polygroups_draw_cutter_plane,
    OBJECT_OT_polygroups_draw_cutter_grid,
    OBJECT_OT_polygroups_generate_cutter_grid,
    OBJECT_OT_polygroups_draw_cutter_arc,
    OBJECT_OT_polygroups_draw_cutter_local_ring,
    OBJECT_OT_polygroups_draw_cutter_local_contour,
    OBJECT_OT_polygroups_draw_local_contour_path,
    OBJECT_OT_polygroups_draw_local_contour_draw,
    OBJECT_OT_polygroups_local_contour_gesture,
    OBJECT_OT_polygroups_finalize_local_contour,
    OBJECT_OT_polygroups_draw_cutter_path,
    OBJECT_OT_polygroups_draw_cutter_draw,
    OBJECT_OT_polygroups_convert_draw_strokes_to_cutter_paths,
    OBJECT_OT_polygroups_join_draw_strokes,
    OBJECT_OT_polygroups_join_cutter_paths,
    OBJECT_OT_polygroups_bezier_cutter_paths,
    OBJECT_OT_polygroups_toggle_cyclic_cutter_paths,
    OBJECT_OT_polygroups_smooth_cutter_paths,
    OBJECT_OT_polygroups_smooth_cutter_path_tilt,
    OBJECT_OT_polygroups_tilt_cutter_path,
    OBJECT_OT_polygroups_copy_mirror_cutters,
    OBJECT_OT_polygroups_auto_fix_after_cutter,
    OBJECT_OT_polygroups_create_cutter_backup,
    OBJECT_OT_polygroups_restore_cutter_backup,
    OBJECT_OT_polygroups_apply_cutter_seams,
    OBJECT_OT_polygroups_split_object_by_cutters,
    OBJECT_OT_polygroups_select_cutter_planes,
    OBJECT_OT_polygroups_clear_cutter_planes,
)


def register():
    from . import ai_text
    ai_text.register()
    import bpy
    from .import_queue import stop_import_queue
    from .remesh_progress import stop_remesh
    from .knife_seam_tool import stop_knife_seams
    from .object_seam_cutter import stop_cutter_apply

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    MESH_OT_polygroups_native_knife_seam.define("MESH_OT_knife_tool")
    MESH_OT_polygroups_native_knife_seam.define("MESH_OT_polygroups_finish_knife_seam")
    from .fab_preparation import stop_fab_prepare
    bpy.app.handlers.load_pre.append(stop_fab_prepare)
    bpy.app.handlers.load_pre.append(stop_import_queue)
    for handler in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_jobs not in handler:
            handler.append(stop_jobs)
    bpy.app.handlers.load_pre.append(stop_phase2)
    bpy.app.handlers.undo_pre.append(stop_phase2)
    bpy.app.handlers.redo_pre.append(stop_phase2)
    bpy.app.timers.register(ensure_libraries, first_interval=0.0)
    bpy.app.handlers.load_post.append(ensure_libraries)
    bpy.app.handlers.load_pre.append(flush_library)
    bpy.app.handlers.load_pre.append(stop_remesh)
    bpy.app.handlers.undo_pre.append(stop_remesh)
    bpy.app.handlers.redo_pre.append(stop_remesh)
    bpy.app.handlers.load_pre.append(stop_knife_seams)
    bpy.app.handlers.load_pre.append(stop_cutter_apply)
    bpy.app.handlers.load_pre.append(discard_mesh_check_backup)
    from .detached_groups import cleanup_windows
    bpy.app.handlers.load_pre.append(cleanup_windows)


def unregister():
    from . import ai_text
    ai_text.unregister()
    import bpy
    from ..core.render_palettes import clear_swatches
    clear_swatches()
    stop_library()
    if flush_library in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(flush_library)
    if ensure_libraries in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(ensure_libraries)
    if bpy.app.timers.is_registered(ensure_libraries):
        bpy.app.timers.unregister(ensure_libraries)
    from .narrow_cut_preview import clear_preview
    clear_preview()
    from .detached_groups import cleanup_windows
    cleanup_windows()
    import bpy
    if cleanup_windows in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(cleanup_windows)
    from .import_queue import stop_import_queue
    from .remesh_progress import stop_remesh
    from .knife_seam_tool import stop_knife_seams
    from .object_seam_cutter import stop_cutter_apply

    from .fab_preparation import stop_fab_prepare
    stop_fab_prepare()
    if stop_fab_prepare in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(stop_fab_prepare)
    stop_import_queue()
    stop_jobs()
    for handler in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_jobs in handler:
            handler.remove(stop_jobs)
    stop_phase2()
    if stop_phase2 in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(stop_phase2)
    if stop_phase2 in bpy.app.handlers.undo_pre:
        bpy.app.handlers.undo_pre.remove(stop_phase2)
    if stop_phase2 in bpy.app.handlers.redo_pre:
        bpy.app.handlers.redo_pre.remove(stop_phase2)
    stop_remesh()
    stop_knife_seams()
    stop_cutter_apply()
    discard_mesh_check_backup()
    if discard_mesh_check_backup in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(discard_mesh_check_backup)
    if stop_cutter_apply in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(stop_cutter_apply)
    if stop_knife_seams in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(stop_knife_seams)
    if stop_remesh in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(stop_remesh)
    if stop_remesh in bpy.app.handlers.undo_pre:
        bpy.app.handlers.undo_pre.remove(stop_remesh)
    if stop_remesh in bpy.app.handlers.redo_pre:
        bpy.app.handlers.redo_pre.remove(stop_remesh)
    if stop_import_queue in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(stop_import_queue)

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
