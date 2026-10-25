"""Preparation workflow RNA property groups."""
from .callbacks import (
    BATCH_REMESH_UNWRAP_METHOD_ITEMS,
    IMPORT_AUTO_UNWRAP_METHOD_ITEMS,
    IMPORT_REMESH_METHOD_ITEMS,
    REMESH_PRESET_ITEMS,
    _import_auto_remesh_update,
    _panel_visibility_update,
    _redraw_view3d,
    _single_section_mode_update,
    _update_batch_smart_decimate,
    _update_batch_smart_lods,
    bpy,
    radians,
)


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
            ("BLEND", "Blend", "Append Generated collections from Blender files"),
        ),
        default="GLB",
    )
    file_import_auto_rename_objects: bpy.props.BoolProperty(
        name="Auto Rename Objects",
        description="Rename selected imported files and move them to the Generated collection",
        default=True,
    )
    file_import_automatic_processing: bpy.props.BoolProperty(
        name="Automatic Import Processing",
        description="Process selected files with the shared Batch Import stages and settings",
        default=False,
    )
    file_import_apply_weld: bpy.props.BoolProperty(
        name="Apply Weld",
        description="Apply Weld to mesh objects imported through file selection",
        default=True,
    )
    file_import_disable_auto_unwrap: bpy.props.BoolProperty(
        name="Disable Auto Unwrap",
        description="Disable automatic UV unwrapping after import",
        default=True,
    )
    file_import_disable_view_assist: bpy.props.BoolProperty(
        name="Disable View Assist",
        description="Disable checker and seam display after import",
        default=True,
    )
    file_import_auto_smart_uv_project: bpy.props.BoolProperty(
        name="Auto Unwrap",
        description="Automatically unwrap imported remesh results",
        default=True,
    )
    file_import_auto_unwrap_method: bpy.props.EnumProperty(
        name="Unwrap Method",
        description="Method used to unwrap imported remesh results",
        items=IMPORT_AUTO_UNWRAP_METHOD_ITEMS,
        default="SMART",
    )
    file_import_remove_small_loose_parts: bpy.props.BoolProperty(
        name="Remove Small Loose Parts",
        default=True,
        description="Automatically remove small disconnected components before Auto Unwrap",
    )
    file_import_small_loose_part_threshold_percent: bpy.props.FloatProperty(
        name="Remove Below",
        default=8.0,
        min=0.0,
        max=100.0,
        soft_max=25.0,
        precision=1,
        subtype="PERCENTAGE",
        description="Remove parts smaller than this percentage of the largest disconnected part",
    )
    file_import_small_loose_part_metric: bpy.props.EnumProperty(
        name="Loose Part Size",
        description="How disconnected part size is measured before Auto Unwrap",
        items=(
            (
                "BOUNDING_BOX",
                "Bounding Box",
                "Use bounding-box size with flat and linear geometry support",
            ),
            (
                "VOLUME",
                "Volume",
                "Use enclosed volume; automatically use bounding-box size for open geometry",
            ),
        ),
        default="BOUNDING_BOX",
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
    batch_disable_auto_unwrap: bpy.props.BoolProperty(
        name="Disable Auto Unwrap",
        description="Disable automatic UV unwrapping after batch import",
        default=True,
    )
    batch_disable_view_assist: bpy.props.BoolProperty(
        name="Disable View Assist",
        description="Disable checker and seam display after batch import",
        default=True,
    )
    batch_auto_smart_uv_project: bpy.props.BoolProperty(
        name="Auto Unwrap",
        description="Automatically unwrap each imported remesh result",
        default=True,
    )
    batch_auto_unwrap_method: bpy.props.EnumProperty(
        name="Unwrap Method",
        description="Method used to unwrap each imported remesh result",
        items=IMPORT_AUTO_UNWRAP_METHOD_ITEMS,
        default="SMART",
    )
    batch_import_mode: bpy.props.EnumProperty(
        name="Import Mode",
        description="Continue automatically or pause after each completed file",
        items=(
            ("AUTO", "Auto Import", "Process every queued file without stopping"),
            (
                "PAUSE_EACH",
                "Pause After Each",
                "Finish the current file completely, then pause before importing the next file",
            ),
        ),
        default="AUTO",
    )
    batch_include_subfolders: bpy.props.BoolProperty(
        name="Include Subfolders",
        description="Scan and import supported mesh files from nested folders",
        default=True,
    )
    show_batch_start_file: bpy.props.BoolProperty(name="Save and Reset", default=True)
    show_batch_start_autosave: bpy.props.BoolProperty(name="Auto Save", default=True)
    show_batch_start_mode: bpy.props.BoolProperty(name="Import Mode", default=True)
    phase2_show_files: bpy.props.BoolProperty(name="Blend File Manager", default=True)
    phase2_show_restore: bpy.props.BoolProperty(name="Restore and Processing", default=True)
    phase2_show_finalization: bpy.props.BoolProperty(name="Batch Finalization", default=True)
    phase2_show_lods_rename: bpy.props.BoolProperty(name="Prepare LODs / Rename", default=True)
    phase2_final_lods: bpy.props.BoolProperty(name="Prepare LODs", default=True)
    phase2_final_lod_engine: bpy.props.EnumProperty(name="LOD Pipeline",
        items=(("UNREAL", "Unreal", ""), ("UNITY", "Unity", "")), default='UNREAL')
    phase2_final_rename: bpy.props.BoolProperty(name="Rename", default=True)
    phase2_final_rename_engine: bpy.props.EnumProperty(name="Rename Pipeline",
        items=(("FAB", "FAB", "Unreal LOD Rename"), ("UNITY", "Unity", "Unity Prepare")), default='FAB')
    phase2_final_cleanup_generated: bpy.props.BoolProperty(name="Delete Generated.N after Successful Rename", default=False)
    phase2_show_export: bpy.props.BoolProperty(name="Export Prepared Models", default=True)
    phase2_export_engine: bpy.props.EnumProperty(name="Pipeline", items=(("FAB", "Unreal / FAB", ""), ("UNITY", "Unity", "")), default='FAB')
    phase2_export_fbx: bpy.props.BoolProperty(name="FBX", default=False)
    phase2_export_glb: bpy.props.BoolProperty(name="GLB", default=True)
    phase2_export_gltf: bpy.props.BoolProperty(name="GLTF", default=False)
    phase2_export_sort: bpy.props.EnumProperty(name="Sort By", items=(("LODS", "LODs", "Asset / Format"), ("LODS_FORMAT", "LODs / Format", "Format / Assets with shared textures")), default='LODS_FORMAT')
    phase2_export_json: bpy.props.BoolProperty(name="Mesh Info JSON", default=True)
    phase2_export_status: bpy.props.StringProperty(default="Not exported")
    phase2_show_export_blend: bpy.props.BoolProperty(name="Export Blend Files", default=True)
    phase2_blend_export_pack: bpy.props.BoolProperty(
        name="Pack Textures", description="Pack only the textures used by each exported collection", default=True)
    phase2_blend_export_reset_y: bpy.props.BoolProperty(
        name="Reset Mesh Y to 0",
        description="Write the prepared MID/HIGH/LODN meshes of each asset collection at Y = 0 (the working file is not changed)",
        default=True)
    phase2_blend_export_generated: bpy.props.BoolProperty(
        name="Export Generated.N Collections",
        description="Also export each Generated.N collection (Retopo / Resculpting meshes) as its own blend with packed textures",
        default=False)
    phase2_blend_export_status: bpy.props.StringProperty(default="Not exported")
    phase2_show_export_zbrush: bpy.props.BoolProperty(name="Export ZBrush", default=True)
    phase2_zbrush_directory: bpy.props.StringProperty(
        name="Output", subtype='DIR_PATH', default="",
        description="Folder for OBJ levels, ZTL files and the job script. Empty: !ZBrush beside the pack root")
    phase2_zbrush_exe: bpy.props.StringProperty(
        name="ZBrush.exe", subtype='FILE_PATH', default="",
        description="Empty: the newest ZBrush found in Program Files")
    phase2_zbrush_build: bpy.props.EnumProperty(
        name="Levels", default='AUTO',
        items=(('AUTO', 'Auto', 'Reconstruct Subdiv with a point/face-count check, falling back to Project All'),
               ('RECONSTRUCT', 'Reconstruct',
                'Import the top level and rebuild the lower levels. Fast, top level is exact, base differs ~0.2 mm'),
               ('PROJECT', 'Project All',
                'Import the base, Divide and project each level onto it. Slow (~100 s per mesh), ~0.5 mm error')))
    phase2_zbrush_blend_folder: bpy.props.StringProperty(
        name="Blends Folder", subtype='DIR_PATH', default="",
        description="Folder with Generated.N.blend files for the batch export. Empty: the folder of the current blend")
    phase2_zbrush_launch: bpy.props.BoolProperty(
        name="Launch ZBrush", default=True, description="Start ZBrush and build the ZTL files after the export")
    phase2_zbrush_status: bpy.props.StringProperty(default="Not exported")
    phase2_final_is_running: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})
    phase2_final_progress: bpy.props.FloatProperty(default=0, min=0, max=100, options={'SKIP_SAVE'})
    phase2_show_auto_render: bpy.props.BoolProperty(name="Auto Render", default=True)
    phase2_auto_render_running: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})
    phase2_auto_transparent: bpy.props.BoolProperty(name="Render Transparent PNG (Without Scene)", default=False)
    phase2_auto_scene_prefix: bpy.props.StringProperty(name="Prefix Scene", default="Scene",
        description="Studio collection prefix hidden for the additional transparent PNG")
    phase2_auto_scene: bpy.props.BoolProperty(name="Scene and Camera Setup", default=True)
    phase2_auto_camera: bpy.props.BoolProperty(name="Auto Frame Camera (10% Margin)", default=True)
    phase2_auto_selection: bpy.props.BoolProperty(name="Mesh Selection: MID and LOD0", default=True)
    phase2_auto_freestyle: bpy.props.BoolProperty(name="Freestyle", default=True)
    phase2_auto_freestyle_pass: bpy.props.BoolProperty(name="As Render Pass", default=True)
    phase2_auto_freestyle_color: bpy.props.FloatVectorProperty(name="Line Color", size=4,
        subtype='COLOR', min=0, max=1, default=(.80695226, .80695226, .80695226, 1))
    phase2_auto_multiview: bpy.props.BoolProperty(name="Multiview", default=True)
    phase2_auto_mv_offset: bpy.props.FloatProperty(name="Offset (m)", default=1, min=0)
    phase2_auto_mv_angle: bpy.props.EnumProperty(name="Angle",
        items=(("-30", "-30 degrees", ""), ("0", "0 degrees", ""), ("30", "+30 degrees", "")), default='-30')
    phase2_auto_mv_hero: bpy.props.BoolProperty(name="Render Hero", default=True)
    phase2_auto_textures: bpy.props.BoolProperty(name="Prepare Textures", default=True)
    phase2_auto_texture_prepare: bpy.props.EnumProperty(name="Prepare Textures",
        items=(("ALL", "All Assets First", "Prepare all texture pairs before rendering"),
               ("EACH", "Per Asset", "Prepare the texture pair just before rendering each asset")), default='ALL')
    phase2_show_status: bpy.props.BoolProperty(name="Status", default=True)
    phase2_files_cleanup: bpy.props.BoolProperty(
        name="Auto Delete Backup Saves", default=False,
        description="After moving blend files, use Save Cleanup to delete numbered backups throughout the current project folder",
    )
    phase2_files_found: bpy.props.IntProperty(default=0, options={"SKIP_SAVE"})
    phase2_files_status: bpy.props.StringProperty(default="Scan required", options={"SKIP_SAVE"})
    phase2_files_cleanup_status: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    phase2_scan_subfolders: bpy.props.BoolProperty(
        name="All Blends Including Subfolders", default=False,
        description="Scan all blend files beside the working blend and in subfolders, excluding the working file",
    )
    phase2_clear_generated: bpy.props.BoolProperty(
        name="Clear Current Generated.N Collections", default=False,
        description="Remove existing Generated.N collections before restoring the scanned files",
    )
    phase2_auto_bake: bpy.props.BoolProperty(name="Auto Bake", default=True)
    phase2_mid_remesh: bpy.props.BoolProperty(name="MID Remesh Before Repack", default=False,
        description="Clear all seams/pins, generate Smart Seams at 22 degrees, remesh the highest Retopo using MID, unwrap and repack the next stage")
    phase2_repair_after_resculpt: bpy.props.BoolProperty(name="Auto Repair After Resculpting", default=True)
    phase2_skip_retopo_backups: bpy.props.BoolProperty(name="Skip Retopo Backup Objects", default=False,
        description="Do not restore Backup_Retopo or Backup_Resculpting objects from saved collections during Phase 2 processing")
    phase2_autosave: bpy.props.BoolProperty(name="Autosave Completed Collections", default=False,
        description="Save the current blend after every N successfully completed collection pipelines")
    phase2_autosave_every: bpy.props.IntProperty(name="Successful Collections per Save", default=1, min=1)
    phase2_autosave_status: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})
    phase2_resculpt_retopo01: bpy.props.BoolProperty(name="Resculpting Retopo_01", default=False,
        description="Run Setup Resculpting on Retopo_01 after the highest Retopo finishes baking")
    phase2_autobake_retopo01: bpy.props.BoolProperty(name="Autobake Retopo_01", default=False,
        description="Repair and rebake Retopo_01 before highpoly cleanup; enabled UV repacking always runs")
    phase2_mesh_auto_repair: bpy.props.BoolProperty(
        name="Auto Repair Mesh", default=True,
        description="Repair folded pockets and merge coincident vertices only on the highest Retopo stage independently of Auto Bake",
    )
    phase2_repack_after_repair: bpy.props.BoolProperty(
        name="Repack UV", default=False,
        description="Always run UVPackmaster PACK on the current target when enabled",
    )
    phase2_delete_high_after_bake: bpy.props.BoolProperty(
        name="Delete Highpoly After Successful Bake", default=False,
        description="Remove the baked Highpoly source from the completed Generated collection only after successful rebaking",
    )
    phase2_delete_lower_retopo: bpy.props.BoolProperty(
        name="Delete Lower Retopo Stages After Successful Bake", default=False,
        description="Remove earlier numbered Retopo stages, keeping the target used by the successful bake",
    )
    phase2_keep_retopo01: bpy.props.BoolProperty(name="Keep Retopo_01 (Resculpted)", default=True,
        description="Preserve Retopo_01 during automatic and manual lower-stage cleanup")
    phase2_show_manual_cleanup: bpy.props.BoolProperty(name="Manual Cleanup", default=False)
    phase2_repair_artifacts: bpy.props.BoolProperty(
        name="Repair Projection Artifacts", default=True,
        description="Enable full projection artifact masks and Autofill for Phase 2 baking",
    )
    phase2_scanned_files: bpy.props.IntProperty(default=0, options={"SKIP_SAVE"})
    phase2_scanned_collections: bpy.props.IntProperty(default=0, options={"SKIP_SAVE"})
    phase2_is_running: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    phase2_done_count: bpy.props.IntProperty(default=0, options={"SKIP_SAVE"})
    phase2_failed_count: bpy.props.IntProperty(default=0, options={"SKIP_SAVE"})
    phase2_total_count: bpy.props.IntProperty(default=0, options={"SKIP_SAVE"})
    phase2_status: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
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
    batch_arrange_secondary_spacing: bpy.props.FloatProperty(
        name="Secondary Spacing",
        description="Distance between rows along Y or Z",
        default=0.1, min=0.0, max=1.0, precision=2, unit="LENGTH",
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
        max=50,
        soft_max=50,
    )
    batch_arrange_plane: bpy.props.EnumProperty(
        name="Plane",
        description="Plane for arranging imported objects",
        items=(("ZX", "ZX - Camera", "Arrange along X and Z"), ("XY", "XY - Floor", "Arrange along X and Y")),
        default="ZX",
    )
    batch_arrange_alignment: bpy.props.EnumProperty(
        name="Alignment", description="Reference used to position objects",
        items=(("BOUNDS", "Object Bounds", "Keep spacing between object bounds"),
               ("ORIGIN", "Object Origins", "Align origins to an evenly spaced grid")),
        default="BOUNDS",
    )
    batch_auto_save: bpy.props.BoolProperty(
        name="Auto Save",
        description="Save the current blend file after a configured number of successfully imported meshes",
        default=False,
    )
    batch_auto_save_interval: bpy.props.IntProperty(
        name="Every Successful Imports",
        description="Save after this many source files finish the complete import pipeline successfully",
        default=5,
        min=1,
        soft_max=100,
    )
    batch_save_generated_separately: bpy.props.BoolProperty(
        name="Save Generated Collections Separately",
        description=(
            "Save each successfully processed Generated.N collection beside the current blend file, "
            "then leave that collection empty in the working file"
        ),
        default=False,
    )
    batch_auto_restore_separate_retopo: bpy.props.BoolProperty(
        name="Auto Restore after Completion",
        description="Restore Retopo objects from separate files after Batch Import completes",
        default=False,
    )
    batch_restore_include_highpoly: bpy.props.BoolProperty(
        name="Include Highpoly Generated",
        description="Include Highpoly_Generated objects in automatic and manual restore from separate files",
        default=False,
    )
    batch_append_include_highpoly: bpy.props.BoolProperty(
        name="Include HighPoly",
        description="Include Highpoly_* objects when appending Generated collections from blend files",
        default=False,
    )
    small_loose_part_threshold_percent: bpy.props.FloatProperty(
        name="Small Part Threshold",
        description="Delete disconnected parts smaller than this percentage of the largest part",
        default=8.0,
        min=0.0,
        max=100.0,
        soft_max=25.0,
        precision=1,
        subtype="PERCENTAGE",
    )
    fold_repair_folds: bpy.props.BoolProperty(name="Repair Folded Pockets", default=True)
    fold_repair_degenerate: bpy.props.BoolProperty(name="Merge Coincident Vertices", default=True,
        description="Collapse near-zero edges of degenerate triangles, preserving UV seams")
    fold_repair_zero_area: bpy.props.BoolProperty(name="Repair Zero Area at UV Seams", default=False,
        description="Repair zero-length edges even across UV seams; preserve corner UVs and seam/sharp flags")
    fold_repair_selected_only: bpy.props.BoolProperty(name="Selected Area Only", default=False,
        description="Repair defects seeded by selected faces, including their local boundary")
    small_loose_part_metric: bpy.props.EnumProperty(
        name="Size Metric",
        description="How disconnected part size is measured",
        items=(
            (
                "BOUNDING_BOX",
                "Bounding Box",
                "Use bounding-box size with flat and linear geometry support",
            ),
            (
                "VOLUME",
                "Volume",
                "Use enclosed volume; automatically use bounding-box size for open geometry",
            ),
        ),
        default="BOUNDING_BOX",
    )
    batch_is_running: bpy.props.BoolProperty(
        name="Running",
        default=False,
        options={"SKIP_SAVE"},
    )
    remesh_auto_generate_seams: bpy.props.BoolProperty(
        name="Auto Generate Seams",
        description="Generate seams along material boundaries on each remeshed result",
        default=True,
    )
    remesh_pregenerate_polygroups: bpy.props.BoolProperty(
        name="Pregenerate Poly Groups",
        description="Run Generate PolyGroups on the source mesh before remeshing",
        default=True,
    )
    remesh_auto_unwrap_checker: bpy.props.BoolProperty(
        name="Auto Unwrap and Apply Checker",
        description="Unwrap each remeshed result with Angle Based and apply the checker material",
        default=True,
    )
    file_import_auto_remesh: bpy.props.BoolProperty(
        name="Auto Remesh",
        default=True,
        update=_import_auto_remesh_update(
            "file_import_auto_remesh",
            "file_import_auto_smart_uv_project",
        ),
    )
    file_import_clear_material: bpy.props.BoolProperty(
        name="Clear Material",
        description="Replace transferred materials on the remeshed result with a plain gray material",
        default=True,
    )
    file_import_remesh_method: bpy.props.EnumProperty(
        name="Remesh Type", items=IMPORT_REMESH_METHOD_ITEMS, default="QUAD",
    )
    file_import_remesh_preset: bpy.props.EnumProperty(items=REMESH_PRESET_ITEMS, default="HIGH")
    file_import_voxel_size: bpy.props.FloatProperty(
        name="Voxel Size", description="Voxel size used by Blender's native Remesh modifier",
        default=0.003, min=0.000001, soft_max=1.0, precision=4, unit="LENGTH",
    )
    file_import_separate_collections: bpy.props.BoolProperty(default=True)
    batch_auto_remesh: bpy.props.BoolProperty(
        name="Auto Remesh",
        default=True,
    )
    batch_clear_material: bpy.props.BoolProperty(
        name="Clear Material",
        description="Replace transferred materials on the remeshed result with a plain gray material",
        default=True,
    )
    batch_remesh_method: bpy.props.EnumProperty(
        name="Remesh Type", items=IMPORT_REMESH_METHOD_ITEMS, default="QUAD",
    )
    batch_remesh_preset: bpy.props.EnumProperty(items=REMESH_PRESET_ITEMS, default="HIGH")
    batch_voxel_size: bpy.props.FloatProperty(
        name="Voxel Size", description="Voxel size used by Blender's native Remesh modifier",
        default=0.003, min=0.000001, soft_max=1.0, precision=4, unit="LENGTH",
    )
    batch_separate_collections: bpy.props.BoolProperty(default=True)
    batch_expanded_stages: bpy.props.IntProperty(
        name="Expanded Batch Stages", default=0, min=0,
        description="Controls which processing stages are expanded in the import panels",
    )
    batch_stage_2_enabled: bpy.props.BoolProperty(
        name="Stage 2: First Remesh", default=True,
        description="Run the first remesh and Smart UV pass",
    )
    batch_first_surface_angle: bpy.props.FloatProperty(
        name="Surface Angle", default=radians(22.0),
        min=radians(1.0), max=radians(89.0), subtype="ANGLE",
        description="Surface angle for Stage 2 Smart UV seam generation",
    )
    batch_first_uv_repair_enabled: bpy.props.BoolProperty(
        name="Smart UV Repair", default=True,
        description="Run Smart UV Repair after the first remesh and before Auto Unwrap",
    )
    batch_first_geometry_repair: bpy.props.BoolProperty(
        name="Geometry Repair", default=True,
        description="Repair folded pockets, degenerate edges and zero-area seam triangles at the end of the first remesh pass",
    )
    batch_stage_3_geometry_repair: bpy.props.BoolProperty(
        name="Geometry Repair", default=True,
        description="Run all three geometry repairs at the end of the second remesh pass",
    )
    batch_stage_4_geometry_repair: bpy.props.BoolProperty(
        name="Geometry Repair", default=True,
        description="Run all three geometry repairs after the third pass and before UV packing and baking",
    )
    batch_first_uv_repair_threshold: bpy.props.FloatProperty(
        name="Critical Stretch Ratio", default=4.0, min=1.1, max=1000.0,
    )
    batch_first_uv_repair_min_faces: bpy.props.IntProperty(
        name="Minimum Region Faces", default=6, min=1,
    )
    batch_first_uv_repair_surface_angle: bpy.props.FloatProperty(
        name="Surface Angle", default=radians(45.0),
        min=0.0, max=radians(180.0), subtype="ANGLE",
    )
    batch_first_remove_small_loose_parts: bpy.props.BoolProperty(
        name="Remove Small Loose Parts",
        default=True,
        description="Automatically remove small disconnected components before the first Auto Unwrap",
    )
    batch_first_small_loose_part_threshold_percent: bpy.props.FloatProperty(
        name="Remove Below",
        default=8.0,
        min=0.0,
        max=100.0,
        soft_max=25.0,
        precision=1,
        subtype="PERCENTAGE",
        description="Remove parts smaller than this percentage of the largest disconnected part",
    )
    batch_first_small_loose_part_metric: bpy.props.EnumProperty(
        name="Loose Part Size",
        description="How disconnected part size is measured before the first Auto Unwrap",
        items=(
            (
                "BOUNDING_BOX",
                "Bounding Box",
                "Use bounding-box size with flat and linear geometry support",
            ),
            (
                "VOLUME",
                "Volume",
                "Use enclosed volume; automatically use bounding-box size for open geometry",
            ),
        ),
        default="BOUNDING_BOX",
    )
    batch_narrow_island_enabled: bpy.props.BoolProperty(
        name="Stage 3: Narrow Island Splitter", default=True,
        description="Split narrow UV islands after the first remesh and before the second",
    )
    batch_narrow_island_max_width_percent: bpy.props.FloatProperty(
        name="Max Physical Width (%)", default=10.0, min=0.0, max=100.0, precision=1,
        description="Maximum thickness for the Stage 3 narrow island splitter",
    )
    batch_small_islands_enabled: bpy.props.BoolProperty(
        name="Stage 4: Small Islands Merger", default=True,
        description="Merge small seam islands before the second remesh pass",
    )
    batch_small_island_threshold: bpy.props.FloatProperty(
        name="Area Threshold (%)", default=5.0, min=1.0, max=49.0,
        description="Percentage of the largest seam island area in each connected mesh component",
    )
    batch_small_island_protect_pinned: bpy.props.BoolProperty(
        name="Protect Pinned Edges", default=True,
        description="Never remove pinned seams during the batch merge",
    )
    batch_small_island_protect_sharp: bpy.props.BoolProperty(
        name="Protect Sharp Edges", default=True,
    )
    batch_small_island_protect_materials: bpy.props.BoolProperty(
        name="Protect Material Boundaries", default=False,
    )
    # Keep existing RNA identifiers so saved .blend files retain remesh/pack choices.
    batch_stage_3_enabled: bpy.props.BoolProperty(
        name="Stage 5: Second Remesh", default=True,
        description="Remesh the result of the preceding enabled stage at the selected density",
    )
    batch_stage_3_auto_remesh: bpy.props.BoolProperty(name="Auto Remesh", default=True)
    batch_stage_3_remesh_preset: bpy.props.EnumProperty(items=REMESH_PRESET_ITEMS, default="MID")
    batch_stage_3_use_materials: bpy.props.BoolProperty(name="Use Materials", default=True)
    batch_stage_3_prepare_polygroups: bpy.props.BoolProperty(name="Prepare Poly Groups", default=True)
    batch_stage_3_material_seams: bpy.props.BoolProperty(name="Auto Generate Seams from Materials", default=True)
    batch_stage_3_smart_relax_edges: bpy.props.BoolProperty(
        name="Smart Relax Edges", default=True,
        description="Smart-relax the generated result's seam edges before UV unwrapping",
    )
    batch_stage_3_autofix_enabled: bpy.props.BoolProperty(
        name="Autofix", default=True,
        description="Repair the second remesh result before Angle Based UV unwrapping",
    )
    batch_stage_3_autofix_fin_loose: bpy.props.BoolProperty(
        name="Remove Fin Faces and Loose Geometry", default=True,
        description="Remove thin protruding fin faces, wire edges, and loose vertices",
    )
    batch_stage_3_autofix_close_nonmanifold: bpy.props.BoolProperty(
        name="Close Open Boundaries", default=True,
        description="Fill open non-manifold boundary loops",
    )
    batch_stage_3_autofix_triangulate_ngons: bpy.props.BoolProperty(
        name="Triangulate N-gons", default=True,
        description="Triangulate faces with more than four sides",
    )
    batch_stage_3_remove_small_loose_parts: bpy.props.BoolProperty(
        name="Remove Small Loose Parts",
        default=True,
        description="Automatically remove small disconnected components before Autofix Before Unwrap",
    )
    batch_stage_3_small_loose_part_threshold_percent: bpy.props.FloatProperty(
        name="Remove Below",
        default=8.0,
        min=0.0,
        max=100.0,
        soft_max=25.0,
        precision=1,
        subtype="PERCENTAGE",
        description="Remove parts smaller than this percentage of the largest disconnected part",
    )
    batch_stage_3_small_loose_part_metric: bpy.props.EnumProperty(
        name="Loose Part Size",
        description="How disconnected part size is measured before Autofix Before Unwrap",
        items=(
            (
                "BOUNDING_BOX",
                "Bounding Box",
                "Use bounding-box size with flat and linear geometry support",
            ),
            (
                "VOLUME",
                "Volume",
                "Use enclosed volume; automatically use bounding-box size for open geometry",
            ),
        ),
        default="BOUNDING_BOX",
    )
    batch_stage_3_auto_unwrap: bpy.props.BoolProperty(name="Auto Unwrap", default=True)
    batch_stage_3_uv_repair_enabled: bpy.props.BoolProperty(
        name="Smart UV Repair", default=True,
        description="Run Smart UV Repair after Auto Unwrap in remesh pass 2",
    )
    batch_stage_3_uv_repair_threshold: bpy.props.FloatProperty(
        name="Critical Stretch Ratio", default=4.0, min=1.1, max=1000.0,
    )
    batch_stage_3_uv_repair_min_faces: bpy.props.IntProperty(
        name="Minimum Region Faces", default=6, min=1,
    )
    batch_stage_3_uv_repair_surface_angle: bpy.props.FloatProperty(
        name="Surface Angle", default=radians(45.0),
        min=0.0, max=radians(180.0), subtype="ANGLE",
    )
    batch_stage_3_auto_unwrap_method: bpy.props.EnumProperty(
        name="Unwrap Method", items=BATCH_REMESH_UNWRAP_METHOD_ITEMS, default="ANGLE",
    )
    batch_second_narrow_island_enabled: bpy.props.BoolProperty(
        name="Stage 6: Narrow Island Splitter", default=True,
        description="Split narrow islands after the second remesh pass",
    )
    batch_second_narrow_island_width: bpy.props.IntProperty(
        name="Thin Width (face rows)", default=3, min=1, max=12,
    )
    batch_second_narrow_island_max_width_percent: bpy.props.FloatProperty(
        name="Max Physical Width (%)", default=6.0, min=0.0, max=100.0, precision=1,
        description="Maximum thickness compared with the widest part of each island; zero disables this filter",
    )
    batch_second_narrow_island_min_area_percent: bpy.props.FloatProperty(
        name="Minimum Island Area (%)", default=2.0, min=0.0, max=100.0, precision=1,
        description="Skip the cut if its result is smaller than this share of the island; zero disables the filter",
    )
    batch_second_narrow_island_min_faces: bpy.props.IntProperty(
        name="Minimum Part Faces", default=8, min=2, max=10000,
    )
    batch_second_narrow_island_min_length: bpy.props.IntProperty(
        name="Minimum Branch Depth", default=3, min=1, max=100,
    )
    batch_second_narrow_island_create_edges: bpy.props.BoolProperty(
        name="Create New Edges", default=True,
    )
    batch_second_narrow_island_smart_relax: bpy.props.BoolProperty(
        name="Smart Relax", default=True,
    )
    batch_second_small_islands_enabled: bpy.props.BoolProperty(
        name="Stage 7: Small Islands Merger", default=True,
        description="Merge small seam islands after the second narrow island pass",
    )
    batch_second_small_island_threshold: bpy.props.FloatProperty(
        name="Area Threshold (%)", default=5.0, min=1.0, max=49.0,
        description="Percentage of the largest seam island area in each connected mesh component",
    )
    batch_second_small_island_protect_pinned: bpy.props.BoolProperty(
        name="Protect Pinned Edges", default=True,
        description="Never remove pinned seams during the batch merge",
    )
    batch_second_small_island_protect_sharp: bpy.props.BoolProperty(
        name="Protect Sharp Edges", default=True,
    )
    batch_second_small_island_protect_materials: bpy.props.BoolProperty(
        name="Protect Material Boundaries", default=False,
    )
    batch_stage_4_enabled: bpy.props.BoolProperty(
        name="Stage 8: Third Remesh", default=True,
        description="Remesh the result of the preceding enabled stage at the selected density",
    )
    batch_stage_4_auto_remesh: bpy.props.BoolProperty(name="Auto Remesh", default=True)
    batch_stage_4_remesh_preset: bpy.props.EnumProperty(items=REMESH_PRESET_ITEMS, default="MID")
    batch_stage_4_use_materials: bpy.props.BoolProperty(name="Use Materials", default=True)
    batch_stage_4_prepare_polygroups: bpy.props.BoolProperty(name="Prepare Poly Groups", default=True)
    batch_stage_4_material_seams: bpy.props.BoolProperty(name="Auto Generate Seams from Materials", default=True)
    batch_stage_4_smart_relax_edges: bpy.props.BoolProperty(
        name="Smart Relax Edges", default=True,
        description="Smart-relax the generated result's seam edges before UV unwrapping",
    )
    batch_stage_4_remove_small_loose_parts: bpy.props.BoolProperty(
        name="Remove Small Loose Parts",
        default=True,
        description="Automatically remove small disconnected components before Autofix Before Unwrap",
    )
    batch_stage_4_small_loose_part_threshold_percent: bpy.props.FloatProperty(
        name="Remove Below",
        default=8.0,
        min=0.0,
        max=100.0,
        soft_max=25.0,
        precision=1,
        subtype="PERCENTAGE",
        description="Remove parts smaller than this percentage of the largest disconnected part",
    )
    batch_stage_4_small_loose_part_metric: bpy.props.EnumProperty(
        name="Loose Part Size",
        description="How disconnected part size is measured before Autofix Before Unwrap",
        items=(
            (
                "BOUNDING_BOX",
                "Bounding Box",
                "Use bounding-box size with flat and linear geometry support",
            ),
            (
                "VOLUME",
                "Volume",
                "Use enclosed volume; automatically use bounding-box size for open geometry",
            ),
        ),
        default="BOUNDING_BOX",
    )
    batch_stage_4_autofix_enabled: bpy.props.BoolProperty(
        name="Autofix", default=True,
        description="Repair the third remesh result before Angle Based UV unwrapping",
    )
    batch_stage_4_autofix_fin_loose: bpy.props.BoolProperty(
        name="Remove Fin Faces and Loose Geometry", default=True,
        description="Remove thin protruding fin faces, wire edges, and loose vertices",
    )
    batch_stage_4_autofix_close_nonmanifold: bpy.props.BoolProperty(
        name="Close Open Boundaries", default=True,
        description="Fill open non-manifold boundary loops",
    )
    batch_stage_4_autofix_triangulate_ngons: bpy.props.BoolProperty(
        name="Triangulate N-gons", default=True,
        description="Triangulate faces with more than four sides",
    )
    batch_stage_4_auto_unwrap: bpy.props.BoolProperty(name="Auto Unwrap", default=True)
    batch_stage_4_uv_repair_enabled: bpy.props.BoolProperty(
        name="Smart UV Repair", default=True,
        description="Run Smart UV Repair after Auto Unwrap in remesh pass 3",
    )
    batch_stage_4_uv_repair_threshold: bpy.props.FloatProperty(
        name="Critical Stretch Ratio", default=4.0, min=1.1, max=1000.0,
    )
    batch_stage_4_uv_repair_min_faces: bpy.props.IntProperty(
        name="Minimum Region Faces", default=6, min=1,
    )
    batch_stage_4_uv_repair_surface_angle: bpy.props.FloatProperty(
        name="Surface Angle", default=radians(45.0),
        min=0.0, max=radians(180.0), subtype="ANGLE",
    )
    batch_stage_4_auto_unwrap_method: bpy.props.EnumProperty(
        name="Unwrap Method", items=BATCH_REMESH_UNWRAP_METHOD_ITEMS, default="ANGLE",
    )
    batch_stage_5_enabled: bpy.props.BoolProperty(
        name="Stage 9: UV Packing", default=True,
        description="Pack final UV islands with UVPackmaster",
    )
    batch_autobake_enabled: bpy.props.BoolProperty(
        name="Stage 10: Auto Bake", default=True,
        description="Bake final remeshes from their matching highpoly sources and save textures",
    )
    batch_autobake_cage_mode: bpy.props.EnumProperty(
        name="Cage Mode",
        items=(
            ("AUTO", "Auto Cage", "Calculate cage extrusion automatically"),
            ("SMART", "Smart Cage Object", "Find or generate a Smart Cage object for each lowpoly"),
        ),
        default="AUTO",
    )
    batch_smart_decimate_enabled: bpy.props.BoolProperty(
        name="Stage 11: Smart Decimate", default=False, update=_update_batch_smart_decimate,
    )
    batch_smart_decimate_triangle_limit: bpy.props.IntProperty(
        name="Triangle Limit", default=3000, min=1, step=1000,
    )
    batch_smart_lods_enabled: bpy.props.BoolProperty(
        name="Stage 12: Smart LODs", default=False, update=_update_batch_smart_lods,
    )
    batch_smart_lods_count: bpy.props.IntProperty(name="LOD Count", default=5, min=1, max=5)
    batch_smart_lods_target_1: bpy.props.IntProperty(name="LOD0 Tris", default=3000, min=1)
    batch_smart_lods_target_2: bpy.props.IntProperty(name="LOD1 Tris", default=1500, min=1)
    batch_smart_lods_target_3: bpy.props.IntProperty(name="LOD2 Tris", default=1000, min=1)
    batch_smart_lods_target_4: bpy.props.IntProperty(name="LOD3 Tris", default=500, min=1)
    batch_smart_lods_target_5: bpy.props.IntProperty(name="LOD4 Tris", default=150, min=1)
    batch_smart_lods_final_decimate: bpy.props.BoolProperty(name="Final Decimate Fallback", default=False)
    batch_smart_lods_triangulate_all: bpy.props.BoolProperty(name="Triangulate All LODs", default=False)
    batch_redo_collection_name: bpy.props.StringProperty(
        name="Redo Collection", description="Generated.N collection selected for rebuilding",
    )
    batch_is_paused: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    batch_stop_requested: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    batch_cancel_requested: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    batch_failed_count: bpy.props.IntProperty(default=0, min=0)
    batch_stage: bpy.props.StringProperty(default="")
    batch_last_error: bpy.props.StringProperty(default="")
    batch_elapsed_seconds: bpy.props.FloatProperty(default=0.0, min=0.0)
    batch_current_seconds: bpy.props.FloatProperty(default=0.0, min=0.0)
    batch_average_seconds: bpy.props.FloatProperty(default=0.0, min=0.0)
    batch_eta_seconds: bpy.props.FloatProperty(default=-1.0, min=-1.0)
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
    batch_current_progress: bpy.props.FloatProperty(
        name="Current Progress",
        description="Processing progress of the current file",
        default=0.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
    )
    batch_remesh_progress: bpy.props.FloatProperty(
        name="Current Remesh Progress",
        description="Progress of the currently running remesh action",
        default=0.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        options={"SKIP_SAVE"},
    )
    batch_baking_progress: bpy.props.FloatProperty(
        name="Current Baking Progress",
        description="Progress of the currently running bake action",
        default=0.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        options={"SKIP_SAVE"},
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


class POLYGROUPS_PG_remesh_status(bpy.types.PropertyGroup):
    is_running: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    cancel_requested: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    stage: bpy.props.StringProperty(default="")
    message: bpy.props.StringProperty(default="")
    source_name: bpy.props.StringProperty(default="")
    result_name: bpy.props.StringProperty(default="")
    progress: bpy.props.FloatProperty(default=0.0, min=0.0, max=100.0)
    elapsed_seconds: bpy.props.FloatProperty(default=0.0, min=0.0)
    polygon_count: bpy.props.IntProperty(default=0, min=0)


class AIRETOPO_PG_panel_visibility_settings(bpy.types.PropertyGroup):
    panel_search: bpy.props.StringProperty(
        name="Search",
        description="Filter AI Retopo sections, tools, and settings",
        default="",
        update=_redraw_view3d,
    )
    topic_import_0: bpy.props.BoolProperty(default=False)
    topic_import_1: bpy.props.BoolProperty(default=False)
    topic_import_2: bpy.props.BoolProperty(default=False)
    topic_import_3: bpy.props.BoolProperty(default=False)
    topic_batch_0: bpy.props.BoolProperty(default=False)
    topic_batch_1: bpy.props.BoolProperty(default=False)
    topic_batch_2: bpy.props.BoolProperty(default=False)
    topic_batch_3: bpy.props.BoolProperty(default=False)
    topic_batch_4: bpy.props.BoolProperty(default=False)
    topic_batch_5: bpy.props.BoolProperty(default=False)
    topic_prepare_0: bpy.props.BoolProperty(default=False)
    topic_prepare_1: bpy.props.BoolProperty(default=False)
    topic_prepare_1_manual: bpy.props.BoolProperty(default=True)
    topic_prepare_1_auto: bpy.props.BoolProperty(default=True)
    topic_prepare_2: bpy.props.BoolProperty(default=False)
    topic_prepare_3: bpy.props.BoolProperty(default=False)
    topic_seam_prep_0: bpy.props.BoolProperty(default=False)
    topic_seam_prep_1: bpy.props.BoolProperty(default=False)
    topic_seam_prep_1_manual: bpy.props.BoolProperty(default=True)
    topic_seam_prep_1_auto: bpy.props.BoolProperty(default=True)
    topic_seam_prep_2: bpy.props.BoolProperty(default=False)
    topic_seam_prep_3: bpy.props.BoolProperty(default=False)
    topic_seam_prep_4: bpy.props.BoolProperty(default=False)
    topic_seam_prep_5: bpy.props.BoolProperty(default=False)
    topic_seam_prep_6: bpy.props.BoolProperty(default=False)
    topic_seam_prep_7: bpy.props.BoolProperty(default=False)
    topic_polygroups_0: bpy.props.BoolProperty(default=False)
    topic_polygroups_1: bpy.props.BoolProperty(default=False)
    topic_polygroups_2: bpy.props.BoolProperty(default=False)
    topic_bake_0: bpy.props.BoolProperty(default=False)
    topic_bake_1: bpy.props.BoolProperty(default=False)
    topic_bake_2: bpy.props.BoolProperty(default=False)
    topic_bake_3: bpy.props.BoolProperty(default=False)
    topic_bake_4: bpy.props.BoolProperty(default=False)
    topic_uv_0: bpy.props.BoolProperty(default=False)
    topic_uv_1: bpy.props.BoolProperty(default=False)
    topic_uv_2: bpy.props.BoolProperty(default=False)
    topic_uv_3: bpy.props.BoolProperty(default=False)
    topic_sculpt_0: bpy.props.BoolProperty(default=False)
    topic_sculpt_1: bpy.props.BoolProperty(default=False)
    topic_seam_final_0: bpy.props.BoolProperty(default=False)
    topic_seam_final_1: bpy.props.BoolProperty(default=False)
    topic_seam_final_2: bpy.props.BoolProperty(default=False)
    topic_seam_final_3: bpy.props.BoolProperty(default=False)
    topic_seam_final_4: bpy.props.BoolProperty(default=False)
    topic_seam_final_5: bpy.props.BoolProperty(default=False)
    topic_ai_0: bpy.props.BoolProperty(default=False)
    topic_ai_1: bpy.props.BoolProperty(default=False)
    topic_ai_2: bpy.props.BoolProperty(default=False)
    topic_ai_3: bpy.props.BoolProperty(default=False)
    topic_render_0: bpy.props.BoolProperty(default=False)
    topic_render_1: bpy.props.BoolProperty(default=False)
    topic_render_2: bpy.props.BoolProperty(default=False)
    topic_render_3: bpy.props.BoolProperty(default=False)
    topic_render_4: bpy.props.BoolProperty(default=False)
    topic_render_5: bpy.props.BoolProperty(default=False)
    topic_render_6: bpy.props.BoolProperty(default=False)
    topic_render_7: bpy.props.BoolProperty(default=False)
    topic_render_8: bpy.props.BoolProperty(default=False)
    topic_render_9: bpy.props.BoolProperty(default=False)
    topic_render_10: bpy.props.BoolProperty(default=False)
    topic_render_11: bpy.props.BoolProperty(default=False)
    topic_render_12: bpy.props.BoolProperty(default=False)
    topic_remesh_0: bpy.props.BoolProperty(default=False)
    topic_remesh_1: bpy.props.BoolProperty(default=False)
    topic_export_0: bpy.props.BoolProperty(default=False)
    topic_export_1: bpy.props.BoolProperty(default=False)
    topic_export_2: bpy.props.BoolProperty(default=False)
    topic_export_3: bpy.props.BoolProperty(default=False)
    single_section_mode: bpy.props.BoolProperty(
        name="Single Mode",
        description="Keep only one main toolkit section expanded at a time",
        default=True,
        update=_single_section_mode_update,
    )
    show_import_section: bpy.props.BoolProperty(default=True, update=_panel_visibility_update("show_import_section"))
    show_batch_import_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_batch_import_section"))
    show_model_preparation_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_model_preparation_section"))
    show_seam_preparation_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_seam_preparation_section"))
    show_polygroups_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_polygroups_section"))
    show_remesh_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_remesh_section"))
    show_resculpting_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_resculpting_section"))
    show_seam_finalization_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_seam_finalization_section"))
    show_uv_preparation_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_uv_preparation_section"))
    show_baking_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_baking_section"))
    show_ai_generation_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_ai_generation_section"))
    show_mesh_finalization_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_mesh_finalization_section"))
    show_render_section: bpy.props.BoolProperty(default=False, update=_panel_visibility_update("show_render_section"))
