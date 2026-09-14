"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
source = bpy.context.object
source.name = "Mesh.002"
collection = bpy.data.collections.new("Generated.002")
bpy.context.scene.collection.children.link(collection)
for previous in tuple(source.users_collection):
    previous.objects.unlink(source)
collection.objects.link(source)
for edge in source.data.edges:
    edge.use_seam = all(abs(source.data.vertices[i].co.y) < 1e-5 for i in edge.vertices)
settings = bpy.context.scene.polygroups_mesh_finalization_settings
assert not settings.smart_lods_auto_arrange
assert abs(settings.smart_lods_spacing - 1.0) < 1e-6
settings.smart_lods_count = 4
for i, target in enumerate((700, 400, 200, 100), 1):
    setattr(settings, f"smart_lods_target_{i}", target)
source_tris = len(source.data.loop_triangles)
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
previous_count = source_tris
for i, target in enumerate((700, 400, 200, 100), 1):
    lod = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    tris = len(lod.data.loop_triangles)
    assert 0 < tris <= target, (i, tris, target)
    assert tris <= previous_count
    assert lod.users_collection == source.users_collection
    assert len(lod.modifiers) == 0
    assert (lod.matrix_world.translation - source.matrix_world.translation).length < 1e-6
    previous_count = tris
assert len(source.data.loop_triangles) == source_tris

# An impossible final limit keeps all four objects and the smallest final mesh.
for i in range(1, 5):
    obj = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)
settings.smart_lods_target_4 = 1
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
assert all(f"Mesh.002.LOD.{i}" in bpy.data.objects for i in range(1, 5))
smart_floor = len(bpy.data.objects["Mesh.002.LOD.4"].data.loop_triangles)
assert smart_floor > 1
for i in range(1, 5):
    obj = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)

# The optional unrestricted pass only runs once the seam-aware passes stall.
settings.smart_lods_final_decimate = True
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
assert all(f"Mesh.002.LOD.{i}" in bpy.data.objects for i in range(1, 5))
fallback_count = len(bpy.data.objects["Mesh.002.LOD.4"].data.loop_triangles)
assert fallback_count < smart_floor, (fallback_count, smart_floor)
assert all(len(bpy.data.objects[f"Mesh.002.LOD.{i}"].modifiers) == 0 for i in range(1, 5))
for i in range(1, 5):
    obj = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)

# The final pass can bring a stalled seam-aware result inside the limit.
settings.smart_lods_target_4 = 4
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
assert len(bpy.data.objects["Mesh.002.LOD.4"].data.loop_triangles) <= 4
for i in range(1, 5):
    obj = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)

# Triangulation is applied to every generated mesh and does not exceed budgets.
settings.smart_lods_triangulate_all = True
settings.smart_lods_target_4 = 100
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
for i, target in enumerate((700, 400, 200, 100), 1):
    lod = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    assert all(len(face.vertices) == 3 for face in lod.data.polygons)
    assert len(lod.data.polygons) == len(lod.data.loop_triangles) <= target
    assert len(lod.modifiers) == 0
for i in range(1, 5):
    obj = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)

# Auto Arrange uses object bounds, so rotated and scaled meshes have a real gap.
source.location = (2.0, 3.0, 0.0)
source.rotation_euler.z = 0.4
source.scale = (1.5, 0.8, 1.0)
settings.smart_lods_auto_arrange = True
settings.smart_lods_spacing = 1.0
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}

def x_bounds(obj):
    coords = [(obj.matrix_world @ Vector(corner)).x for corner in obj.bound_box]
    return min(coords), max(coords)

previous = source
for i in range(1, 5):
    lod = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    gap = x_bounds(lod)[0] - x_bounds(previous)[1]
    assert abs(gap - 1.0) < 1e-4, (i, gap)
    assert abs(lod.matrix_world.translation.y - source.matrix_world.translation.y) < 1e-6
    previous = lod
for i in range(1, 5):
    obj = bpy.data.objects[f"Mesh.002.LOD.{i}"]
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)

# The spacing control also accepts a custom gap.
settings.smart_lods_count = 1
settings.smart_lods_spacing = 2.5
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
lod = bpy.data.objects["Mesh.002.LOD.1"]
assert abs(x_bounds(lod)[0] - x_bounds(source)[1] - 2.5) < 1e-4
mesh = lod.data
bpy.data.objects.remove(lod, do_unlink=True)
bpy.data.meshes.remove(mesh)

# A mesh without seams still gets a full-mesh LOD, also when run from Edit Mode.
settings.smart_lods_spacing = 1.0
settings.smart_lods_target_1 = 300
for edge in source.data.edges:
    edge.use_seam = False
bpy.ops.object.mode_set(mode="EDIT")
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
assert bpy.context.active_object == source and source.mode == "EDIT"
assert len(bpy.data.objects["Mesh.002.LOD.1"].data.loop_triangles) <= 300
print("SMART_LODS_TEST_PASSED")
