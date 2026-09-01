import os

import bpy


CUTTER_COLLECTION_NAME = "Seam Cutters"
CUTTER_PROP = "polygroups_object_seam_cutter"
CUTTER_TYPE_PROP = "polygroups_object_seam_cutter_type"
CUTTER_SOLIDIFY_MODIFIER_NAME = "Cutter Plane Thickness"

_PROMPT_COLLECTION_ITEMS = []
_PROMPT_FILE_ITEMS = []
_PANEL_VISIBILITY_UPDATE_LOCK = False

SECTION_VISIBILITY_PROPERTIES = (
    "show_import_section",
    "show_batch_import_section",
    "show_model_preparation_section",
    "show_seam_preparation_section",
    "show_polygroups_section",
    "show_remesh_section",
    "show_resculpting_section",
    "show_seam_finalization_section",
    "show_uv_preparation_section",
    "show_baking_section",
    "show_ai_generation_section",
    "show_mesh_finalization_section",
    "show_render_section",
)


def _set_single_visible_section(settings, visible_property):
    global _PANEL_VISIBILITY_UPDATE_LOCK
    if _PANEL_VISIBILITY_UPDATE_LOCK:
        return

    _PANEL_VISIBILITY_UPDATE_LOCK = True
    try:
        for property_name in SECTION_VISIBILITY_PROPERTIES:
            if property_name != visible_property:
                setattr(settings, property_name, False)
    finally:
        _PANEL_VISIBILITY_UPDATE_LOCK = False


def _panel_visibility_update(property_name):
    def update(self, context):
        del context
        if (
            _PANEL_VISIBILITY_UPDATE_LOCK
            or not self.single_section_mode
            or not getattr(self, property_name)
        ):
            return

        _set_single_visible_section(self, property_name)

    return update


def _normalize_render_output_directory(self, context):
    del context
    value = (self.output_directory or "").strip()
    if value.startswith("//"):
        self["output_directory"] = bpy.path.abspath(value)


def _single_section_mode_update(self, context):
    del context
    if _PANEL_VISIBILITY_UPDATE_LOCK or not self.single_section_mode:
        return

    visible_properties = [
        property_name
        for property_name in SECTION_VISIBILITY_PROPERTIES
        if getattr(self, property_name)
    ]
    if len(visible_properties) > 1:
        _set_single_visible_section(self, visible_properties[0])


def _sync_cutter_solidify_thickness(self, context):
    del context
    collection = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
    if collection is None:
        return

    for obj in collection.objects:
        if obj.type != "MESH" or not obj.get(CUTTER_PROP):
            continue

        modifier = obj.modifiers.get(CUTTER_SOLIDIFY_MODIFIER_NAME)
        if modifier is None:
            modifier = obj.modifiers.new(CUTTER_SOLIDIFY_MODIFIER_NAME, "SOLIDIFY")

        modifier.thickness = self.cutter_solidify_thickness
        modifier.offset = 0.0


def _sync_selected_cutter_path_settings(self, context):
    if context is None:
        return

    for obj in context.selected_objects:
        if obj.type != "CURVE" or not obj.get(CUTTER_PROP) or obj.get(CUTTER_TYPE_PROP) != "PATH":
            continue

        obj.data.resolution_u = self.cutter_path_render_u
        obj.data.render_resolution_u = self.cutter_path_render_u
        obj.data.extrude = self.cutter_path_extrude


def _prompt_collection_items(self, context):
    del context
    from .services import prompt_library

    global _PROMPT_COLLECTION_ITEMS
    names = prompt_library.collection_names()
    if not names:
        names = ["General"]

    _PROMPT_COLLECTION_ITEMS = [
        (name, name, f"{name} prompt collection")
        for name in names
    ]
    return _PROMPT_COLLECTION_ITEMS


def _prompt_file_items(self, context):
    del context
    from .services import prompt_library

    global _PROMPT_FILE_ITEMS
    names = prompt_library.prompt_names(self.prompt_library_collection)
    if not names:
        _PROMPT_FILE_ITEMS = [("__NONE__", "No prompts", "No prompt files found")]
        return _PROMPT_FILE_ITEMS

    _PROMPT_FILE_ITEMS = [
        (name, os.path.splitext(name)[0].replace("_", " ").title(), name)
        for name in names
    ]
    return _PROMPT_FILE_ITEMS


