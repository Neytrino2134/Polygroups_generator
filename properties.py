import bpy


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


class POLYGROUPS_PG_knife_seam_settings(bpy.types.PropertyGroup):
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


CLASSES = (
    POLYGROUPS_PG_model_preparation_settings,
    POLYGROUPS_PG_knife_seam_settings,
    POLYGROUPS_PG_quick_knife_seam_settings,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.polygroups_model_preparation_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_model_preparation_settings,
    )
    bpy.types.Scene.polygroups_knife_seam_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_knife_seam_settings,
    )
    bpy.types.Scene.polygroups_quick_knife_seam_settings = bpy.props.PointerProperty(
        type=POLYGROUPS_PG_quick_knife_seam_settings,
    )


def unregister():
    del bpy.types.Scene.polygroups_quick_knife_seam_settings
    del bpy.types.Scene.polygroups_knife_seam_settings
    del bpy.types.Scene.polygroups_model_preparation_settings

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
