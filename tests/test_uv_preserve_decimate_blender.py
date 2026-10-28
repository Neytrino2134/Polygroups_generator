"""Run with Blender --background --factory-startup --python this_file."""
import sys
from pathlib import Path

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import meshopt_simplify  # noqa: E402

assert meshopt_simplify.is_available(), meshopt_simplify.DLL_PATH


def key(co, uv=None):
    point = tuple(round(value, 5) for value in co)
    return point if uv is None else point + (round(uv.x, 5), round(uv.y, 5))


bpy.ops.mesh.primitive_monkey_add()
source = bpy.context.object
source.name = "Retopo_04_Highpoly_Generated.003"
collection = bpy.data.collections.new("Generated.003")
bpy.context.scene.collection.children.link(collection)
for existing in list(source.users_collection):
    existing.objects.unlink(source)
collection.objects.link(source)
subdivision = source.modifiers.new("sub", "SUBSURF")
subdivision.levels = 2
bpy.ops.object.modifier_apply(modifier=subdivision.name)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
bpy.ops.uv.seams_from_islands()
bpy.ops.object.mode_set(mode="OBJECT")
for name in ("A", "B"):
    source.data.materials.append(bpy.data.materials.new(name))
for polygon in source.data.polygons:
    polygon.material_index = int(polygon.center.x > 0)
group = source.vertex_groups.new(name="Weights")
group.add([vertex.index for vertex in source.data.vertices if vertex.co.z > 0], 0.75, "REPLACE")

mesh = source.data
uv = mesh.uv_layers.active.data
original_corners = {key(mesh.vertices[loop.vertex_index].co, uv[loop.index].uv) for loop in mesh.loops}
seam_points = {key(mesh.vertices[index].co) for edge in mesh.edges if edge.use_seam for index in edge.vertices}
source_polygons = len(mesh.polygons)
source_tris = meshopt_simplify.triangle_count(mesh)
target = source_tris // 4

assert bpy.ops.object.polygroups_uv_preserve_decimate(
    triangle_limit=target, seam_mode="LOCK", join_triangles=False) == {"FINISHED"}
lod = bpy.context.object
assert lod is not source and lod.name == "Retopo_04_Highpoly_Generated_UVDecimated.003", lod.name
assert lod.get("polygroups_smart_decimated") and lod.users_collection == source.users_collection
assert len(source.data.polygons) == source_polygons, "source must stay untouched"
lod_mesh = lod.data
assert meshopt_simplify.triangle_count(lod_mesh) <= target, meshopt_simplify.triangle_count(lod_mesh)
assert all(len(polygon.vertices) == 3 for polygon in lod_mesh.polygons)

# Every corner keeps an original (position, UV) pair exactly: textures cannot slide.
lod_uv = lod_mesh.uv_layers.active.data
for loop in lod_mesh.loops:
    assert key(lod_mesh.vertices[loop.vertex_index].co, lod_uv[loop.index].uv) in original_corners
# Locked seams: no island border vertex disappears.
lod_points = {key(vertex.co) for vertex in lod_mesh.vertices}
assert seam_points <= lod_points, len(seam_points - lod_points)
assert any(edge.use_seam for edge in lod_mesh.edges)
assert {polygon.material_index for polygon in lod_mesh.polygons} == {0, 1}
assert len(lod_mesh.materials) == 2
weights = [g.weight for vertex in lod_mesh.vertices for g in vertex.groups if vertex.co.z > 0]
assert weights and all(abs(weight - 0.75) < 1e-6 for weight in weights)

# Quads: joining never moves vertices and keeps the triangle budget.
bpy.context.view_layer.objects.active = source
source.select_set(True)
assert bpy.ops.object.polygroups_uv_preserve_decimate(triangle_limit=target, join_triangles=True) == {"FINISHED"}
quads = bpy.context.object
assert any(len(polygon.vertices) == 4 for polygon in quads.data.polygons)
assert len(quads.data.polygons) < meshopt_simplify.triangle_count(quads.data) <= target

# Prefer/Free seams reach a budget that locked seams cannot.
aggressive = max(1, source_tris // 40)
counts = {}
for mode in ("LOCK", "FREE"):
    bpy.context.view_layer.objects.active = source
    assert bpy.ops.object.polygroups_uv_preserve_decimate(
        triangle_limit=aggressive, seam_mode=mode, join_triangles=False) == {"FINISHED"}
    counts[mode] = meshopt_simplify.triangle_count(bpy.context.object.data)
assert counts["FREE"] < counts["LOCK"], counts

# Batch over Generated.N uses section settings.
settings = bpy.context.scene.polygroups_mesh_finalization_settings
settings.uv_decimate_ratio = 0.3
settings.uv_decimate_hide_source = True
before = {obj.name for obj in bpy.data.objects}
assert bpy.ops.object.polygroups_uv_preserve_decimate_all_generated() == {"FINISHED"}
created = [bpy.data.objects[name] for name in {obj.name for obj in bpy.data.objects} - before]
assert len(created) == 1 and source.hide_viewport

assert bpy.ops.object.polygroups_delete_all_decimated() == {"FINISHED"}
assert not [obj for obj in bpy.data.objects if obj.get("polygroups_smart_decimated")]
print("UV Preserve Decimate checks passed")