class POLYGROUPS_PG_model_preparation_settings(bpy.types.PropertyGroup):
    weld_distance: bpy.props.FloatProperty(
        name="Weld Distance",
        description="Merge distance for the Weld modifier",
        default=0.0001,
        min=0.0,
        soft_max=0.01,
        precision=5,
    )
    batch_import_directory: bpy.props.StringProperty(
        name="Folder",
        description="Folder with mesh files to import one by one",
        default="",
        subtype="DIR_PATH",
    )
    batch_import_format: bpy.props.EnumProperty(
        name="Format",
        description="Mesh file format for batch import",
        items=(
            ("AUTO", "Auto", "Import supported mesh files by extension"),
            ("USD", "USD", "Import USD, USDA, and USDC files"),
            ("FBX", "FBX", "Import FBX files"),
            ("OBJ", "OBJ", "Import OBJ files"),
            ("STL", "STL", "Import STL files"),
            ("GLB", "GLB", "Import GLB and GLTF files"),
            ("3MF", "3MF", "Import 3MF files"),
        ),
        default="GLB",
    )
    file_import_auto_rename_objects: bpy.props.BoolProperty(
        name="Auto Rename Objects",
        description="Rename selected imported files and move them to the Generated collection",
        default=True,
    )
    file_import_apply_weld: bpy.props.BoolProperty(
        name="Apply Weld",
        description="Apply Weld to mesh objects imported through file selection",
        default=True,
    )
    batch_auto_rename_objects: bpy.props.BoolProperty(
        name="Auto Rename Objects",
        description="Rename imported objects and move them to the Generated collection",
        default=True,
    )
    batch_apply_weld: bpy.props.BoolProperty(
        name="Apply Weld",
        description="Apply Weld to imported mesh objects after each file import",
        default=True,
    )
    batch_include_subfolders: bpy.props.BoolProperty(
        name="Include Subfolders",
        description="Scan and import supported mesh files from nested folders",
        default=False,
    )
    batch_auto_arrange_objects: bpy.props.BoolProperty(
        name="Auto Arrange Imports",
        description="Automatically arrange imported mesh objects after each batch import step",
        default=False,
    )
    batch_arrange_spacing: bpy.props.FloatProperty(
        name="Spacing",
        description="Distance between arranged imported objects",
        default=0.1,
        min=0.0,
        max=1.0,
        precision=2,
        unit="LENGTH",
    )
    batch_arrange_mode: bpy.props.EnumProperty(
        name="Arrange Mode",
        description="How to arrange imported objects on the ZX plane",
        items=(
            ("LINE", "One Row", "Arrange objects in one horizontal row"),
            ("GRID", "Rows", "Arrange objects in a grid with a fixed row count"),
        ),
        default="LINE",
    )
    batch_arrange_rows: bpy.props.IntProperty(
        name="Rows",
        description="Number of rows used when Arrange Mode is Rows",
        default=2,
        min=1,
        soft_max=10,
    )
    batch_is_running: bpy.props.BoolProperty(
        name="Running",
        default=False,
    )
    batch_total_count: bpy.props.IntProperty(
        name="Total",
        default=0,
        min=0,
    )
    batch_imported_count: bpy.props.IntProperty(
        name="Imported Files",
        default=0,
        min=0,
    )
    batch_imported_object_count: bpy.props.IntProperty(
        name="Imported Objects",
        default=0,
        min=0,
    )
    batch_remaining_count: bpy.props.IntProperty(
        name="Remaining",
        default=0,
        min=0,
    )
    batch_import_progress: bpy.props.FloatProperty(
        name="Progress",
        default=0.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
    )
    batch_current_file: bpy.props.StringProperty(
        name="Current File",
        default="",
    )


class AIRETOPO_PG_panel_visibility_settings(bpy.types.PropertyGroup):
    single_section_mode: bpy.props.BoolProperty(
        name="Single Mode",
        description="Keep only one main toolkit section expanded at a time",
        default=False,
        update=_single_section_mode_update,
    )
    show_import_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_import_section"))
    show_batch_import_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_batch_import_section"))
    show_model_preparation_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_model_preparation_section"))
    show_seam_preparation_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_seam_preparation_section"))
    show_polygroups_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_polygroups_section"))
    show_remesh_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_remesh_section"))
    show_resculpting_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_resculpting_section"))
    show_seam_finalization_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_seam_finalization_section"))
    show_uv_preparation_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_uv_preparation_section"))
    show_baking_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_baking_section"))
    show_ai_generation_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_ai_generation_section"))
    show_mesh_finalization_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_mesh_finalization_section"))
    show_render_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_render_section"))


class POLYGROUPS_PG_knife_seam_settings(bpy.types.PropertyGroup):
    stable_view_cut: bpy.props.BoolProperty(
        name="Stable View Cut",
        description="Use a viewport-plane cut that stays continuous on dense meshes when zoomed out",
        default=True,
    )
    use_occlude_geometry: bpy.props.BoolProperty(
        name="Occlude Geometry",
        description="Limit the cut to visible geometry only",
        default=False,
    )
    only_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Only cut currently selected geometry",
        default=False,
    )
    xray: bpy.props.BoolProperty(
        name="X-Ray",
        description="Show the cut through the mesh while drawing",
        default=True,
    )
    mark_seam: bpy.props.BoolProperty(
        name="Mark As Seam",
        description="Mark selected knife-cut edges as seams after confirming the cut",
        default=True,
    )
    clear_selection_after_cutting: bpy.props.BoolProperty(
        name="Clear Selection After Cutting",
        description="Deselect vertices, edges, and faces after post-cut processing",
        default=False,
    )


