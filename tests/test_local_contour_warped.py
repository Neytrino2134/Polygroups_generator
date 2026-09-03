"""Regression for ray hits on non-planar quads disagreeing with section chords.

Run with Blender --background --factory-startup --python-exit-code 1 --python this_file.
"""
import sys
from pathlib import Path
from math import sin, cos, tau

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.local_contour import (
    section_loops, _distance_to_segment, _segments, fitted_section,
)

vertices = []
segments = 20
for level in range(3):
    for index in range(segments):
        angle = tau * index / segments + .25 * level
        radius = 1 + .15 * cos(angle * 3 + level)
        vertices.append((radius * cos(angle), radius * sin(angle), level - 1))
faces = []
for level in range(2):
    for index in range(segments):
        next_index = (index + 1) % segments
        faces.append((level * segments + index, level * segments + next_index,
                      (level + 1) * segments + next_index, (level + 1) * segments + index))
faces += [tuple(reversed(range(segments))), tuple(range(2 * segments, 3 * segments))]
mesh = bpy.data.meshes.new('Warped quads')
mesh.from_pydata(vertices, [], faces)
target = bpy.data.objects.new('Warped quads', mesh)
bpy.context.collection.objects.link(target)
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
original = [tuple(p.vertices) for p in mesh.polygons]
for x, z in ((.23, .35), (.15, -.42), (.51, .7)):
    hit, seed, _, _ = target.evaluated_get(depsgraph).ray_cast(
        Vector((x, -4, z)), Vector((0, 1, 0)),
    )
    assert hit
    normal = Vector((.17, .05, 1)).normalized()
    loops, epsilon = section_loops(target, depsgraph, seed, normal)
    distance = min(_distance_to_segment(seed, a, b)
                   for loop in loops for a, b in _segments(loop))
    assert distance <= epsilon * 100, (distance, epsilon)
    cutter_vertices, cutter_faces = fitted_section(
        target, depsgraph, seed, normal, seed, 64, .002,
    )
    assert len(cutter_vertices) == 64 and len(cutter_faces) == 1
    assert all(abs((point - seed).dot(normal)) < 1e-5 for point in cutter_vertices)
assert original == [tuple(p.vertices) for p in mesh.polygons], 'source polygons were changed'
print('Warped section regression passed', flush=True)
