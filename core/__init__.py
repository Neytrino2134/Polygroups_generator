from .facesets import assign_face_sets_from_materials
from .materials import assign_materials, clear_materials
from .mesh_segmentation import get_seam_edges, split_into_groups

__all__ = (
    "assign_face_sets_from_materials",
    "assign_materials",
    "clear_materials",
    "get_seam_edges",
    "split_into_groups",
)