class POLYGROUPS_PG_seam_preparation_settings(bpy.types.PropertyGroup):
    selection_smooth_iterations: bpy.props.IntProperty(
        name="Smooth Iterations",
        description="Number of smoothing passes for the selected face region",
        default=2,
        min=1,
        max=25,
        soft_max=10,
    )
    seam_gap_max_edges: bpy.props.IntProperty(
        name="Max Gap Edges",
        description="Maximum number of non-seam edges allowed between two seam endpoints",
        default=3,
        min=1,
        max=20,
        soft_max=8,
    )
    seam_gap_max_distance: bpy.props.FloatProperty(
        name="Max Gap Distance",
        description="Maximum distance allowed when matching seam endpoints or short gap paths",
        default=0.02,
        min=0.0,
        soft_max=0.2,
        precision=4,
        unit="LENGTH",
    )
    seam_gap_status: bpy.props.StringProperty(
        name="Seam Gap Status",
        default="Not checked",
    )
    show_knife_seam_settings: bpy.props.BoolProperty(
        name="Knife Seam",
        default=False,
    )
    show_quick_knife_seam_settings: bpy.props.BoolProperty(
        name="Quick Knife Seam",
        default=False,
    )
    show_object_seam_cutter_settings: bpy.props.BoolProperty(
        name="Object Seam Cutter",
        default=False,
    )


class POLYGROUPS_PG_object_seam_cutter_settings(bpy.types.PropertyGroup):
    cutter_size_multiplier: bpy.props.FloatProperty(
        name="Cutter Size",
        description="Cutter plane size relative to the active object's bounding box diagonal",
        default=1.5,
        min=0.1,
        soft_max=5.0,
        precision=2,
    )
    cutter_alpha: bpy.props.FloatProperty(
        name="Cutter Alpha",
        description="Viewport opacity for newly created cutter planes",
        default=0.25,
        min=0.05,
        max=1.0,
        subtype="FACTOR",
    )
    cutter_solidify_thickness: bpy.props.FloatProperty(
        name="Plane Thickness",
        description="Visual Solidify thickness for cutter planes; seam calculation still uses the original center plane",
        default=0.001,
        min=0.0,
        soft_max=0.01,
        precision=5,
        update=_sync_cutter_solidify_thickness,
    )
    cutter_arc_segments: bpy.props.IntProperty(
        name="Cylinder Segments",
        description="Number of segments used for the open arc cylinder cutter",
        default=16,
        min=3,
        max=96,
        soft_max=32,
    )
    cutter_local_ring_segments: bpy.props.IntProperty(
        name="Local Ring Segments",
        description="Number of segments used for local ring cutter disks",
        default=64,
        min=8,
        max=192,
        soft_max=96,
    )
    cutter_local_ring_radius_offset: bpy.props.FloatProperty(
        name="Ring Radius Offset",
        description="Additional world-space radius added to local ring cutters",
        default=0.0,
        soft_min=-1.0,
        soft_max=1.0,
        precision=4,
    )
    cutter_local_ring_fit_mode: bpy.props.EnumProperty(
        name="Ring Fit Mode",
        description="How local ring cutters are oriented and centered",
        items=(
            ("VOLUME", "Snap To Volume", "Use surface hits to estimate the local volume center and orient the ring across the form"),
            ("SURFACE", "Surface Diameter", "Use the two clicked points as a screen-facing surface diameter"),
        ),
        default="VOLUME",
    )
    cutter_apply_method: bpy.props.EnumProperty(
        name="Apply Method",
        description="Method used to apply arc, path, and draw cutter seams",
        items=(
            ("BOOLEAN", "Boolean - faster", "Use the faster boolean union workflow before deleting cutter faces"),
            ("KNIFE", "Knife Intersect - cleaner", "Use Intersect Knife for cleaner cuts before deleting cutter faces"),
        ),
        default="BOOLEAN",
    )
    cutter_mirror_axis: bpy.props.EnumProperty(
        name="Mirror Axis",
        description="Object-mode axis used when copying and mirroring selected cutters",
        items=(
            ("X", "X", "Mirror across the X axis"),
            ("Y", "Y", "Mirror across the Y axis"),
            ("Z", "Z", "Mirror across the Z axis"),
        ),
        default="X",
    )
    cutter_path_render_u: bpy.props.IntProperty(
        name="Path Render U",
        description="Render U resolution for newly created cutter path curves",
        default=20,
        min=1,
        max=128,
        soft_max=64,
        update=_sync_selected_cutter_path_settings,
    )
    cutter_path_extrude: bpy.props.FloatProperty(
        name="Path Extrude",
        description="Visual curve extrude for cutter paths; seam calculation uses the path centerline",
        default=0.015,
        min=0.0,
        soft_max=0.05,
        precision=4,
        update=_sync_selected_cutter_path_settings,
    )
    continue_path_cutters: bpy.props.BoolProperty(
        name="Continue Path Cutters",
        description="Append new cutter paths to nearby existing cutter paths instead of creating separate objects",
        default=True,
    )
    cutter_path_join_distance: bpy.props.FloatProperty(
        name="Path Join Distance",
        description="Maximum distance used when continuing or joining cutter path curves",
        default=0.05,
        min=0.0,
        soft_max=0.5,
        precision=4,
    )
    cutter_draw_min_point_distance: bpy.props.FloatProperty(
        name="Draw Point Distance",
        description="Minimum surface distance between points while drawing cutter strokes",
        default=0.01,
        min=0.0,
        soft_max=0.2,
        precision=4,
    )
    cutter_draw_simplify_distance: bpy.props.FloatProperty(
        name="Draw Simplify",
        description="Optional distance-based simplification applied to cutter paths created with the draw tool",
        default=0.0,
        min=0.0,
        soft_max=0.2,
        precision=4,
    )
    continue_draw_strokes: bpy.props.BoolProperty(
        name="Continue Draw Strokes",
        description="Append new draw strokes to nearby existing draw strokes instead of creating separate objects",
        default=True,
    )
    cutter_draw_join_distance: bpy.props.FloatProperty(
        name="Draw Join Distance",
        description="Maximum distance used when continuing or joining cutter draw strokes",
        default=0.05,
        min=0.0,
        soft_max=0.5,
        precision=4,
    )
    auto_convert_draw_strokes: bpy.props.BoolProperty(
        name="Auto Convert Draw Strokes",
        description="Create a cutter path immediately after finishing a draw stroke",
        default=False,
    )
    delete_draw_strokes_after_convert: bpy.props.BoolProperty(
        name="Delete Draw Strokes After Convert",
        description="Delete source draw stroke objects after converting them to cutter paths",
        default=True,
    )
    auto_convert_draw_strokes_on_apply: bpy.props.BoolProperty(
        name="Auto Convert Draw On Apply",
        description="Convert cutter draw strokes to cutter paths before applying cutter seams",
        default=True,
    )
    hide_cutters_after_apply: bpy.props.BoolProperty(
        name="Hide Cutters After Apply",
        description="Hide cutter plane objects after applying seams",
        default=True,
    )
    fill_split_cutters: bpy.props.BoolProperty(
        name="Fill Cutter",
        description="Fill cut boundary openings after splitting an object with plane or arc cutters",
        default=False,
    )
    delete_cutters_after_apply: bpy.props.BoolProperty(
        name="Delete Cutters After Apply",
        description="Delete cutter plane objects after applying seams",
        default=False,
    )
    last_cutter_count: bpy.props.IntProperty(
        name="Last Cutters",
        default=0,
        min=0,
    )
    last_marked_edge_count: bpy.props.IntProperty(
        name="Last Seams",
        default=0,
        min=0,
    )


