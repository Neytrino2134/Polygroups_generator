"""Blender background: grid counts, finite cuts and source preservation."""
import sys
from pathlib import Path
from collections import Counter
import addon_utils
import bpy
import bmesh
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.context.preferences.addons[ROOT.name].preferences.play_sound_after_operations = False
from polygroups_generator.operators.cutter_grid import grid_planes, create_grid
from polygroups_generator.operators import object_seam_cutter as c

lower, upper = Vector((-2, -2, -2)), Vector((2, 2, 2))
planes = list(grid_planes(lower, upper, (True, False, True), (2, 7, 1)))
assert Counter(axis for axis, _, _ in planes) == {0: 2, 2: 1}
for axis, index, corners in planes:
    assert len(corners) == 4 and len({round(p[axis], 6) for p in corners}) == 1
    assert all(all(lower[i] <= p[i] <= upper[i] for i in range(3)) for p in corners)
    assert lower[axis] < corners[0][axis] < upper[axis]

settings = bpy.context.scene.polygroups_object_seam_cutter_settings
settings.cutter_grid_axes = (True, True, True)
settings.cutter_grid_counts = (2, 1, 1)
settings.cutter_auto_fix_mesh = False
for method in ("BOOLEAN", "KNIFE"):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("Two separate boxes")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    bmesh.ops.create_cube(bm, size=2, matrix=Matrix.Translation((0, 6, 0)))
    bm.to_mesh(mesh)
    bm.free()
    target = bpy.data.objects.new("Two separate boxes", mesh)
    bpy.context.collection.objects.link(target)
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    before = (len(mesh.vertices), len(mesh.polygons))
    cutters = create_grid(lower, upper, settings)
    assert len(cutters) == 4
    assert before == (len(mesh.vertices), len(mesh.polygons))
    assert len({obj.users_collection[0].name for obj in cutters}) == 1
    for obj in cutters:
        assert obj[c.CUTTER_TYPE_PROP] == "GRID_PLANE"
        assert len(obj.data.polygons) == 1 and len(obj.data.vertices) == 4
        obj.select_set(True)
    settings.cutter_apply_method = method
    assert bpy.ops.object.polygroups_apply_cutter_seams() == {"FINISHED"}
    bm = bmesh.new()
    bm.from_mesh(mesh)
    seams = [e for e in bm.edges if e.seam]
    assert seams and all(v.co.y < 2 for e in seams for v in e.verts), "Cut escaped the drawn volume"
    assert all(e.is_manifold for e in bm.edges)
    assert sum(v.co.y > 4 for v in bm.verts) == 8, "Unrelated box was split"
    bm.free()
    print("PASS finite grid apply", method, flush=True)

settings.cutter_grid_axes = (False, False, False)
before = (len(bpy.data.objects), len(bpy.data.collections))
try:
    create_grid(lower, upper, settings)
except ValueError:
    pass
else:
    raise AssertionError("Empty grid accepted")
assert before == (len(bpy.data.objects), len(bpy.data.collections))
# Auto generation reads evaluated bounds, including rotation, scale and modifiers.
from polygroups_generator.operators.cutter_grid import evaluated_bounds
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_cube_add()
target = bpy.context.object
target.location = (3, -2, 1)
target.rotation_euler.z = .4
target.scale = (1.5, .7, 2)
array = target.modifiers.new("Bounds extension", "ARRAY")
array.count = 2
bpy.context.view_layer.update()
settings.cutter_grid_axes = (True, True, True)
settings.cutter_grid_counts = (2, 3, 1)
lower, upper = evaluated_bounds(bpy.context, target)
before = (len(target.data.vertices), len(target.data.polygons))
assert bpy.ops.object.polygroups_generate_cutter_grid() == {"FINISHED"}
cutters = [obj for obj in bpy.context.selected_objects if obj.get(c.CUTTER_TYPE_PROP) == "GRID_PLANE"]
assert len(cutters) == 6 and bpy.context.active_object == target
assert before == (len(target.data.vertices), len(target.data.polygons))
for cutter in cutters:
    assert all(all(lower[i] - 1e-5 <= (cutter.matrix_world @ v.co)[i] <= upper[i] + 1e-5
                   for i in range(3)) for v in cutter.data.vertices)
assert upper.x - lower.x > 4, "Modifier was ignored in automatic bounds"
print("CUTTER_GRID_TESTS_PASSED", flush=True)
