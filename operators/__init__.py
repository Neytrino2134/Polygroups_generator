from .apply_weld import OBJECT_OT_polygroups_apply_weld
from .clear_materials import OBJECT_OT_clear_polygroups_materials
from .face_sets_to_materials import OBJECT_OT_face_sets_to_materials
from .generate_polygroups import OBJECT_OT_generate_polygroups
from .knife_seam_tool import MESH_OT_polygroups_knife_seam
from .quick_knife_seam_tool import MESH_OT_polygroups_quick_knife_seam

CLASSES = (
    OBJECT_OT_polygroups_apply_weld,
    OBJECT_OT_generate_polygroups,
    OBJECT_OT_face_sets_to_materials,
    OBJECT_OT_clear_polygroups_materials,
    MESH_OT_polygroups_knife_seam,
    MESH_OT_polygroups_quick_knife_seam,
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