class POLYGROUPS_PG_quick_knife_seam_settings(bpy.types.PropertyGroup):
    use_fill: bpy.props.BoolProperty(
        name="Fill",
        description="Fill the cut with a new face",
        default=False,
    )
    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Tolerance for the bisect cut",
        default=0.0001,
        min=0.0,
        soft_max=0.01,
        precision=5,
    )
    mark_seam: bpy.props.BoolProperty(
        name="Mark As Seam",
        description="Mark newly created cut edges as seams",
        default=True,
    )
    clear_selection_after_cutting: bpy.props.BoolProperty(
        name="Clear Selection After Cutting",
        description="Deselect vertices, edges, and faces after the cut",
        default=True,
    )


class POLYGROUPS_PG_polygroups_settings(bpy.types.PropertyGroup):
    material_mode: bpy.props.EnumProperty(
        name="Material Mode",
        description="How generated PolyGroup materials use the source material textures",
        items=(
            ("TEXTURE_ONLY", "Source Texture", "Use the source material texture color"),
            ("TEXTURE_TINT", "Texture + Color", "Multiply source texture color by a random PolyGroup color"),
            ("COLOR_ONLY", "Random Color", "Use random PolyGroup colors without source textures"),
            ("CHECKER_TEXTURE", "Checker Texture", "Use a UV checker texture material"),
        ),
        default="TEXTURE_TINT",
    )
    checker_scale: bpy.props.FloatProperty(
        name="Checker Scale",
        description="Mapping scale for generated checker texture materials",
        default=16.0,
        min=0.01,
        soft_max=100.0,
        precision=2,
    )


class POLYGROUPS_PG_seam_finalization_settings(bpy.types.PropertyGroup):
    auto_unwrap_after_seam: bpy.props.BoolProperty(
        name="Auto Unwrap",
        description="Run Angle Based unwrap on selected faces after final seam operators",
        default=False,
    )
    auto_average_islands_scale_after_unwrap: bpy.props.BoolProperty(
        name="Auto Average Islands Scale",
        description="Average UV island scale after automatic seam unwrap and restore the edit selection",
        default=False,
    )
    prefer_backside_longitudinal_seam: bpy.props.BoolProperty(
        name="Prefer Backside Longitudinal Seam",
        description="Try to place longitudinal seams on the backside relative to the current 3D view",
        default=False,
    )
    double_longitudinal_seam: bpy.props.BoolProperty(
        name="Double Seam",
        description="Create a second longitudinal seam on the opposite side of the selected cylinder or cone",
        default=False,
    )


