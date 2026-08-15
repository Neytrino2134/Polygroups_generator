from .apply_weld import OBJECT_OT_polygroups_apply_weld
from .baking import OBJECT_OT_polygroups_bake_selected_to_active
from .baking import OBJECT_OT_polygroups_prepare_and_bake
from .baking import OBJECT_OT_polygroups_prepare_highpoly_bake_materials
from .baking import OBJECT_OT_polygroups_prepare_lowpoly_bake_material
from .baking import OBJECT_OT_polygroups_save_bake_textures
from .batch_import import OBJECT_OT_polygroups_batch_import
from .batch_import import OBJECT_OT_polygroups_scan_import_folder
from .batch_import import OBJECT_OT_polygroups_select_import_folder
from .clear_materials import OBJECT_OT_clear_polygroups_materials
from .face_sets_to_materials import OBJECT_OT_face_sets_to_materials
from .generate_polygroups import OBJECT_OT_generate_polygroups
from .generate_polygroups import OBJECT_OT_polygroups_apply_checker_material
from .generate_polygroups import OBJECT_OT_polygroups_apply_material_mode
from .knife_seam_tool import MESH_OT_polygroups_knife_seam
from .mark_material_boundaries_seam import MESH_OT_polygroups_mark_material_boundaries_seam
from .mark_longitudinal_seam import MESH_OT_polygroups_mark_boundary_and_longitudinal_seam
from .mark_longitudinal_seam import MESH_OT_polygroups_mark_longitudinal_seam
from .mark_selection_boundary_seam import MESH_OT_polygroups_mark_selection_boundary_seam
from .mark_selected_edges_seam import MESH_OT_polygroups_mark_selected_edges_seam
from .object_seam_cutter import OBJECT_OT_polygroups_apply_cutter_seams
from .object_seam_cutter import OBJECT_OT_polygroups_clear_cutter_planes
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_arc
from .object_seam_cutter import OBJECT_OT_polygroups_draw_cutter_plane
from .object_seam_cutter import OBJECT_OT_polygroups_select_cutter_planes
from .quick_knife_seam_tool import MESH_OT_polygroups_quick_knife_seam
from .rename_objects import OBJECT_OT_polygroups_rename_objects
from .remesh_presets import OBJECT_OT_polygroups_set_quad_count_preset
from .resculpting import OBJECT_OT_polygroups_add_multires
from .resculpting import OBJECT_OT_polygroups_add_shrinkwrap_to_highpoly
from .resculpting import OBJECT_OT_polygroups_setup_resculpting
from .select_seam_tool import MESH_OT_polygroups_select_seam_tool
from .safety_checks import OBJECT_OT_polygroups_checked_quad_remesh
from .safety_checks import OBJECT_OT_polygroups_checked_generate_polygroups
from .safety_checks import OBJECT_OT_polygroups_make_lowpoly_active
from .safety_checks import OBJECT_OT_polygroups_rename_and_apply_weld
from .safety_checks import OBJECT_OT_polygroups_skip_quad_remesh
from .smooth_face_selection import MESH_OT_polygroups_smooth_face_selection
from .unwrap_angle_based import OBJECT_OT_polygroups_average_islands_scale
from .unwrap_angle_based import OBJECT_OT_polygroups_smart_uv_project
from .unwrap_angle_based import OBJECT_OT_polygroups_unwrap_angle_based

CLASSES = (
    OBJECT_OT_polygroups_apply_weld,
    OBJECT_OT_polygroups_select_import_folder,
    OBJECT_OT_polygroups_scan_import_folder,
    OBJECT_OT_polygroups_batch_import,
    OBJECT_OT_polygroups_rename_objects,
    OBJECT_OT_polygroups_prepare_highpoly_bake_materials,
    OBJECT_OT_polygroups_prepare_lowpoly_bake_material,
    OBJECT_OT_polygroups_bake_selected_to_active,
    OBJECT_OT_polygroups_prepare_and_bake,
    OBJECT_OT_polygroups_save_bake_textures,
    OBJECT_OT_polygroups_add_multires,
    OBJECT_OT_polygroups_add_shrinkwrap_to_highpoly,
    OBJECT_OT_polygroups_setup_resculpting,
    OBJECT_OT_polygroups_rename_and_apply_weld,
    OBJECT_OT_polygroups_checked_quad_remesh,
    OBJECT_OT_polygroups_checked_generate_polygroups,
    OBJECT_OT_polygroups_skip_quad_remesh,
    OBJECT_OT_polygroups_make_lowpoly_active,
    OBJECT_OT_polygroups_set_quad_count_preset,
    OBJECT_OT_generate_polygroups,
    OBJECT_OT_polygroups_apply_checker_material,
    OBJECT_OT_polygroups_apply_material_mode,
    MESH_OT_polygroups_mark_material_boundaries_seam,
    OBJECT_OT_polygroups_unwrap_angle_based,
    OBJECT_OT_polygroups_smart_uv_project,
    OBJECT_OT_polygroups_average_islands_scale,
    OBJECT_OT_face_sets_to_materials,
    OBJECT_OT_clear_polygroups_materials,
    MESH_OT_polygroups_mark_boundary_and_longitudinal_seam,
    MESH_OT_polygroups_mark_longitudinal_seam,
    MESH_OT_polygroups_mark_selected_edges_seam,
    MESH_OT_polygroups_mark_selection_boundary_seam,
    MESH_OT_polygroups_smooth_face_selection,
    MESH_OT_polygroups_knife_seam,
    MESH_OT_polygroups_quick_knife_seam,
    MESH_OT_polygroups_select_seam_tool,
    OBJECT_OT_polygroups_draw_cutter_plane,
    OBJECT_OT_polygroups_draw_cutter_arc,
    OBJECT_OT_polygroups_apply_cutter_seams,
    OBJECT_OT_polygroups_select_cutter_planes,
    OBJECT_OT_polygroups_clear_cutter_planes,
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
