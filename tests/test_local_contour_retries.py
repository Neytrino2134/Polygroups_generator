"""Blender background regression for bounded automatic contour retries."""
import sys
from pathlib import Path
from unittest.mock import patch
import bpy
import addon_utils
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core import local_contour as c

corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
vertices = [(x, y, z) for z in (-1, 0, 1) for x, y in corners]
faces = [(4*j+i, 4*j+(i+1)%4, 4*(j+1)+(i+1)%4, 4*(j+1)+i)
         for j in range(2) for i in range(4)]
faces += [(3, 2, 1, 0), (8, 9, 10, 11)]
# A tiny non-manifold fin branches the exact z=0 section, but not nearby ones.
vertices += [(1.2, -1, 0), (1.2, -1, .0001)]
faces.append((5, 12, 13))
mesh = bpy.data.meshes.new("Ambiguous exact section")
mesh.from_pydata(vertices, [], faces)
obj = bpy.data.objects.new("Ambiguous exact section", mesh)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
seed, normal = Vector((0, -1, 0)), Vector((0, 0, 1))
before = ([tuple(v.co) for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons])
try:
    c.fitted_section(obj, dg, seed, normal, seed, 32, .01)
except c.SectionNotFound:
    pass
else:
    raise AssertionError("Regression mesh did not reproduce ambiguous section")
with patch.object(c, "fitted_section", wraps=c.fitted_section) as fitting:
    points, fill = c.fitted_section_with_retries(obj, dg, seed, normal, 32, .01, 2)
    assert 1 < fitting.call_count <= 10
assert len(points) == 32 and len(fill) == 1
assert max(p.z for p in points) - min(p.z for p in points) < 1e-6
assert 0 < abs(points[0].z) <= .01
assert before == ([tuple(v.co) for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons])

# A valid exact stroke remains exact, with no extra searches.
seed = Vector((0, -1, .5))
with patch.object(c, "fitted_section", wraps=c.fitted_section) as fitting:
    points, _ = c.fitted_section_with_retries(obj, dg, seed, normal, 32, .01, 2)
    assert fitting.call_count == 1
assert all(abs(p.z - .5) < 1e-6 for p in points)

# A genuinely open surface is not filled or accepted after retry exhaustion.
open_mesh = bpy.data.meshes.new("Open surface")
open_mesh.from_pydata([(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)], [], [(0, 1, 2, 3)])
open_obj = bpy.data.objects.new("Open surface", open_mesh)
bpy.context.collection.objects.link(open_obj)
bpy.context.view_layer.update()
with patch.object(c, "fitted_section", wraps=c.fitted_section) as fitting:
    try:
        c.fitted_section_with_retries(open_obj, bpy.context.evaluated_depsgraph_get(),
                                     Vector((0, -1, 0)), normal, 32, .01, 2)
    except c.SectionNotFound as exc:
        assert "10 nearby attempts" in str(exc)
    else:
        raise AssertionError("Open surface accepted as closed contour")
    assert fitting.call_count == 10
print("LOCAL_CONTOUR_RETRY_TESTS_PASSED", flush=True)
