"""Blender background regression: duplicate triangles and disconnected face vertices."""
import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.local_contour import fitted_section, section_loops

vertices = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
triangles = [tri for a, b, c, d in quads for tri in ((a, b, c), (a, c, d))]

for split in (False, True):
    coords = [] if split else vertices
    faces = []
    for triangle in triangles:
        if split:
            start = len(coords)
            coords.extend(vertices[i] for i in triangle)
            face = tuple(range(start, start + 3))
        else:
            face = triangle
        faces.extend((face, tuple(reversed(face))))
    mesh = bpy.data.meshes.new("Duplicate triangles")
    mesh.from_pydata(coords, [], faces)
    obj = bpy.data.objects.new("Duplicate triangles", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    before = ([tuple(v.co) for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    seed = Vector((0, -1, 0))
    for normal in (Vector((0, 0, 1)), Vector((.2, 0, 1)).normalized()):
        loops, _ = section_loops(obj, depsgraph, seed, normal)
        assert len(loops) == 1, (split, len(loops))
        for offset in (0, .01):
            points, fill = fitted_section(obj, depsgraph, seed, normal, seed, 32, offset)
            assert len(points) == 32 and len(fill) == 1
            assert all(abs((p - seed).dot(normal)) < 1e-5 for p in points)
            if offset == 0:
                assert all(abs(max(abs(p.x), abs(p.y)) - 1) < 1e-5 for p in points)
            else:
                assert all(max(abs(p.x), abs(p.y)) > 1 for p in points)
    # An exact face-plane intersection must not include cap triangulation diagonals.
    loops, _ = section_loops(obj, depsgraph, Vector((0, 0, 1)), Vector((0, 0, 1)))
    assert len(loops) == 1
    assert before == ([tuple(v.co) for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons])
    print("PASS duplicate triangles, split vertices:", split, flush=True)

# Evaluate modifiers rather than ignoring the displayed surface.
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.object
modifier = obj.modifiers.new("Displayed shape", "SUBSURF")
modifier.levels = 2
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
hit, seed, _, _ = obj.evaluated_get(depsgraph).ray_cast(Vector((0, -4, 0)), Vector((0, 1, 0)))
assert hit
points, fill = fitted_section(obj, depsgraph, seed, Vector((0, 0, 1)), seed, 32, 0)
assert max(abs(p.x) for p in points) < .9
assert len(obj.data.vertices) == 8 and len(obj.data.polygons) == 6
print("Local contour duplicate and evaluated surface tests passed", flush=True)