class POLYGROUPS_PG_mesh_finalization_settings(bpy.types.PropertyGroup):
    show_smart_decimate_settings: bpy.props.BoolProperty(
        name="Decimate",
        default=True,
    )
    show_mesh_check_settings: bpy.props.BoolProperty(
        name="Check Mesh",
        default=True,
    )
    show_all_mesh_fix_operators: bpy.props.BoolProperty(
        name="Show All Fix Operators",
        description="Show all mesh repair operators independently from detected issue categories",
        default=False,
    )
    show_fab_rename_settings: bpy.props.BoolProperty(
        name="FAB Rename",
        default=True,
    )
    show_mesh_export_settings: bpy.props.BoolProperty(
        name="Export",
        default=True,
    )
    smart_decimate_ratio: bpy.props.FloatProperty(
        name="Ratio",
        description="Decimate ratio for non-seam areas",
        default=0.4,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    smart_decimate_duplicate_and_apply: bpy.props.BoolProperty(
        name="Duplicate And Apply Decimate",
        description="Duplicate the active object, add Smart Decimate to the duplicate, and apply it",
        default=True,
    )
    fab_asset_name: bpy.props.StringProperty(
        name="Asset Name",
        description="Base asset name used for FAB/Unreal object, material, and texture names",
        default="Asset",
        options={"TEXTEDIT_UPDATE"},
    )
    fab_asset_index: bpy.props.StringProperty(
        name="Index",
        description="Optional asset index inserted into FAB/Unreal names",
        default="01",
        options={"TEXTEDIT_UPDATE"},
    )
    fab_auto_increment_index: bpy.props.BoolProperty(
        name="Auto Increment Index",
        description="Increase the numeric index after a successful FAB rename operation",
        default=True,
    )
    fab_copy_textures: bpy.props.BoolProperty(
        name="Copy Textures",
        description="Copy external material textures to a Textures folder next to the blend file",
        default=True,
    )
    fab_collection_color_tag: bpy.props.EnumProperty(
        name="Collection Color Tag",
        description="Color tag assigned to the final FAB collection",
        items=(
            ("NONE", "None", "Do not assign a collection color tag"),
            ("COLOR_01", "Color 1", "Assign collection color tag 1"),
            ("COLOR_02", "Color 2", "Assign collection color tag 2"),
            ("COLOR_03", "Color 3", "Assign collection color tag 3"),
            ("COLOR_04", "Color 4", "Assign collection color tag 4"),
            ("COLOR_05", "Color 5", "Assign collection color tag 5"),
            ("COLOR_06", "Color 6", "Assign collection color tag 6"),
            ("COLOR_07", "Color 7", "Assign collection color tag 7"),
            ("COLOR_08", "Color 8", "Assign collection color tag 8"),
        ),
        default="COLOR_04",
    )
    mesh_export_format: bpy.props.EnumProperty(
        name="Export Format",
        description="File format used by Export Selected Meshes",
        items=(
            ("FBX", "FBX", "Export one FBX file per selected mesh"),
            ("GLB", "GLB", "Export one binary GLB file per selected mesh"),
            ("GLTF", "GLTF", "Export one embedded GLTF file per selected mesh"),
        ),
        default="FBX",
    )
    blend_export_directory: bpy.props.StringProperty(
        name="Blend Output",
        description="Folder used for exported asset blend files",
        default="//!Blend",
        subtype="DIR_PATH",
    )
    blend_export_static_collections: bpy.props.StringProperty(
        name="Static Collections",
        description="Comma-separated collection names copied into every individual asset blend file",
        default="",
    )
    blend_export_static_collection_picker: bpy.props.PointerProperty(
        name="Static Collection",
        description="Collection picked from the scene and added to the static export list",
        type=bpy.types.Collection,
    )
    blend_export_individual_assets: bpy.props.BoolProperty(
        name="Individual Assets",
        description="Export one blend file for every *_Collection asset collection",
        default=True,
    )
    blend_export_all_low: bpy.props.BoolProperty(
        name="All LOW",
        description="Export one blend file containing all *_LOW objects",
        default=True,
    )
    blend_export_all_mid: bpy.props.BoolProperty(
        name="All MID",
        description="Export one blend file containing all *_MID objects",
        default=True,
    )
    blend_export_include_render_settings: bpy.props.BoolProperty(
        name="Render Settings",
        description="Copy world, render, camera, color management, and unit settings into exported blend files",
        default=True,
    )
    blend_export_overwrite_existing: bpy.props.BoolProperty(
        name="Overwrite Existing",
        description="Overwrite existing blend export files",
        default=True,
    )
    blend_export_collection_count: bpy.props.IntProperty(name="Blend Collections", default=0, min=0)
    blend_export_low_count: bpy.props.IntProperty(name="LOW Objects", default=0, min=0)
    blend_export_mid_count: bpy.props.IntProperty(name="MID Objects", default=0, min=0)
    blend_export_file_count: bpy.props.IntProperty(name="Blend Files", default=0, min=0)
    blend_export_status: bpy.props.StringProperty(
        name="Blend Export Status",
        default="Not scanned",
    )
    mesh_check_status: bpy.props.StringProperty(
        name="Mesh Check Status",
        default="Not checked",
    )
    mesh_check_inconsistent_normals: bpy.props.IntProperty(default=0, min=0)
    mesh_check_inward_normals: bpy.props.IntProperty(default=0, min=0)
    mesh_check_ngons: bpy.props.IntProperty(default=0, min=0)
    mesh_check_nonmanifold_edges: bpy.props.IntProperty(default=0, min=0)
    mesh_check_boundary_edges: bpy.props.IntProperty(default=0, min=0)
    mesh_check_boundary_loops: bpy.props.IntProperty(default=0, min=0)
    mesh_check_loose_vertices: bpy.props.IntProperty(default=0, min=0)
    mesh_check_loose_edges: bpy.props.IntProperty(default=0, min=0)
    mesh_check_zero_area_faces: bpy.props.IntProperty(default=0, min=0)
    mesh_check_duplicate_vertices: bpy.props.IntProperty(default=0, min=0)
    mesh_check_thin_protrusions: bpy.props.IntProperty(default=0, min=0)


class POLYGROUPS_PG_render_settings(bpy.types.PropertyGroup):
    render_engine: bpy.props.EnumProperty(
        name="Render Engine",
        description="Render engine used for batch asset previews",
        items=(
            ("CYCLES", "Cycles", "Render with Cycles"),
            ("EEVEE", "Eevee", "Render with Eevee"),
        ),
        default="CYCLES",
    )
    max_samples: bpy.props.IntProperty(
        name="Max Samples",
        description="Maximum render samples for the selected engine",
        default=64,
        min=1,
        max=4096,
        soft_max=512,
    )
    resolution_x: bpy.props.IntProperty(
        name="Resolution X",
        description="Render resolution width",
        default=1024,
        min=16,
        max=16384,
        soft_max=4096,
    )
    resolution_y: bpy.props.IntProperty(
        name="Resolution Y",
        description="Render resolution height",
        default=1024,
        min=16,
        max=16384,
        soft_max=4096,
    )
    resolution_scale: bpy.props.IntProperty(
        name="Resolution Scale",
        description="Render resolution percentage scale",
        default=100,
        min=1,
        max=400,
        subtype="PERCENTAGE",
    )
    output_directory: bpy.props.StringProperty(
        name="Output Folder",
        description="Base folder for render output",
        default="//!Renders",
        subtype="DIR_PATH",
        update=_normalize_render_output_directory,
    )
    render_low: bpy.props.BoolProperty(
        name="Render LOW",
        description="Include *_LOW objects in the render queue",
        default=True,
    )
    render_mid: bpy.props.BoolProperty(
        name="Render MID",
        description="Include *_MID objects in the render queue",
        default=True,
    )
    skip_existing: bpy.props.BoolProperty(
        name="Skip Existing",
        description="Skip render files that already exist",
        default=True,
    )
    overwrite_existing: bpy.props.BoolProperty(
        name="Overwrite Existing",
        description="Overwrite existing render files instead of making Blender ask",
        default=True,
    )
    transparent_background: bpy.props.BoolProperty(
        name="Transparent Background",
        description="Render with transparent film and hide scene/background collections during each job",
        default=False,
    )
    scene_collection_prefix: bpy.props.StringProperty(
        name="Scene Collection Prefix",
        description="Scene/background collection prefix hidden during transparent renders",
        default="Scene",
    )
    multiview_render: bpy.props.BoolProperty(
        name="Multi View",
        description="Render temporary front, back, and side views of each asset together",
        default=False,
    )
    multiview_offset: bpy.props.FloatProperty(
        name="Multi View Offset",
        description="World-space X offset used for temporary multi view duplicates",
        default=0.7,
        min=0.0,
        soft_max=5.0,
        precision=3,
        unit="LENGTH",
    )
    freestyle_edges: bpy.props.BoolProperty(
        name="Freestyle Edges",
        description="Render Freestyle edge marks for LOW/MID asset objects",
        default=False,
    )
    freestyle_as_render_pass: bpy.props.BoolProperty(
        name="As Render Pass",
        description="Save Freestyle edges as a separate pass image instead of compositing them into the asset render",
        default=True,
    )
    freestyle_line_thickness: bpy.props.FloatProperty(
        name="Line Thickness",
        description="Absolute Freestyle line thickness in pixels",
        default=0.1,
        min=0.01,
        soft_max=5.0,
        precision=3,
    )
    freestyle_line_color: bpy.props.FloatVectorProperty(
        name="Line Color",
        description="Freestyle line color",
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        size=4,
        subtype="COLOR",
    )
    queue_data: bpy.props.StringProperty(
        name="Render Queue Data",
        default="[]",
        options={"HIDDEN"},
    )
    queue_index: bpy.props.IntProperty(
        name="Queue Index",
        default=0,
        min=0,
        options={"HIDDEN"},
    )
    total_count: bpy.props.IntProperty(name="Queued", default=0, min=0)
    rendered_count: bpy.props.IntProperty(name="Rendered", default=0, min=0)
    remaining_count: bpy.props.IntProperty(name="Remaining", default=0, min=0)
    collection_count: bpy.props.IntProperty(name="Collections", default=0, min=0)
    current_collection: bpy.props.StringProperty(name="Current Collection", default="")
    current_object: bpy.props.StringProperty(name="Current Object", default="")
    last_output_path: bpy.props.StringProperty(name="Last Output", default="", subtype="FILE_PATH")
    status: bpy.props.StringProperty(name="Status", default="Not scanned")
    is_running: bpy.props.BoolProperty(name="Running", default=False)
    stop_requested: bpy.props.BoolProperty(name="Stop Requested", default=False, options={"HIDDEN"})


class POLYGROUPS_PG_baking_settings(bpy.types.PropertyGroup):
    bake_resolution: bpy.props.IntProperty(
        name="Bake Resolution",
        description="Width and height for generated bake images",
        default=2048,
        min=16,
        max=16384,
        soft_max=8192,
    )
    bake_margin: bpy.props.IntProperty(
        name="Bake Margin",
        description="Bake margin in pixels",
        default=16,
        min=0,
        max=256,
    )
    ray_distance: bpy.props.FloatProperty(
        name="Ray Distance",
        description="Maximum ray distance for selected-to-active baking",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        step=0.5,
        precision=4,
    )
    cage_extrusion: bpy.props.FloatProperty(
        name="Cage Extrusion",
        description="Cage extrusion for selected-to-active baking",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        step=0.5,
        precision=4,
    )
    use_auto_cage: bpy.props.BoolProperty(
        name="AutoCage",
        description="Automatically calculate cage extrusion from selected highpoly and active lowpoly before baking",
        default=False,
    )
    auto_cage_coverage: bpy.props.FloatProperty(
        name="Coverage",
        description="Highpoly surface coverage percentile used for automatic cage extrusion",
        default=95.0,
        min=90.0,
        max=99.8,
        precision=1,
        subtype="PERCENTAGE",
    )
    auto_cage_margin: bpy.props.FloatProperty(
        name="Safety Margin",
        description="Fixed extra distance added to the automatic cage extrusion",
        default=0.001,
        min=0.0,
        soft_max=0.02,
        precision=5,
        unit="LENGTH",
    )
    auto_cage_margin_percent: bpy.props.FloatProperty(
        name="Size Margin",
        description="Object-size relative margin added to the automatic cage extrusion",
        default=0.001,
        min=0.0,
        max=0.05,
        precision=4,
        subtype="FACTOR",
    )
    auto_cage_safe_zone: bpy.props.FloatProperty(
        name="Safe Zone",
        description="Extra percentage added on top of the calculated automatic cage extrusion",
        default=3.0,
        min=0.0,
        max=10.0,
        precision=1,
        subtype="PERCENTAGE",
    )
    auto_cage_max: bpy.props.FloatProperty(
        name="Max Cage",
        description="Maximum allowed automatic cage extrusion; 0 disables the limit",
        default=0.05,
        min=0.0,
        soft_max=1.0,
        precision=4,
        unit="LENGTH",
    )
    auto_cage_sample_limit: bpy.props.IntProperty(
        name="Samples",
        description="Maximum highpoly sample points used for AutoCage analysis",
        default=10000,
        min=100,
        max=200000,
        soft_max=50000,
    )
    auto_cage_status: bpy.props.StringProperty(
        name="AutoCage Status",
        default="Not calculated",
    )
    image_prefix: bpy.props.StringProperty(
        name="Image Prefix",
        description="Prefix for generated bake images",
        default="Bake_Temp",
    )
    use_selected_to_active: bpy.props.BoolProperty(
        name="Selected To Active",
        description="Bake from selected source meshes to the active target mesh",
        default=True,
    )
    bake_base_color: bpy.props.BoolProperty(
        name="Base Color",
        description="Bake source Base Color to the active target",
        default=True,
    )
    bake_normal: bpy.props.BoolProperty(
        name="Normal",
        description="Bake source normals to the active target",
        default=True,
    )
    auto_save_textures_after_bake: bpy.props.BoolProperty(
        name="Auto Save Textures After Bake",
        description="Run Save Textures automatically after Prepare And Bake finishes",
        default=True,
    )


class POLYGROUPS_PG_resculpting_settings(bpy.types.PropertyGroup):
    multires_levels: bpy.props.IntProperty(
        name="Multires Levels",
        description="Subdivision levels to create on the active lowpoly mesh",
        default=2,
        min=0,
        max=6,
        soft_max=3,
    )
    shrinkwrap_limit: bpy.props.FloatProperty(
        name="Shrinkwrap Limit",
        description="Projection limit for the Shrinkwrap modifier",
        default=0.01,
        min=0.0,
        soft_max=0.1,
        precision=4,
        unit="LENGTH",
    )
    shrinkwrap_offset: bpy.props.FloatProperty(
        name="Shrinkwrap Offset",
        description="Surface offset for the Shrinkwrap modifier",
        default=0.0,
        soft_min=-0.1,
        soft_max=0.1,
        precision=4,
        unit="LENGTH",
    )


class AIRETOPO_PG_ai_generation_settings(bpy.types.PropertyGroup):
    show_prompt_library_settings: bpy.props.BoolProperty(
        name="Prompt Library",
        default=True,
    )
    prompt_library_collection: bpy.props.EnumProperty(
        name="Collection",
        description="Prompt library collection",
        items=_prompt_collection_items,
    )
    prompt_library_prompt: bpy.props.EnumProperty(
        name="Prompt",
        description="Prompt text file from the selected collection",
        items=_prompt_file_items,
    )
    prompt_library_status: bpy.props.StringProperty(
        name="Prompt Library Status",
        default="",
    )
    show_openai_image_settings: bpy.props.BoolProperty(
        name="OpenAI Image",
        default=True,
    )
    show_google_image_settings: bpy.props.BoolProperty(
        name="Google Image",
        default=False,
    )
    prompt: bpy.props.StringProperty(
        name="Prompt",
        description="Prompt for OpenAI image generation",
        default="",
        options={"TEXTEDIT_UPDATE"},
    )
    model: bpy.props.EnumProperty(
        name="Model",
        description="OpenAI image generation model",
        items=(
            ("gpt-image-2", "gpt-image-2", "State-of-the-art image generation model"),
            ("gpt-image-1", "gpt-image-1", "High quality image generation model"),
            ("gpt-image-1-mini", "gpt-image-1-mini", "Faster and lower cost image generation model"),
        ),
        default="gpt-image-1",
    )
    size: bpy.props.EnumProperty(
        name="Size",
        description="Generated image size",
        items=(
            ("1024x1024", "1024 x 1024", "Square image"),
            ("1024x1536", "1024 x 1536", "Portrait image"),
            ("1536x1024", "1536 x 1024", "Landscape image"),
        ),
        default="1024x1024",
    )
    quality: bpy.props.EnumProperty(
        name="Quality",
        description="Generated image quality",
        items=(
            ("auto", "Auto", "Let the API choose the quality"),
            ("low", "Low", "Lower quality and faster generation"),
            ("medium", "Medium", "Balanced quality"),
            ("high", "High", "Higher quality"),
        ),
        default="auto",
    )
    output_format: bpy.props.EnumProperty(
        name="Output Format",
        description="Generated image file format",
        items=(
            ("png", "PNG", "Save generated images as PNG"),
            ("jpeg", "JPEG", "Save generated images as JPEG"),
            ("webp", "WebP", "Save generated images as WebP"),
        ),
        default="png",
    )
    input_image_name: bpy.props.StringProperty(
        name="Input Image",
        description="Optional Blender image to send with the prompt as editing context",
        default="",
    )
    is_generating: bpy.props.BoolProperty(
        name="Generating",
        default=False,
    )
    last_status: bpy.props.StringProperty(
        name="Status",
        default="",
    )
    last_image_name: bpy.props.StringProperty(
        name="Last Image",
        default="",
    )
    last_image_path: bpy.props.StringProperty(
        name="Last Image Path",
        default="",
        subtype="FILE_PATH",
    )


class AIRETOPO_PG_google_image_settings(bpy.types.PropertyGroup):
    prompt: bpy.props.StringProperty(
        name="Prompt",
        description="Prompt for Google Gemini image generation",
        default="",
        options={"TEXTEDIT_UPDATE"},
    )
    model: bpy.props.EnumProperty(
        name="Model",
        description="Google Gemini image generation model",
        items=(
            ("gemini-3.1-flash-image", "Gemini 3.1 Flash Image", "Nano Banana 2 general image generation model"),
            ("gemini-3.1-flash-lite-image", "Gemini 3.1 Flash Lite Image", "Nano Banana 2 Lite fast and low-cost image model"),
            ("gemini-3-pro-image", "Gemini 3 Pro Image", "Nano Banana Pro premium image generation model"),
            ("gemini-2.5-flash-image", "Gemini 2.5 Flash Image", "Legacy Nano Banana image model"),
        ),
        default="gemini-3.1-flash-image",
    )
    aspect_ratio: bpy.props.EnumProperty(
        name="Aspect Ratio",
        description="Generated image aspect ratio",
        items=(
            ("1:1", "1:1", "Square"),
            ("2:3", "2:3", "Portrait"),
            ("3:2", "3:2", "Landscape"),
            ("3:4", "3:4", "Portrait"),
            ("4:3", "4:3", "Landscape"),
            ("4:5", "4:5", "Portrait"),
            ("5:4", "5:4", "Landscape"),
            ("9:16", "9:16", "Vertical"),
            ("16:9", "16:9", "Widescreen"),
            ("21:9", "21:9", "Ultrawide"),
        ),
        default="1:1",
    )
    image_size: bpy.props.EnumProperty(
        name="Image Size",
        description="Generated image size class",
        items=(
            ("1K", "1K", "Standard image size"),
            ("2K", "2K", "High image size"),
            ("4K", "4K", "Ultra image size"),
        ),
        default="1K",
    )
    output_format: bpy.props.EnumProperty(
        name="Save Format",
        description="File format used when saving generated Google images from Blender",
        items=(
            ("png", "PNG", "Save generated images as PNG"),
            ("jpeg", "JPEG", "Save generated images as JPEG"),
            ("webp", "WebP", "Save generated images as WebP"),
        ),
        default="png",
    )
    input_image_name: bpy.props.StringProperty(
        name="Input Image",
        description="Optional Blender image to send with the prompt as editing context",
        default="",
    )
    is_generating: bpy.props.BoolProperty(
        name="Generating",
        default=False,
    )
    last_status: bpy.props.StringProperty(
        name="Status",
        default="",
    )
    last_image_name: bpy.props.StringProperty(
        name="Last Image",
        default="",
    )
    last_image_path: bpy.props.StringProperty(
        name="Last Image Path",
        default="",
        subtype="FILE_PATH",
    )


CLASSES = (
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
