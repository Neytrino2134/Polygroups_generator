"""Render workflow RNA property groups."""
from .callbacks import (
    RenderPaletteGroup,
    _normalize_render_output_directory,
    _render_lod_update,
    _render_low_update,
    _update_render_resolution_preset,
    _update_studio_backdrop,
    _update_studio_color_tag,
    bpy,
)


class POLYGROUPS_PG_render_settings(bpy.types.PropertyGroup):
    image_format: bpy.props.EnumProperty(name="Image Format",
        items=(("PNG", "PNG", "PNG image"), ("JPEG", "JPEG", "JPEG image"),
               ("WEBP", "WebP", "WebP image")), default="PNG")
    animation_views_image_format: bpy.props.EnumProperty(name="Four Views Image Format",
        items=(("PNG", "PNG", "PNG image"), ("JPEG", "JPEG", "JPEG image"),
               ("WEBP", "WebP", "WebP image")), default="WEBP")
    texture_render_mode: bpy.props.EnumProperty(
        name="Texture Render Mode",
        items=(("SEPARATE", "Separate", "Render Base Color and Normal as separate images"),
               ("COMBINED", "Together", "Render both texture planes in one image and one pass"),
               ("BOTH", "Separate + Together", "Save separate images and an additional combined image")),
        default="SEPARATE",
    )
    palette_groups: bpy.props.CollectionProperty(type=RenderPaletteGroup)
    palette_group_index: bpy.props.IntProperty(default=0, min=0)
    palette_library_initialized: bpy.props.BoolProperty(default=False)
    studio_backdrop: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_camera: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_camera_aim: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_light_position: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_camera_position: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_scene_position: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_key: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_key_aim: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_fill: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_fill_aim: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_rim: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_rim_aim: bpy.props.PointerProperty(type=bpy.types.Object)
    studio_collection_color_tag: bpy.props.EnumProperty(
        name="Collection Color Tag",
        items=[("NONE", "None", "No color tag")] + [
            (f"COLOR_{index:02d}", f"Color {index}", f"Collection color tag {index}")
            for index in range(1, 9)],
        default="COLOR_08", update=_update_studio_color_tag,
    )
    studio_move_step: bpy.props.FloatProperty(
        name="Movement Step (m)",
        description="Movement distance in metres for all studio arrow buttons",
        default=0.1, min=0.001, soft_max=10, precision=3,
    )
    studio_width: bpy.props.FloatProperty(name="Width", default=20, min=0.1, soft_max=20, unit="LENGTH", update=_update_studio_backdrop)
    studio_depth: bpy.props.FloatProperty(name="Depth", default=8, min=0.1, soft_max=20, unit="LENGTH", update=_update_studio_backdrop)
    studio_height: bpy.props.FloatProperty(name="Height", default=5, min=0.1, soft_max=20, unit="LENGTH", update=_update_studio_backdrop)
    studio_distance: bpy.props.FloatProperty(name="Distance", default=3, min=0.1, soft_max=20, unit="LENGTH", update=_update_studio_backdrop)
    studio_radius: bpy.props.FloatProperty(name="Radius", default=1, min=0.001, soft_max=20, unit="LENGTH", update=_update_studio_backdrop)
    studio_color: bpy.props.FloatVectorProperty(name="Background Color", subtype="COLOR", size=3, default=(0.18, 0.18, 0.18), min=0, max=1, update=_update_studio_backdrop)

    animation_frame_count: bpy.props.IntProperty(
        name="Animation Length",
        description="Last frame and total turnaround animation length",
        default=300,
        min=2,
        soft_max=1200,
    )
    animation_fps: bpy.props.IntProperty(
        name="Frame Rate",
        description="Frames per second for the turnaround animation",
        default=30,
        min=1,
        max=240,
    )
    animation_quality: bpy.props.EnumProperty(
        name="Video Quality",
        description="Constant-rate quality for the encoded video",
        items=(("PERC_LOSSLESS", "Perceptually Lossless", "Highest practical quality"),
               ("HIGH", "High", "High quality and moderate file size"),
               ("MEDIUM", "Medium", "Balanced quality and file size")),
        default="HIGH",
    )
    animation_keep_scene_collections: bpy.props.BoolProperty(
        name="Keep Scene/Light/Camera Collections",
        description="Keep collections starting with Scene, Light, or Camera and all their contents visible during animation rendering",
        default=True,
    )
    animation_media_type: bpy.props.EnumProperty(
        name="Media Type",
        description="Save the animation as a video or a PNG image sequence",
        items=(("VIDEO", "Video", "Encode a video file"),
               ("IMAGE", "Image Sequence", "Save one PNG image per frame")),
        default="VIDEO",
    )
    animation_container: bpy.props.EnumProperty(
        name="Video Container",
        description="Container for the rendered animation video",
        items=(("MKV", "Matroska", "Matroska video (.mkv)"),
               ("MPEG4", "MPEG-4", "MPEG-4 video (.mp4)"),
               ("WEBM", "WebM", "WebM video (.webm)"),
               ("QUICKTIME", "QuickTime", "QuickTime video (.mov)")),
        default="MPEG4",
    )
    animation_delete_collection_after_render: bpy.props.BoolProperty(
        name="Delete Turnaround Collection After Render",
        description="Delete the prepared Turnaround Animation collection after a successful animation render",
        default=True,
    )
    animation_collection_name: bpy.props.StringProperty(default="", options={"HIDDEN"})
    animation_object_name: bpy.props.StringProperty(default="", options={"HIDDEN"})
    animation_status: bpy.props.StringProperty(name="Animation Status", default="Not prepared")
    animation_last_output: bpy.props.StringProperty(name="Animation Output", default="", subtype="FILE_PATH")
    animation_progress: bpy.props.FloatProperty(
        name="Animation Progress", default=0.0, min=0.0, max=100.0,
        subtype="PERCENTAGE", options={"SKIP_SAVE"},
    )
    render_arrange_spacing: bpy.props.FloatProperty(
        name="Spacing", description="Distance between arranged objects",
        default=0.1, min=0.0, max=1.0, precision=2, unit="LENGTH",
    )
    render_arrange_secondary_spacing: bpy.props.FloatProperty(
        name="Secondary Spacing", description="Distance between rows along Y or Z",
        default=0.1, min=0.0, max=1.0, precision=2, unit="LENGTH",
    )
    render_arrange_mode: bpy.props.EnumProperty(
        name="Arrange Mode", description="How to arrange objects",
        items=(("LINE", "One Row", "Arrange objects in one row"),
               ("GRID", "Rows", "Arrange objects in a grid")),
        default="LINE",
    )
    render_arrange_rows: bpy.props.IntProperty(
        name="Rows", description="Number of rows used in Rows mode",
        default=2, min=1, max=50, soft_max=50,
    )
    render_arrange_plane: bpy.props.EnumProperty(
        name="Plane", description="Plane for arranging objects",
        items=(("ZX", "ZX - Camera", "Arrange along X and Z"),
               ("XY", "XY - Floor", "Arrange along X and Y")),
        default="ZX",
    )
    render_arrange_alignment: bpy.props.EnumProperty(
        name="Alignment", description="Reference used to position objects",
        items=(("BOUNDS", "Object Bounds", "Keep spacing between object bounds"),
               ("ORIGIN", "Object Origins", "Align origins to an evenly spaced grid")),
        default="BOUNDS",
    )
    render_engine: bpy.props.EnumProperty(
        name="Render Engine",
        description="Render engine used for batch asset previews",
        items=(
            ("CYCLES", "Cycles", "Render with Cycles"),
            ("EEVEE", "Eevee", "Render with Eevee"),
        ),
        default="EEVEE",
    )
    max_samples: bpy.props.IntProperty(
        name="Max Samples",
        description="Maximum render samples for the selected engine",
        default=64,
        min=1,
        max=4096,
        soft_max=512,
    )
    resolution_aspect_preset: bpy.props.EnumProperty(
        name="Aspect Ratio",
        description="Aspect ratio used when selecting a resolution preset",
        items=(("SQUARE", "1:1", "Square"),
               ("WIDE", "16:9", "Widescreen"),
               ("PORTRAIT", "3:4", "Portrait")),
        default="SQUARE",
        update=_update_render_resolution_preset,
    )
    resolution_size_preset: bpy.props.EnumProperty(
        name="Resolution Preset",
        description="Resolution along the longest image side",
        items=(("1K", "1K", "1024 pixels on the longest side"),
               ("2K", "2K", "2048 pixels on the longest side"),
               ("4K", "4K", "4096 pixels on the longest side")),
        default="1K",
        update=_update_render_resolution_preset,
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
        update=_render_low_update,
    )
    render_high: bpy.props.BoolProperty(name="HIGH", description="Render SM_*_HIGH meshes", default=False)
    render_rename_suffix: bpy.props.EnumProperty(name="Suffix", items=[
        ('HIGH', '_HIGH', ''), ('MID', '_MID', ''), ('LOW', '_LOW', '')], default='HIGH')
    render_lod_enabled: bpy.props.BoolProperty(name="LOD", default=False,
        description="Render one LOD instead of LOW, using LOW image filenames", update=_render_lod_update)
    render_lod_level: bpy.props.EnumProperty(name="LOD Level",
        items=[(f'LOD{i}', f'LOD{i}', f'Render LOD{i} as LOW') for i in range(6)],
        default='LOD0', update=_render_lod_update)
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
        description="Render an additional transparent PNG for each job while keeping the main scene render",
        default=False,
    )
    scene_collection_prefix: bpy.props.StringProperty(
        name="Scene Collection Prefix",
        description="Scene/background collection prefix hidden during transparent renders",
        default="Scene",
    )
    multiview_render: bpy.props.BoolProperty(
        name="Multi View",
        description="Automatically create front, back and side views for render jobs without prepared previews",
        default=False,
    )
    multiview_render_hero: bpy.props.BoolProperty(
        name="Render Hero View",
        description="Also render the centered front view without the side and back views, using the same background and Freestyle settings",
        default=True,
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
    multiview_angle: bpy.props.EnumProperty(
        name="View Angle",
        description="Additional Z rotation applied to all three multi view positions",
        items=(
            ("-30", "-30°", "Rotate every view by -30 degrees"),
            ("0", "0°", "Use front, back and side angles without an offset"),
            ("30", "+30°", "Rotate every view by +30 degrees"),
        ),
        default="0",
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
    clear_freestyle_after_render: bpy.props.BoolProperty(
        name="Clear Freestyle After Render",
        description="When the render queue or Phase 2 Auto Render ends, clear the Freestyle edge marks it added to the rendered meshes",
        default=True,
    )
    animation_views_freestyle_dual: bpy.props.BoolProperty(
        name="Views With and Without Freestyle",
        description="Save clean and Freestyle versions of each of the four views",
        default=False,
    )
    animation_freestyle_dual_video: bpy.props.BoolProperty(
        name="Videos With and Without Freestyle",
        description="Render two videos in two passes: clean and with Freestyle edges",
        default=False,
    )
    freestyle_line_thickness: bpy.props.FloatProperty(
        name="Line Thickness",
        description="Absolute Freestyle line thickness in pixels",
        default=1.0,
        min=0.01,
        soft_max=5.0,
        precision=3,
    )
    freestyle_line_color: bpy.props.FloatVectorProperty(
        name="Line Color",
        description="Freestyle line color",
        default=(1.0, 0.1946178304415758, 0.0, 1.0),
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
    queue_scanned: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
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
