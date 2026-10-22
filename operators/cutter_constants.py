"""Stable cutter metadata, collection names and geometric limits."""
from math import radians


CUTTER_COLLECTION_NAME = "Seam Cutters"
CUTTER_COLLECTION_BY_TOOL = {
    "PLANE": "Seam Cutters Plane",
    "GRID_PLANE": "Seam Cutters Grid",
    "ARC": "Seam Cutters Arc",
    "LOCAL_RING": "Seam Cutters Local Ring",
    "LOCAL_CONTOUR": "Seam Cutters Local Contour",
    "PATH": "Seam Cutters Path",
    "DRAW": "Seam Cutters Draw",
}
CUTTER_PROP = "polygroups_object_seam_cutter"
CUTTER_TYPE_PROP = "polygroups_object_seam_cutter_type"
CUTTER_PIN_SEAMS_PROP = "polygroups_object_seam_cutter_pin_seams"
CUTTER_SOURCE_TOOL_PROP = "polygroups_object_seam_cutter_source_tool"
CUTTER_PATH_DATA_PROP = "polygroups_object_seam_cutter_path_data"
CUTTER_DRAW_DATA_PROP = "polygroups_object_seam_cutter_draw_data"
CUTTER_BACKUP_PREFIX = "Backup_"
CUTTER_BACKUP_COLLECTION_NAME = "Cutter Backups"
CUTTER_BACKUP_OWNER_PROP = "polygroups_cutter_backup_owner"
CUTTER_BACKUP_SNAPSHOT_PROP = "polygroups_cutter_backup_snapshot"
CUTTER_INSTANCE_ID_PROP = "polygroups_cutter_instance_id"
CUTTER_ORIGINAL_NAME_PROP = "polygroups_cutter_original_name"
CUTTER_SOLIDIFY_MODIFIER_NAME = "Cutter Plane Thickness"
AUTOWELD_MODIFIER_NAME = "Retopo Weld"
AUTOWELD_VERTEX_GROUP_NAME = "Cutter Seam Weld"
BOOLEAN_PATH_TEMP_MATERIAL_NAME = "__AI_RETOPO_PATH_CUTTER_TEMP__"
BOOLEAN_PATH_PLACEHOLDER_MATERIAL_NAME = "__AI_RETOPO_PATH_ORIGINAL_TEMP__"
DEFAULT_CUTTER_PATH_TILT = radians(90.0)
CUTTER_PATH_TILT_STEP = radians(15.0)
DEFAULT_NON_PLANE_CUTTER_THICKNESS = 0.0001
AUTOFIX_MAX_PROTRUSION_FACES = 2000
AUTOFIX_MAX_LOOSE_GEOMETRY = 10000
AUTOFIX_MAX_HOLE_EDGE_COUNT = 128
AUTOFIX_MAX_HOLE_LOOPS = 16
