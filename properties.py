"""Compatibility imports and ordered Blender RNA registration."""

from .settings.callbacks import (
    AUTOWELD_MODIFIER_NAME,
    BATCH_REMESH_UNWRAP_METHOD_ITEMS,
    CUTTER_COLLECTION_NAME,
    CUTTER_PROP,
    CUTTER_SOLIDIFY_MODIFIER_NAME,
    CUTTER_TYPE_PROP,
    IMPORT_AUTO_UNWRAP_METHOD_ITEMS,
    IMPORT_REMESH_METHOD_ITEMS,
    PALETTE_PROPERTY_CLASSES,
    REMESH_PRESET_ITEMS,
    RenderPaletteGroup,
    SECTION_SUBSECTION_PROPERTIES,
    SECTION_VISIBILITY_PROPERTIES,
    SUBSECTION_VISIBILITY_PROPERTIES,
    _PANEL_VISIBILITY_UPDATE_LOCK,
    _PROMPT_COLLECTION_ITEMS,
    _PROMPT_FILE_ITEMS,
    _auto_cage_mode_update,
    _import_auto_remesh_update,
    _island_selector_tool_icon_update,
    _normalize_render_output_directory,
    _panel_visibility_update,
    _prompt_collection_items,
    _prompt_file_items,
    _redraw_view3d,
    _render_lod_update,
    _render_low_update,
    _seam_tool_icon_update,
    _set_single_visible_section,
    _single_section_mode_update,
    _small_islands_tool_icon_update,
    _smart_cage_mode_update,
    _smart_cage_strength_get,
    _smart_cage_strength_set,
    _sync_cutter_autoweld_distance,
    _sync_cutter_extrude,
    _sync_cutter_solidify_thickness,
    _sync_cutter_thickness,
    _sync_selected_cutter_path_settings,
    _update_batch_smart_decimate,
    _update_batch_smart_lods,
    _update_render_resolution_preset,
    _update_studio_backdrop,
    _update_studio_color_tag,
    _update_unity_name_index,
    bpy,
    os,
    preset_resolution,
    radians,
)

from .settings.preparation import (
    POLYGROUPS_PG_model_preparation_settings,
    POLYGROUPS_PG_remesh_status,
    AIRETOPO_PG_panel_visibility_settings,
)

from .settings.seams import (
    POLYGROUPS_PG_knife_seam_settings,
    POLYGROUPS_PG_seam_preparation_settings,
    POLYGROUPS_PG_object_seam_cutter_settings,
    POLYGROUPS_PG_quick_knife_seam_settings,
    POLYGROUPS_PG_polygroups_settings,
)

from .settings.finalization import (
    POLYGROUPS_PG_seam_finalization_settings,
    POLYGROUPS_PG_mesh_finalization_settings,
)

from .settings.render import (
    POLYGROUPS_PG_render_settings,
)

from .settings.baking import (
    POLYGROUPS_PG_baking_settings,
    POLYGROUPS_PG_resculpting_settings,
)

from .settings.ai import (
    AIRETOPO_PG_openai_text_settings,
    AIRETOPO_PG_google_text_settings,
    AIRETOPO_PG_ai_generation_settings,
    AIRETOPO_PG_google_image_settings,
)



CLASSES = (
    AIRETOPO_PG_openai_text_settings,
    AIRETOPO_PG_google_text_settings,
    *PALETTE_PROPERTY_CLASSES,
    POLYGROUPS_PG_remesh_status,
    AIRETOPO_PG_panel_visibility_settings,
    POLYGROUPS_PG_model_preparation_settings,
    POLYGROUPS_PG_knife_seam_settings,
    POLYGROUPS_PG_seam_preparation_settings,
    POLYGROUPS_PG_quick_knife_seam_settings,
    POLYGROUPS_PG_object_seam_cutter_settings,
    POLYGROUPS_PG_polygroups_settings,
    POLYGROUPS_PG_seam_finalization_settings,
    POLYGROUPS_PG_mesh_finalization_settings,
    POLYGROUPS_PG_render_settings,
    POLYGROUPS_PG_baking_settings,
    POLYGROUPS_PG_resculpting_settings,
    AIRETOPO_PG_ai_generation_settings,
    AIRETOPO_PG_google_image_settings,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.airetopo_openai_text_settings = bpy.props.PointerProperty(type=AIRETOPO_PG_openai_text_settings)
    bpy.types.Scene.airetopo_google_text_settings = bpy.props.PointerProperty(type=AIRETOPO_PG_google_text_settings)

    bpy.types.Scene.polygroups_remesh_status = bpy.props.PointerProperty(type=POLYGROUPS_PG_remesh_status)

    bpy.types.Scene.airetopo_panel_visibility_settings = bpy.props.PointerProperty(
        type=AIRETOPO_PG_panel_visibility_settings,
    )
    bpy.types.Scene.polygroups_model_preparation_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_model_preparation_settings,
    )
    bpy.types.Scene.polygroups_knife_seam_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_knife_seam_settings,
    )
    bpy.types.Scene.polygroups_seam_preparation_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_seam_preparation_settings,
    )
    bpy.types.Scene.polygroups_quick_knife_seam_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_quick_knife_seam_settings,
    )
    bpy.types.Scene.polygroups_object_seam_cutter_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_object_seam_cutter_settings,
    )
    bpy.types.Scene.polygroups_generator_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_polygroups_settings,
    )
    bpy.types.Scene.polygroups_seam_finalization_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_seam_finalization_settings,
    )
    bpy.types.Scene.polygroups_mesh_finalization_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_mesh_finalization_settings,
    )
    bpy.types.Scene.polygroups_render_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_render_settings,
    )
    bpy.types.Scene.polygroups_baking_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_baking_settings,
    )
    bpy.types.Scene.polygroups_resculpting_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_resculpting_settings,
    )
    bpy.types.Scene.airetopo_ai_generation_settings = bpy.props.PointerProperty(
        type=AIRETOPO_PG_ai_generation_settings,
    )
    bpy.types.Scene.airetopo_google_image_settings = bpy.props.PointerProperty(
        type=AIRETOPO_PG_google_image_settings,
    )


def unregister():
    del bpy.types.Scene.airetopo_openai_text_settings
    del bpy.types.Scene.airetopo_google_text_settings
    del bpy.types.Scene.polygroups_remesh_status
    del bpy.types.Scene.airetopo_panel_visibility_settings
    del bpy.types.Scene.airetopo_google_image_settings
    del bpy.types.Scene.airetopo_ai_generation_settings
    del bpy.types.Scene.polygroups_resculpting_settings
    del bpy.types.Scene.polygroups_baking_settings
    del bpy.types.Scene.polygroups_render_settings
    del bpy.types.Scene.polygroups_mesh_finalization_settings
    del bpy.types.Scene.polygroups_seam_finalization_settings
    del bpy.types.Scene.polygroups_generator_settings
    del bpy.types.Scene.polygroups_object_seam_cutter_settings
    del bpy.types.Scene.polygroups_quick_knife_seam_settings
    del bpy.types.Scene.polygroups_seam_preparation_settings
    del bpy.types.Scene.polygroups_knife_seam_settings
    del bpy.types.Scene.polygroups_model_preparation_settings

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
