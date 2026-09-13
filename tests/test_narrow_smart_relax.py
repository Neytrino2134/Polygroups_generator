"""Blender integration test for optional relaxation of generated narrow-island seams."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators import split_narrow_islands as narrow_module


def make_mesh():
    bm = bmesh.new()
    vertices = {}
    cells = {(x, y) for x in range(20) for y in range(20)}
    cells |= {(x, y) for x in range(20, 40) for y in range(8, 11)}
    for x, y in sorted(cells):
        corners = ((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1))
        for corner in corners:
            if corner not in vertices:
                vertices[corner] = bm.verts.new((*corner, 0))
        bm.faces.new([vertices[corner] for corner in corners])
    mesh = bpy.data.meshes.new('Narrow Smart Relax')
    bm.to_mesh(mesh)
    bm.free()
    return mesh


obj = bpy.data.objects.new('Narrow Smart Relax', make_mesh())
bpy.context.collection.objects.link(obj)
bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

for edit in (False, True):
    for create_edges in (False, True):
        if obj.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        obj.data = make_mesh()
        if edit:
            bpy.ops.object.mode_set(mode='EDIT')
        before = [vertex.co.copy() for vertex in obj.data.vertices]
        assert bpy.ops.mesh.polygroups_split_narrow_islands(
            source='MESH', action='PREVIEW', smart_relax=True,
            create_edges=create_edges,
        ) == {'FINISHED'}
        assert all(vertex.co == old for vertex, old in zip(obj.data.vertices, before))
        assert bpy.ops.mesh.polygroups_split_narrow_islands(
            source='MESH', action='SEAMS', smart_relax=True,
            create_edges=create_edges,
        ) == {'FINISHED'}
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            assert any(edge.seam for edge in bm.edges)
        else:
            assert any(edge.use_seam for edge in obj.data.edges)

if obj.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

# A diagonal route must still identify its new edges after topology is rebuilt.
bm = bmesh.new()
vertices = {(x, y): bm.verts.new((x, y, 0))
            for x in range(-4, 5) for y in range(-4, 5)}
uv = bm.loops.layers.uv.new('UVMap')
for x in range(-4, 4):
    for y in range(-4, 4):
        face = bm.faces.new((vertices[x, y], vertices[x + 1, y],
                             vertices[x + 1, y + 1], vertices[x, y + 1]))
        for loop in face.loops:
            loop[uv].uv = loop.vert.co.xy
path = [(-4, -2), (-3, -2), (-2, -2), (-2, -1), (-1, -1),
        (-1, 0), (0, 0), (0, 1), (1, 1), (1, 2), (2, 2), (3, 2), (4, 2)]
bm.edges.index_update()
cuts = {bm.edges.get((vertices[a], vertices[b])).index
        for a, b in zip(path, path[1:])}
for edge in bm.edges:
    edge.seam = edge.is_boundary
mesh = bpy.data.meshes.new('Diagonal Smart Relax')
bm.to_mesh(mesh)
bm.free()
obj.data = mesh
old_count = len(mesh.polygons)
old_boundary = {tuple(sorted(edge.vertices)) for edge in mesh.edges if edge.use_seam}
old_positions = [vertex.co.copy() for vertex in mesh.vertices]
original_plan = narrow_module.plan_cuts

def fixed_plan(work, *args):
    graph, _, pairs = narrow_module.island_graph(work)
    return cuts, [None], graph, pairs

narrow_module.plan_cuts = fixed_plan
try:
    assert bpy.ops.mesh.polygroups_split_narrow_islands(
        source='UV', action='SEAMS', create_edges=True, smart_relax=True,
    ) == {'FINISHED'}
finally:
    narrow_module.plan_cuts = original_plan
assert len(mesh.polygons) > old_count
assert all(any(tuple(sorted(edge.vertices)) == pair and edge.use_seam
               for edge in mesh.edges) for pair in old_boundary)
assert all(mesh.vertices[index].co == old_positions[index]
           for pair in old_boundary for index in pair)

addon_utils.disable(ROOT.name, default_set=True)
print('NARROW SMART RELAX PASSED', flush=True)
