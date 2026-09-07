import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.seam_object_overlay import seam_line_points


settings = bpy.context.scene.polygroups_seam_preparation_settings
assert settings.show_seams_object_mode is False

mesh = bpy.data.meshes.new("Show Seams Test Mesh")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 1), (1, 2)], [])
mesh.edges[1].use_seam = True
obj = bpy.data.objects.new("Show Seams Test", mesh)
obj.matrix_world = Matrix.Translation((2.0, 3.0, 4.0))

points = seam_line_points(obj)
assert len(points) == 2
assert tuple(points[0]) == (3.0, 3.0, 4.0)
assert tuple(points[1]) == (3.0, 4.0, 4.0)

bpy.data.objects.remove(obj, do_unlink=True)
print("SHOW_SEAMS_OBJECT_MODE_TEST_PASSED")
