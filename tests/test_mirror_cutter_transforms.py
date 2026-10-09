"""Mirrored cutter copies must apply only scale and preserve reflected geometry."""

from pathlib import Path
import sys

import addon_utils
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators import object_seam_cutter as cutter


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

bpy.ops.mesh.primitive_cube_add(location=(2.0, 0.0, 0.0))
target = bpy.context.active_object
target.name = "Mirror Target"

bpy.ops.mesh.primitive_plane_add(location=(3.0, 1.0, 0.5), rotation=(0.2, 0.3, 0.4))
source = bpy.context.active_object
source.name = "Transform Cutter"
source.scale = (1.5, 0.75, 2.0)
source[cutter.CUTTER_PROP] = True
source[cutter.CUTTER_TYPE_PROP] = "PLANE"

source.select_set(True)
target.select_set(True)
bpy.context.view_layer.objects.active = target
bpy.context.scene.polygroups_object_seam_cutter_settings.cutter_mirror_axis = "X"

bpy.context.view_layer.update()
reflection = cutter._mirror_matrix_from_target(target, "X")
expected_matrix = reflection @ source.matrix_world
expected_points = [expected_matrix @ vertex.co for vertex in source.data.vertices]
expected_location, expected_rotation, _ = expected_matrix.decompose()
source_matrix = source.matrix_world.copy()
assert bpy.ops.object.polygroups_copy_mirror_cutters() == {"FINISHED"}
mirrored = bpy.data.objects["Transform Cutter_Mirror"]

assert (mirrored.location - expected_location).length < 1e-6
assert mirrored.rotation_euler.to_quaternion().rotation_difference(expected_rotation).angle < 1e-6
bpy.context.view_layer.update()
for vertex, expected in zip(mirrored.data.vertices, expected_points):
    assert (mirrored.matrix_world @ vertex.co - expected).length < 1e-5
assert all(abs(source.matrix_world[i][j] - source_matrix[i][j]) < 1e-6 for i in range(4) for j in range(4))
assert (Vector(mirrored.scale) - Vector((1.0, 1.0, 1.0))).length < 1e-6, mirrored.scale
assert bpy.context.view_layer.objects.active == target

print("MIRROR_CUTTER_TRANSFORMS_OK", flush=True)
