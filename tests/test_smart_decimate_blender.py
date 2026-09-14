"""Run with Blender --background --factory-startup --python this_file."""
import importlib.util
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smart_decimate", ROOT / "operators/smart_decimate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
bpy.utils.register_class(module.OBJECT_OT_polygroups_smart_decimate)

bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
source = bpy.context.object
source.name = "Retopo_04_Highpoly_Generated.002"
collection = bpy.data.collections.new("Generated.002")
bpy.context.scene.collection.children.link(collection)
for existing in list(source.users_collection):
    existing.objects.unlink(source)
collection.objects.link(source)
for edge in source.data.edges:
    edge.use_seam = all(abs(source.data.vertices[i].co.y) < 1e-5 for i in edge.vertices)
original_vertices = len(source.data.vertices)

assert bpy.ops.object.polygroups_smart_decimate(ratio=.4) == {"FINISHED"}
seams, body = source.modifiers
assert seams.name == "Seams Decimate" and abs(seams.ratio - .9) < 1e-6
assert not seams.invert_vertex_group and body.invert_vertex_group
assert seams.vertex_group == body.vertex_group
assert bpy.ops.object.polygroups_smart_decimate(seams_ratio=.8) == {"FINISHED"}
assert len(source.modifiers) == 2
assert abs(seams.ratio - .8) < 1e-6

assert bpy.ops.object.polygroups_smart_decimate(duplicate_and_apply=True) == {"FINISHED"}
duplicate = bpy.context.object
assert duplicate.name == "Retopo_04_Highpoly_Generated_SmartDecimated.002", duplicate.name
assert duplicate.users_collection == source.users_collection
assert duplicate.data != source.data and len(duplicate.modifiers) == 0
assert len(duplicate.data.vertices) < original_vertices
assert len(source.data.vertices) == original_vertices and len(source.modifiers) == 2
assert module._decimated_name("Mesh") == "Mesh_SmartDecimated"
assert module._decimated_name("Mesh.001.part") == "Mesh.001.part_SmartDecimated"
print("Smart Decimate integration checks passed")
