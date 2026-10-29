"""Finalization workflow RNA property groups."""
from .callbacks import (
    _redraw_view3d,
    _seam_tool_icon_update,
    _update_unity_name_index,
    bpy,
    radians,
)
from ..core.meshopt_simplify import DECIMATE_METHOD_ITEMS, SEAM_MODE_ITEMS


class POLYGROUPS_PG_seam_finalization_settings(bpy.types.PropertyGroup):
    uv_repair_threshold: bpy.props.FloatProperty(
        name="Critical Stretch Ratio", default=4.0, min=1.1, max=1000.0,
    )
    uv_repair_grow_threshold: bpy.props.FloatProperty(
        name="Region Growth Ratio", default=1.8, min=1.01, max=1000.0,
    )
    uv_repair_min_faces: bpy.props.IntProperty(
        name="Minimum Region Faces", default=6, min=1,
    )
    uv_repair_smooth_steps: bpy.props.IntProperty(
        name="Boundary Smoothing", default=2, min=0, max=20,
    )
    uv_repair_surface_angle: bpy.props.FloatProperty(
        name="Surface Angle", default=radians(45.0), subtype="ANGLE", min=0.0, max=radians(180.0),
    )
    uv_repair_sharp_preference: bpy.props.FloatProperty(
        name="Prefer Sharp Longitudinal Edges", default=3.0, min=0.0, max=20.0,
    )
    uv_repair_selected_only: bpy.props.BoolProperty(name="Selected Faces Only", default=False)
    uv_repair_create_edges: bpy.props.BoolProperty(
        name="Create New Edges", default=True,
        description="Allow smart routing to split faces when it improves the seam path",
    )
    uv_repair_pin_generated: bpy.props.BoolProperty(name="Pin Generated Seams", default=True)
    uv_repair_merge_small_islands: bpy.props.BoolProperty(
        name="Merge Small UV Islands", default=True,
        description="Locally merge small islands made by this repair before generated seams are pinned",
    )
    uv_repair_small_island_threshold: bpy.props.FloatProperty(
        name="Small Island Area (%)", default=3.0, min=0.0, max=49.0, precision=2,
        description="Maximum island area as a percentage of its repaired region, not of the whole mesh",
    )
    uv_repair_average_island_scale: bpy.props.BoolProperty(
        name="Average Island Scale", default=True,
        description="Average texel density across all UV islands after repairing and unwrapping",
    )
    uv_repair_native_pack: bpy.props.BoolProperty(
        name="Native Blender Pack", default=True,
        description="Pack all UV islands with Blender's native Pack Islands after repair",
    )
    uv_repair_cleanup_artifacts: bpy.props.BoolProperty(
        name="Clean UV Artifacts During Repair", default=True,
        description="Run tiny malformed UV island cleanup as the first Smart UV Repair step",
    )
    uv_repair_artifact_method: bpy.props.EnumProperty(
        name="Artifact Fix Method",
        items=(
            ('DELETE', 'Delete Faces', 'Delete artifact faces from mesh geometry'),
            ('MERGE_CENTER', 'Merge to Center', 'Collapse each connected artifact to its center'),
        ),
        default='MERGE_CENTER',
    )
    uv_repair_artifact_max_faces: bpy.props.IntProperty(
        name="Maximum Island Faces", default=7, min=1, max=100,
    )
    uv_repair_artifact_stretch: bpy.props.FloatProperty(
        name="Artifact Stretch", default=8.0, min=1.1, max=10000.0,
    )
    uv_repair_artifact_compactness: bpy.props.FloatProperty(
        name="Needle Compactness", default=10.0, min=1.0, max=10000.0,
        description="Detect tiny UV islands with a long perimeter compared with their UV area",
    )
    uv_repair_smart_relax: bpy.props.BoolProperty(
        name="Smart Relax Generated", default=True,
        description="Relax generated seam paths on the mesh surface; this can move mesh vertices",
    )
    topology_guard_selected_only: bpy.props.BoolProperty(
        name="Selected Charts Only", default=False,
        description="Process only seam-bounded charts touched by selected faces",
    )
    topology_guard_fix_handles: bpy.props.BoolProperty(
        name="Handles / Through Holes", default=True,
        description="Cut genus charts (tubes through a surface, torus handles) with two boundary rings at the tube lips",
    )
    topology_guard_fix_annuli: bpy.props.BoolProperty(
        name="Tubes / Annuli", default=True,
        description="Add longitudinal seams that connect the boundary loops of tube-like charts",
    )
    topology_guard_fix_closed: bpy.props.BoolProperty(
        name="Closed Charts", default=True,
        description="Slit closed charts without any boundary between their two farthest points",
    )
    topology_guard_fix_necks: bpy.props.BoolProperty(
        name="Protrusions / Capped Tubes", default=True,
        description="Ring protrusions such as spikes and legs at their neck, and cut caps off closed tubes",
    )
    topology_guard_fix_bridges: bpy.props.BoolProperty(
        name="Close Nearly Split Islands", default=True,
        description="When a seam stops a few edges short of the island border, finish it if that splits the island in two",
    )
    topology_guard_bridge_max_edges: bpy.props.IntProperty(
        name="Max Bridge Edges", default=5, min=1, max=20,
        description="Longest missing seam piece, in edges, that may be added to split an island",
    )
    topology_guard_bridge_min_share: bpy.props.FloatProperty(
        name="Min Split Share", default=0.05, min=0.0, max=0.5, subtype="FACTOR",
        description="Each of the two new islands must hold at least this share of the original island's faces",
    )
    topology_guard_time_limit: bpy.props.IntProperty(
        name="Time Limit (s)", default=120, min=0, max=3600,
        description=("Stop Topology Guard on one mesh after this many seconds and keep the seams found so far, "
                     "so a hard mesh cannot freeze Blender for minutes. 0 = no limit"),
    )
    topology_guard_collapse_knots: bpy.props.BoolProperty(
        name="Collapse Mesh Knots", default=True,
        description=("Merge tiny tangles into one point: holes whose rim was welded to one vertex, "
                     "and faces folded over their neighbours. A merge that would break the mesh is skipped"),
    )
    topology_guard_knot_max_verts: bpy.props.IntProperty(
        name="Max Knot Vertices", default=8, min=3, max=24,
        description="Collapse only knots made of at most this many vertices",
    )
    topology_guard_hole_ratio: bpy.props.FloatProperty(
        name="Hole Ratio", default=0.25, min=0.0, max=1.0, subtype="FACTOR",
        description="Boundary loops shorter than this share of the longest loop are holes that unwrap fills; they get no seam",
    )
    topology_guard_lip_angle: bpy.props.FloatProperty(
        name="Lip Angle", default=radians(45.0), subtype="ANGLE", min=radians(5.0), max=radians(85.0),
        description="Tube rings stop where the surface turns this far away from the tube wall",
    )
    topology_guard_max_flare: bpy.props.FloatProperty(
        name="Max Ring Flare", default=2.5, min=1.05, max=20.0,
        description="Tube rings stop when a ring becomes this many times longer than the narrowest ring",
    )
    topology_guard_sharp_preference: bpy.props.FloatProperty(
        name="Prefer Sharp Edges", default=1.0, min=0.0, max=20.0,
        description="Longitudinal seams prefer sharp edges, where they are less visible",
    )
    topology_guard_neck_angle: bpy.props.FloatProperty(
        name="Crease Ring Angle", default=radians(35.0), subtype="ANGLE", min=radians(1.0), max=radians(180.0),
        description="Closed loops of edges sharper than this are neck candidates",
    )
    topology_guard_neck_elongation: bpy.props.FloatProperty(
        name="Protrusion Elongation", default=0.3, min=0.05, max=10.0,
        description="Cut a neck when the part beyond it has at least this area relative to the squared neck length",
    )
    topology_guard_neck_max_share: bpy.props.FloatProperty(
        name="Max Protrusion Share", default=0.35, min=0.01, max=0.95, subtype="FACTOR",
        description="A protrusion may cover at most this share of its chart",
    )
    topology_guard_tube_tolerance: bpy.props.FloatProperty(
        name="Tube Wall Tolerance", default=0.35, min=0.0, max=1.0, subtype="FACTOR",
        description="Maximum average tilt of a tube wall towards its axis for cap cutting",
    )
    topology_guard_cup_min_height: bpy.props.FloatProperty(
        name="Min Tube Height", default=0.5, min=0.0, max=20.0,
        description="Cut a cap off a tube only when the tube is at least this many diameters long",
    )
    topology_guard_create_edges: bpy.props.BoolProperty(
        name="Create New Edges", default=True,
        description="Smooth longitudinal seams like Generate Smart Seams, splitting faces with diagonal edges",
    )
    topology_guard_smooth_rings: bpy.props.BoolProperty(
        name="Smooth Rings Too", default=False,
        description="Also reroute boundary rings with smart routing; rings on clean edge loops usually need no smoothing",
    )
    topology_guard_pin_generated: bpy.props.BoolProperty(
        name="Pin Generated Seams", default=False,
        description="Protect generated seams with the toolkit seam pin attribute",
    )
    topology_guard_smart_relax: bpy.props.BoolProperty(
        name="Smart Relax Generated", default=False,
        description="Relax generated seam paths on the mesh surface; this can move mesh vertices",
    )
    topology_guard_unwrap: bpy.props.BoolProperty(
        name="Unwrap Fixed Charts", default=True,
        description="Unwrap the processed charts with Angle Based after adding seams",
    )
    topology_guard_pack: bpy.props.BoolProperty(
        name="Average and Pack", default=False,
        description="Average island scale and pack all UV islands after unwrapping",
    )
    topology_guard_after_smart_seams: bpy.props.BoolProperty(
        name="Run After Smart Seams", default=False,
        description="Run Topology Guard automatically inside Generate Smart Seams and Smart UV Unwrap",
    )
    topology_guard_before_repair: bpy.props.BoolProperty(
        name="Run Before Smart UV Repair", default=False,
        description="Fix chart topology and unwrap before Smart UV Repair measures stretch",
    )
    narrow_island_source: bpy.props.EnumProperty(
        name="Analyze",
        items=(
            ('UV', 'UV Islands', 'Respect UV discontinuities and seams'),
            ('MESH', 'Mesh / Seams', 'Use mesh boundaries and existing seams'),
        ),
        default='UV',
    )
    narrow_island_width: bpy.props.IntProperty(
        name="Thin Width (face rows)", default=5, min=1, max=12,
    )
    narrow_island_max_width_percent: bpy.props.FloatProperty(
        name="Max Physical Width (%)", default=35.0, min=0.0, max=100.0, precision=1,
        description="Maximum thickness compared with the widest part of each island; zero disables this filter",
    )
    narrow_island_min_area_percent: bpy.props.FloatProperty(
        name="Minimum Island Area (%)", default=2.0, min=0.0, max=100.0, precision=1,
        description="Skip the whole cut if its result is smaller than this share of the original island; zero disables the filter",
    )
    narrow_island_min_faces: bpy.props.IntProperty(
        name="Minimum Part Faces", default=8, min=2, max=10000,
    )
    narrow_island_min_length: bpy.props.IntProperty(
        name="Minimum Branch Depth", default=3, min=1, max=100,
    )
    narrow_island_selected_only: bpy.props.BoolProperty(
        name="Selected Islands Only", default=False,
        description="Analyze whole islands touched by selected faces",
    )
    narrow_island_create_edges: bpy.props.BoolProperty(
        name="Create New Edges", default=True,
        description="Allow diagonal cuts through polygons for straighter narrow-island seams",
    )
    narrow_island_smart_relax: bpy.props.BoolProperty(
        name="Smart Relax", default=True,
        description="Relax newly generated seams after applying cuts; moves mesh vertices but leaves existing seams unchanged",
    )
    uv_seam_path_auto_unwrap: bpy.props.BoolProperty(
        name="Auto Unwrap UV Island",
        description="Unwrap and separate the edited UV island when the UV Seam Path chain is finished",
        default=True,
    )
    uv_seam_path_margin: bpy.props.FloatProperty(
        name="Island Gap",
        description="Gap between island parts created by UV Seam Path",
        default=0.01,
        min=0.0,
        max=0.25,
        soft_max=0.05,
        precision=4,
    )
    show_checker_solid_mode: bpy.props.BoolProperty(
        name="Show Checker in Solid Mode",
        description="Overlay a UV checker on the active mesh while preserving Solid mode lighting and MatCap",
        default=False,
        update=_redraw_view3d,
    )
    checker_overlay_opacity: bpy.props.FloatProperty(
        name="Opacity",
        description="Opacity of the UV checker drawn over Solid mode shading",
        default=0.1,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
        update=_redraw_view3d,
    )
    checker_overlay_max_polygons: bpy.props.IntProperty(
        name="Ignore Objects Above",
        description="Do not build the Solid Mode checker overlay for meshes above this polygon count; zero disables the limit",
        default=500000,
        min=0,
        soft_max=5000000,
        subtype="UNSIGNED",
        update=_redraw_view3d,
    )
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
    smart_uv_unwrap_auto_pack: bpy.props.BoolProperty(
        name="Auto Pack",
        description="Pack UV islands with Blender's native Pack Islands after Smart UV Unwrap",
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
    pin_longitudinal_seam: bpy.props.BoolProperty(
        name="Mark Generated As Pinned",
        description="Pin seam edges generated by the Longitudinal Seam tool",
        default=False,
        update=_seam_tool_icon_update,
    )


class POLYGROUPS_PG_mesh_finalization_settings(bpy.types.PropertyGroup):
    show_fab_variant_rename: bpy.props.BoolProperty(name="HIGH / MID / LOW", default=True)
    show_unreal_lod_rename: bpy.props.BoolProperty(name="Unreal LOD Rename", default=True)
    unreal_lod_asset_name: bpy.props.StringProperty(name="Asset Name", default="Asset")
    unreal_lod_name_index: bpy.props.StringProperty(name="Name Index", default="00")
    unreal_lod_version_index: bpy.props.StringProperty(name="Version Index", default="01")
    unreal_lod_keep_high: bpy.props.BoolProperty(name="Keep Highest as HIGH/MID", default=True,
        description="Keep the highest polygon mesh separately; start LOD0 from the next mesh in every collection")
    unreal_lod_high_suffix: bpy.props.EnumProperty(name="Highest Mesh Suffix",
        items=(("_HIGH", "_HIGH", ""), ("_MID", "_MID", "")), default="_MID",
        description="Suffix appended to the highest polygon mesh instead of _LOD0")
    unreal_lod_prepare_materials: bpy.props.BoolProperty(name="Prepare Materials and Textures", default=True)
    unreal_lod_copy_textures: bpy.props.BoolProperty(name="Copy Textures", default=True)
    unreal_lod_collection_color: bpy.props.EnumProperty(name="Collection Color Tag",
        items=(("NONE", "None", "", "OUTLINER_COLLECTION", 0),
            *((f"COLOR_{i:02d}", f"Color {i}", "", f"COLLECTION_COLOR_{i:02d}", i) for i in range(1, 9))), default='COLOR_04')
    unreal_lod_random_collection_color: bpy.props.BoolProperty(name="Random Color Tag", default=False)
    show_unity_rename_settings: bpy.props.BoolProperty(name="Unity Rename", default=False)
    show_unity_asset_render_settings: bpy.props.BoolProperty(name="Render Unity Assets", default=False)
    show_unity_turnaround_settings: bpy.props.BoolProperty(name="Turnaround", default=False)
    unity_asset_name: bpy.props.StringProperty(name="Asset Name", default="Asset")
    unity_asset_suffix: bpy.props.StringProperty(name="Suffix", description="Optional name suffix after the asset index", default="")
    unity_collection_color_tag: bpy.props.EnumProperty(name="Collection Color Tag",
        description="Color assigned to Unity LOD collections", items=(
            ("NONE", "None", "No collection color", "OUTLINER_COLLECTION", 0),
            *((f"COLOR_{i:02d}", f"Color {i}", "", f"COLLECTION_COLOR_{i:02d}", i) for i in range(1, 9))),
        default="NONE")
    unity_random_collection_color: bpy.props.BoolProperty(name="Random Color Tag",
        description="Automatically choose a collection color before preparing Auto LOD meshes", default=True)
    unity_generate_text_labels: bpy.props.BoolProperty(name="Generate Text Labels", default=True)
    unity_label_size: bpy.props.FloatProperty(name="Label Size", default=0.1, min=0.001, unit="LENGTH")
    unity_render_mode: bpy.props.EnumProperty(name="Unity Render Mode",
        items=(("ALL", "All Asset LODs Together", "Render all LODs of the active Unity asset in 4K"),
               ("INDIVIDUAL", "One LOD per Image", "Render each LOD of the active Unity asset separately"),
               ("SELECTED", "Selected Assets", "Render selected Unity meshes together")), default="ALL")
    unity_render_separate: bpy.props.BoolProperty(
        name="Separate Renders",
        description="Render each Unity mesh in the chosen set separately, with its own label and automatic framing",
        default=False,
    )
    unity_render_text: bpy.props.BoolProperty(name="Include Text Labels", default=True)
    unity_render_freestyle: bpy.props.BoolProperty(name="Enable Freestyle", default=True)
    unity_render_mesh_info: bpy.props.BoolProperty(
        name="Export Mesh Info JSON",
        description="Write MeshInfo.json beside the Unity renders using the Unity FBX mesh info format",
        default=False,
    )
    unity_render_image_format: bpy.props.EnumProperty(name="Image Format",
        items=(("PNG", "PNG", "PNG image"), ("JPEG", "JPEG", "JPEG image"),
               ("WEBP", "WebP", "WebP image")), default="WEBP")
    unity_name_index: bpy.props.StringProperty(name="Name Index", default="00", maxlen=2, update=_update_unity_name_index)
    unity_asset_index: bpy.props.StringProperty(name="Version Index", default="01")
    unity_auto_increment_index: bpy.props.BoolProperty(name="Auto Increment Index", default=True)
    unity_copy_textures: bpy.props.BoolProperty(name="Copy Textures", default=True)
    unity_skip_lods: bpy.props.BoolProperty(name="Skip LODs", default=False,
        description="Skip Generate LODs only; run Prepare Meshes (Auto LODs) on selected meshes, then export")
    unity_export_directory: bpy.props.StringProperty(name="Directory", subtype="DIR_PATH", default="//!Unity")
    unity_export_clear_asset_folder: bpy.props.BoolProperty(name="Clear Asset Folder Before Start", description="Remove existing contents of each exported asset folder before exporting", default=True)
    unity_export_autosave: bpy.props.BoolProperty(name="Autosave Before Start", description="Save the current blend file before starting Unity export", default=True)
    unity_export_overwrite: bpy.props.BoolProperty(name="Overwrite Existing", default=False)
    unity_export_fbx: bpy.props.BoolProperty(name="FBX", default=True)
    unity_export_gltf: bpy.props.BoolProperty(name="GLTF", default=True)
    unity_export_glb: bpy.props.BoolProperty(name="GLB", default=False)
    unity_glb_mode: bpy.props.EnumProperty(name="GLB LODs", items=(("SEPARATE", "Separate Files", ""), ("COMBINED", "One File per Asset", "")), default='COMBINED')
    unity_gltf_mode: bpy.props.EnumProperty(name="GLTF Mode", items=(
        ("COMBINED", "All LODs in One GLTF", "One embedded GLTF containing all selected asset LODs and one shared texture set"),
        ("SHARED", "Separate LODs / Shared Textures", "Separate GLTF and BIN files for LODs referencing one common Textures folder")),
        default="COMBINED")
    unity_export_all_renders: bpy.props.BoolProperty(name="Export All Renders",
        description="Render each selected LOD and the asset turnaround into the Unity asset folder", default=True)
    unity_export_info_format: bpy.props.EnumProperty(
        name="Mesh Info",
        description="Write vertex and triangle counts for each exported LOD",
        items=(("NONE", "None", "Do not write a mesh info report"),
               ("JSON", "JSON", "Write MeshInfo.json for each asset"),
               ("TXT", "TXT", "Write MeshInfo.txt for each asset")),
        default="JSON",
    )
    unity_export_status: bpy.props.StringProperty(name="Export Status", default="Not exported")
    unity_use_auto_rig_pro: bpy.props.BoolProperty(
        name="Auto-Rig Pro Export",
        description="Export LOD0 together with the selected rig using the saved Auto-Rig Pro export settings",
        default=False,
    )
    show_smart_decimate_settings: bpy.props.BoolProperty(
        name="Decimate",
        default=False,
    )
    show_smart_lods_settings: bpy.props.BoolProperty(name="Smart LODs", default=False)
    smart_lods_is_running: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})
    smart_lods_progress: bpy.props.FloatProperty(default=0, min=0, max=100, options={'SKIP_SAVE'})
    smart_lods_status: bpy.props.StringProperty(default='', options={'SKIP_SAVE'})
    smart_lods_prepare_mode: bpy.props.EnumProperty(name="Prepare For", items=(("UNITY", "Unity", "Prepare generated LODs for Unity"), ("UNREAL", "Unreal", "Prepare generated meshes as Unreal _LODN assets")), default="UNITY")
    smart_lods_count: bpy.props.IntProperty(
        name="LOD Count", description="Number of generated LOD meshes",
        default=5, min=1, max=5,
    )
    smart_lods_target_1: bpy.props.IntProperty(name="LOD0", default=2900, min=1, step=100)
    smart_lods_target_2: bpy.props.IntProperty(name="LOD1", step=100, default=1500, min=1)
    smart_lods_target_3: bpy.props.IntProperty(name="LOD2", step=100, default=1000, min=1)
    smart_lods_target_4: bpy.props.IntProperty(name="LOD3", step=100, default=500, min=1)
    smart_lods_target_5: bpy.props.IntProperty(name="LOD4", step=100, default=150, min=1)
    smart_lods_decimate_method: bpy.props.EnumProperty(
        name="Decimate Method", items=DECIMATE_METHOD_ITEMS, default="UV_PRESERVE")
    smart_lods_uv_seam_mode: bpy.props.EnumProperty(
        name="Seams", items=SEAM_MODE_ITEMS, default="LOCK",
        description="Starting seam protection; relaxed automatically when a LOD budget is not reached")
    smart_lods_final_decimate: bpy.props.BoolProperty(
        name="Final Decimate Fallback",
        description="If seam-aware decimation cannot reach a triangle limit, add an unrestricted Decimate pass",
        default=True,
    )
    smart_lods_triangulate_all: bpy.props.BoolProperty(
        name="Triangulate All LODs",
        description="Apply triangulation to every generated LOD mesh",
        default=True,
    )
    smart_lods_remove_zero_area: bpy.props.BoolProperty(
        name="Check and Remove Zero-Area Faces",
        description="Check every generated LOD after decimation/triangulation and remove exactly zero-area triangles; keep nonzero thin faces",
        default=True,
    )
    smart_decimate_smart_arrange: bpy.props.BoolProperty(name="Smart Arrange", default=True,
        description="Place decimated copies on a common origin grid sized by the widest source asset")
    smart_lods_smart_arrange: bpy.props.BoolProperty(name="Smart Arrange", default=True,
        description="Precompute one grid from the widest source asset; align every LOD level to the same world X by object origins")
    smart_lods_auto_arrange: bpy.props.BoolProperty(
        name="Auto Arrange",
        description="Arrange one LOD pack per row on the XY floor plane, aligned by object origins",
        default=True,
    )
    smart_lods_create_text: bpy.props.BoolProperty(name="Create LOD Labels", default=False)
    smart_lods_text_size: bpy.props.FloatProperty(name="Label Size", default=0.1, min=0.001, unit="LENGTH")
    smart_lods_render_select_all: bpy.props.BoolProperty(name="Select All Generated LODs", default=True)
    smart_lods_render_mode: bpy.props.EnumProperty(
        name="LOD Render Mode",
        items=(("ALL", "All LODs Together", "Select all generated LODs and render one 4K image"),
               ("INDIVIDUAL", "One LOD per Image", "Render each generated LOD and its label separately"),
               ("SELECTED", "Selected LODs", "Render only the selected LODs together")),
        default="ALL",
    )
    smart_lods_render_text: bpy.props.BoolProperty(name="Include LOD Labels", default=True)
    smart_lods_render_freestyle: bpy.props.BoolProperty(name="Enable Freestyle", default=True)
    smart_lods_spacing: bpy.props.FloatProperty(
        name="Spacing Y",
        description="Spacing between LOD pack rows on the XY floor plane",
        default=1.0,
        min=0.0,
        soft_max=10.0,
        subtype="DISTANCE",
        unit="LENGTH",
    )
    smart_lods_alignment: bpy.props.EnumProperty(name="Align By",
        items=(("BOUNDS", "Bounds", "Place successive LODs with a gap between mesh bounds"),
               ("ORIGIN", "Origin", "Align object origins along X using Spacing as the origin-to-origin distance")),
        default="ORIGIN", options={"HIDDEN"})
    show_mesh_check_settings: bpy.props.BoolProperty(
        name="Check Mesh",
        default=False,
    )
    show_all_mesh_fix_operators: bpy.props.BoolProperty(
        name="Show All Fix Operators",
        description="Show all mesh repair operators independently from detected issue categories",
        default=False,
    )
    show_fab_rename_settings: bpy.props.BoolProperty(
        name="FAB Rename",
        default=False,
    )
    show_mesh_export_settings: bpy.props.BoolProperty(
        name="Export",
        default=False,
    )
    smart_decimate_triangle_limit: bpy.props.IntProperty(
        name="Triangle Limit",
        description="Automatically fit decimate ratios to this triangle budget; 0 uses manual ratios",
        default=0,
        min=0,
    )
    smart_decimate_ratio: bpy.props.FloatProperty(
        name="Ratio",
        description="Decimate ratio for non-seam areas",
        default=0.4,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    smart_decimate_seams_ratio: bpy.props.FloatProperty(
        name="Seams Decimate Ratio",
        description="Decimate ratio for seam vertices",
        default=0.9,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    smart_decimate_duplicate_and_apply: bpy.props.BoolProperty(
        name="Duplicate And Apply Decimate",
        description="Duplicate the active object, add Smart Decimate to the duplicate, and apply it",
        default=True,
    )
    smart_decimate_reunwrap_uv: bpy.props.BoolProperty(name='Reunwrap UV / Pin Island Borders', default=True,
        description='Apply both decimation passes and relax UV interiors while preserving island borders')
    smart_decimate_hide_source: bpy.props.BoolProperty(
        name="Hide LOW After Decimate", default=False,
        description="Disable original LOW viewport display after successful Smart Decimate",
    )
    show_smart_decimate_blender_settings: bpy.props.BoolProperty(name="Smart Decimate (Blender)", default=True)
    show_uv_decimate_settings: bpy.props.BoolProperty(name="UV Preserve Decimate", default=False)
    uv_decimate_triangle_limit: bpy.props.IntProperty(
        name="Triangle Limit", description="Target triangle count; 0 uses Ratio", default=0, min=0)
    uv_decimate_ratio: bpy.props.FloatProperty(
        name="Ratio", description="Fraction of source triangles to keep when Triangle Limit is 0",
        default=0.25, min=0.0, max=1.0, subtype="FACTOR")
    uv_decimate_seam_mode: bpy.props.EnumProperty(name="Seams", items=SEAM_MODE_ITEMS, default="LOCK")
    uv_decimate_uv_weight: bpy.props.FloatProperty(
        name="UV Weight", description="Importance of UV error relative to geometric error",
        default=1.0, min=0.0, soft_max=10.0)
    uv_decimate_max_error: bpy.props.FloatProperty(
        name="Max Error", description="Stop before this relative error (1.0 = only the triangle budget limits)",
        default=1.0, min=0.0, max=1.0, subtype="FACTOR")
    uv_decimate_lock_open_borders: bpy.props.BoolProperty(
        name="Lock Open Borders", description="Never move vertices on open mesh borders", default=False)
    uv_decimate_join_triangles: bpy.props.BoolProperty(
        name="Join Triangles To Quads",
        description="Merge triangle pairs into quads without moving vertices or crossing seams/materials",
        default=True)
    uv_decimate_join_angle: bpy.props.FloatProperty(
        name="Quad Angle", description="Max face and shape angle for joining triangle pairs into quads",
        default=radians(60), min=0.0, max=radians(180), subtype="ANGLE")
    uv_decimate_duplicate: bpy.props.BoolProperty(
        name="Decimate A Duplicate", description="Keep the active object and decimate a copy", default=True)
    uv_decimate_hide_source: bpy.props.BoolProperty(
        name="Hide LOW After Decimate", default=False,
        description="Disable original LOW viewport display after successful UV Preserve Decimate")
    fab_prepare_is_running: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    fab_prepare_stop_requested: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    fab_prepare_total: bpy.props.IntProperty(default=0, min=0, options={"SKIP_SAVE"})
    fab_prepare_done: bpy.props.IntProperty(default=0, min=0, options={"SKIP_SAVE"})
    fab_prepare_prepared: bpy.props.IntProperty(default=0, min=0, options={"SKIP_SAVE"})
    fab_prepare_skipped: bpy.props.IntProperty(default=0, min=0, options={"SKIP_SAVE"})
    fab_prepare_failed: bpy.props.IntProperty(default=0, min=0, options={"SKIP_SAVE"})
    fab_prepare_current: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    fab_prepare_status: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    fab_prepare_queue_data: bpy.props.StringProperty(default="[]", options={"SKIP_SAVE"})
    fab_prepare_progress: bpy.props.FloatProperty(default=0, min=0, max=1, options={"SKIP_SAVE"})
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
    mesh_export_fbx: bpy.props.BoolProperty(name="FBX", default=True)
    mesh_export_glb: bpy.props.BoolProperty(name="GLB", default=False)
    mesh_export_gltf: bpy.props.BoolProperty(name="GLTF", default=False)
    unreal_glb_mode: bpy.props.EnumProperty(name="GLB Mode", items=(
        ("COMBINED", "All LODs in One GLB", "One self-contained GLB per asset containing all selected LOD meshes"),
        ("SEPARATE", "Separate LODs", "One self-contained GLB file per selected mesh")),
        default="COMBINED")
    unreal_gltf_mode: bpy.props.EnumProperty(name="GLTF Mode", items=(
        ("COMBINED", "All LODs in One GLTF", "One embedded GLTF per asset containing its selected LOD meshes"),
        ("SHARED", "Separate LODs / Shared Textures", "Separate GLTF files for LODs with a shared texture directory")),
        default="COMBINED")
    mesh_export_sort: bpy.props.EnumProperty(
        name="Sort By",
        description="Arrange exported FAB meshes by asset set or by mesh quality",
        items=(
            ("SET", "Sets", "Put LOW, MID and HIGH of each asset in one folder"),
            ("VARIANT", "LOW / MID / HIGH", "Put all meshes of each quality in one folder"),
            ("LODS", "LODs", "Group Unreal LOD meshes by asset, with separate format folders"),
            ("LODS_FORMAT", "LODs / Format", "Group all assets by format, with one shared Textures folder per format"),
        ),
        default="VARIANT",
    )
    gltf_export_embedded: bpy.props.BoolProperty(
        name="Embed Textures and Buffers",
        description="Store textures and binary mesh data inside each .gltf file instead of separate files",
        default=False,
    )
    gltf_export_info_format: bpy.props.EnumProperty(
        name="Mesh Info",
        description="Write vertex and triangle counts for exported meshes to !GLTF",
        items=(("NONE", "None", "Do not write a mesh info report"),
               ("JSON", "JSON", "Write MeshInfo.json"),
               ("TXT", "TXT", "Write MeshInfo.txt")),
        default="NONE",
    )
    mesh_export_info_format: bpy.props.EnumProperty(
        name="Mesh Info",
        description="Write vertex and triangle counts for exported meshes to !Unreal",
        items=(
            ("NONE", "None", "Do not write a mesh info report"),
            ("JSON", "JSON", "Write MeshInfo.json"),
            ("TXT", "TXT", "Write MeshInfo.txt"),
        ),
        default="NONE",
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
    mesh_check_active_stage: bpy.props.EnumProperty(
        name="Active Check Stage",
        items=(
            ("FIN_FACES", "Dangling Fin Polygons", "Find weakly attached fin-like polygons"),
            ("DOUBLE_WALLS", "Zero-Thickness Double Walls", "Find coincident faces with opposite normals"),
            ("LOOSE_EDGES", "Loose Edges", "Find edges that do not belong to a face"),
            ("ISOLATED_VERTICES", "Isolated Vertices", "Find vertices not connected to an edge"),
            ("NGONS", "N-gons", "Find polygons with more than four sides"),
            ("OPEN_BOUNDARIES", "Open Boundaries", "Find open non-manifold boundary loops"),
            ("NORMALS", "Inverted Normals", "Find inconsistent or inward-facing normals"),
        ),
        default="FIN_FACES",
        options={"SKIP_SAVE"},
    )
    mesh_check_stage_state: bpy.props.EnumProperty(
        name="Check Stage State",
        items=(
            ("NOT_SCANNED", "Not Scanned", "This stage has not been scanned"),
            ("ISSUES", "Issues Found", "This stage has unresolved issues"),
            ("CLEAN", "Clean", "This stage has no issues"),
            ("FIXED", "Fixed", "The issues in this stage were fixed"),
            ("SKIPPED", "Skipped", "The issues in this stage were skipped"),
            ("COMPLETE", "Complete", "The staged check is complete"),
        ),
        default="NOT_SCANNED",
        options={"SKIP_SAVE"},
    )
    mesh_check_can_undo: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    mesh_check_last_fixed_stage: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    mesh_check_scanned_stages: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
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
    mesh_check_double_walls: bpy.props.IntProperty(default=0, min=0)
