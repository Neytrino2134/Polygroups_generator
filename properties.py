import os

import bpy


CUTTER_COLLECTION_NAME = "Seam Cutters"
CUTTER_PROP = "polygroups_object_seam_cutter"
CUTTER_TYPE_PROP = "polygroups_object_seam_cutter_type"
CUTTER_SOLIDIFY_MODIFIER_NAME = "Cutter Plane Thickness"

_PROMPT_COLLECTION_ITEMS = []
_PROMPT_FILE_ITEMS = []


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
    show_import_section: bpy.props.BoolProperty(default=True)
    show_batch_import_section: bpy.props.BoolProperty(default=True)
    show_model_preparation_section: bpy.props.BoolProperty(default=True)
    show_seam_preparation_section: bpy.props.BoolProperty(default=True)
    show_polygroups_section: bpy.props.BoolProperty(default=True)
    show_remesh_section: bpy.props.BoolProperty(default=True)
    show_resculpting_section: bpy.props.BoolProperty(default=True)
    show_seam_finalization_section: bpy.props.BoolProperty(default=True)
    show_uv_preparation_section: bpy.props.BoolProperty(default=True)
    show_baking_section: bpy.props.BoolProperty(default=True)
    show_ai_generation_section: bpy.props.BoolProperty(default=True)


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
    cutter_path_tilt_step_degrees: bpy.props.FloatProperty(
        name="Path Tilt Step",
        description="Tilt angle step applied to selected cutter path curves",
        default=15.0,
        soft_min=-90.0,
        soft_max=90.0,
        precision=1,
    )
    hide_cutters_after_apply: bpy.props.BoolProperty(
        name="Hide Cutters After Apply",
        description="Hide cutter plane objects after applying seams",
        default=True,
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
    prefer_backside_longitudinal_seam: bpy.props.BoolProperty(
        name="Prefer Backside Longitudinal Seam",
        description="Try to place longitudinal seams on the backside relative to the current 3D view",
        default=False,
    )


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
    del bpy.types.Scene.polygroups_seam_finalization_settings
    del bpy.types.Scene.polygroups_generator_settings
    del bpy.types.Scene.polygroups_object_seam_cutter_settings
    del bpy.types.Scene.polygroups_quick_knife_seam_settings
    del bpy.types.Scene.polygroups_seam_preparation_settings
    del bpy.types.Scene.polygroups_knife_seam_settings
    del bpy.types.Scene.polygroups_model_preparation_settings

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
