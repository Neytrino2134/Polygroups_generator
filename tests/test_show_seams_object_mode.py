import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Matrix
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator import seam_object_overlay as overlay
from polygroups_generator.seam_object_overlay import seam_line_points


settings = bpy.context.scene.polygroups_seam_preparation_settings
assert settings.show_seams_object_mode is False
assert settings.seam_overlay_max_polygons == 500000
heavy = SimpleNamespace(type="MESH", data=SimpleNamespace(polygons=range(500001)))
assert overlay.exceeds_polygon_limit(heavy, 500000)
assert not overlay.exceeds_polygon_limit(heavy, 0)

mesh = bpy.data.meshes.new("Show Seams Test Mesh")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 1), (1, 2)], [])
mesh.edges[1].use_seam = True
obj = bpy.data.objects.new("Show Seams Test", mesh)
obj.matrix_world = Matrix.Translation((2.0, 3.0, 4.0))

points = seam_line_points(obj)
assert len(points) == 2
assert tuple(points[0]) == (3.0, 3.0, 4.0)
assert tuple(points[1]) == (3.0, 4.0, 4.0)

# An unchanged object reuses its GPU batch without walking all edges again.
key = overlay._cache_key(obj)
overlay._BATCH_CACHE = (key, "cached batch")
overlay._CACHE_ID_POINTERS = {obj.as_pointer(), mesh.as_pointer()}
original_points = overlay.seam_line_points
overlay.seam_line_points = lambda _obj: (_ for _ in ()).throw(AssertionError("seams rebuilt"))
assert overlay._seam_batch(obj) == "cached batch"
overlay.seam_line_points = original_points


class FakeID:
    def __init__(self, pointer):
        self.pointer = pointer
        self.original = self

    def as_pointer(self):
        return self.pointer


unrelated = SimpleNamespace(
    id=FakeID(456), is_updated_geometry=True, is_updated_transform=False
)
overlay.invalidate_geometry(None, SimpleNamespace(updates=[unrelated]))
assert overlay._BATCH_CACHE is not None
related = SimpleNamespace(
    id=FakeID(obj.as_pointer()), is_updated_geometry=True, is_updated_transform=False
)
overlay.invalidate_geometry(None, SimpleNamespace(updates=[related]))
assert overlay._BATCH_CACHE is None

bpy.data.objects.remove(obj, do_unlink=True)
print("SHOW_SEAMS_OBJECT_MODE_TEST_PASSED")
