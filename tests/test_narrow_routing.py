"""Blender integration: shorter narrow cuts, diagonals, UV data and preview."""
import sys
from pathlib import Path
import bmesh
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
from polygroups_generator.operators import split_narrow_islands as module


def fixture(triangles=False, warp=False):
    bm = bmesh.new()
    vertices = {(x, y): bm.verts.new((x, y, .04*x*y if warp else 0))
                for x in range(-4, 5) for y in range(-4, 5)}
    uv = bm.loops.layers.uv.new('UVMap')
    secondary = bm.loops.layers.uv.new('DetailUV')
    tag = bm.faces.layers.int.new('test_region')
    for x in range(-4, 4):
        for y in range(-4, 4):
            face = bm.faces.new([vertices[x, y], vertices[x+1, y],
                                 vertices[x+1, y+1], vertices[x, y+1]])
            face.material_index = (x+4)*8+y+4
            face[tag] = face.material_index+100
            face.select = x < 0
            for loop in face.loops:
                loop[uv].uv = loop.vert.co.xy
                loop[secondary].uv = (loop.vert.co.x+face.material_index*10, loop.vert.co.y)
                loop[secondary].pin_uv = True
    path = [(-4, -2), (-3, -2), (-2, -2), (-2, -1), (-1, -1),
            (-1, 0), (0, 0), (0, 1), (1, 1), (1, 2), (2, 2), (3, 2), (4, 2)]
    cut_edges = {bm.edges.get((vertices[a], vertices[b])) for a, b in zip(path, path[1:])}
    for edge in bm.edges:
        edge.seam = edge.is_boundary
    if triangles:
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='ALTERNATE')
    for face in bm.faces:
        face.select = face.material_index < 32
    bm.normal_update()
    graph, _, pairs = module.island_graph(bm)
    return bm, {edge.index for edge in cut_edges}, graph


def length(bm, cuts):
    return sum(bm.edges[index].calc_length() for index in cuts)


for triangles in (False, True):
    for warp in (False, True):
        for source in ('UV', 'MESH'):
            bm, cuts, graph = fixture(triangles, warp)
            original_count = len(bm.verts), len(bm.edges), len(bm.faces)
            original_selection = [face.select for face in bm.faces]
            original_seams = [edge.seam for edge in bm.edges]
            original_positions = [vert.co.copy() for vert in bm.verts]
            work, refined, _, _, rerouted, created = module.refine_cuts(bm, cuts, graph, source, True)
            print('DIAGONAL', triangles, warp, source, rerouted, created, length(bm, cuts), length(work, refined))
            assert rerouted and created
            assert length(work, refined) < length(bm, cuts)-.2
            assert len(work.faces) > len(bm.faces)
            assert all(vert.co == co for vert, co in zip(work.verts, original_positions))
            assert original_count == (len(bm.verts), len(bm.edges), len(bm.faces))
            assert original_selection == [face.select for face in bm.faces]
            assert original_seams == [edge.seam for edge in bm.edges]
            uv = work.loops.layers.uv['UVMap']
            secondary = work.loops.layers.uv['DetailUV']
            tag = work.faces.layers.int['test_region']
            assert all(len(edge.link_faces) in (1, 2) for edge in work.edges)
            assert all(face.calc_area() > 1e-8 for face in work.faces)
            for face in work.faces:
                assert face[tag] == face.material_index+100
                assert face.select == (face.material_index < 32)
                for loop in face.loops:
                    assert (loop[uv].uv-loop.vert.co.xy).length < 1e-5
                    assert abs(loop[secondary].uv.x-loop.vert.co.x-face.material_index*10) < 1e-4
                    assert abs(loop[secondary].uv.y-loop.vert.co.y) < 1e-5
            work.free()
            bm.free()

# Existing-edge mode removes a real detour, preserving topology.
bm, _, graph = fixture()
vertices = {(int(v.co.x), int(v.co.y)): v for v in bm.verts}
path = [(-4, 0), (-3, 0), (-2, 0), (-2, 1), (-1, 1), (0, 1),
        (0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
cuts = {bm.edges.get((vertices[a], vertices[b])).index for a, b in zip(path, path[1:])}
work, refined, _, _, rerouted, created = module.refine_cuts(bm, cuts, graph)
assert rerouted and not created
assert len(work.faces) == len(bm.faces)
assert length(work, refined) <= 8.001
work.free()
bm.free()

# Two separate islands must both reroute even when the first creates faces.
bm, cuts, _ = fixture()
marks = bm.edges.layers.int.new('raw_cut')
for index in cuts:
    bm.edges[index][marks] = 1
duplicate = bmesh.ops.duplicate(bm, geom=list(bm.verts)+list(bm.edges)+list(bm.faces))
for item in duplicate['geom']:
    if isinstance(item, bmesh.types.BMVert):
        item.co.x += 20
graph, _, _ = module.island_graph(bm)
cuts = {edge.index for edge in bm.edges if edge[marks]}
work, refined, _, _, routed, created = module.refine_cuts(bm, cuts, graph, create_edges=True)
assert routed == 2 and created > 0
assert length(work, refined) < length(bm, cuts)
work.free()
bm.free()

# A UV-only island boundary remains a barrier and is not converted to a seam.
bm, cuts, _ = fixture()
layer = bm.loops.layers.uv.active
for face in bm.faces:
    if face.calc_center_median().x >= 0:
        for loop in face.loops:
            loop[layer].uv.x += 20
graph, _, pairs = module.island_graph(bm)
internal = set().union(*pairs.values())
cuts &= internal
old_seams = [edge.seam for edge in bm.edges]
work, refined, _, _, routed, created = module.refine_cuts(bm, cuts, graph, create_edges=True)
assert all(edge.seam == old for edge, old in zip(work.edges, old_seams))
work.free()
bm.free()

# Exercise preview/apply on the same staircase without relying on detection.
bpy.utils.register_class(module.MESH_OT_polygroups_split_narrow_islands)
original_plan = module.plan_cuts
try:
    for edit_mode in (False, True):
        bm, cuts, graph = fixture()
        obj = bpy.context.active_object
        if obj.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bm.to_mesh(obj.data)
        bm.free()
        count = len(obj.data.polygons)
        uv_before = [tuple(item.uv) for item in obj.data.uv_layers['DetailUV'].data]
        def fixed_plan(mesh, *args):
            adjacency, _, pairs = module.island_graph(mesh)
            return cuts, [None], adjacency, pairs
        module.plan_cuts = fixed_plan
        if edit_mode:
            bpy.ops.object.mode_set(mode='EDIT')
        assert bpy.ops.mesh.polygroups_split_narrow_islands(action='PREVIEW', create_edges=True) == {'FINISHED'}
        live = bmesh.from_edit_mesh(obj.data)
        assert len(live.faces) == count
        secondary = live.loops.layers.uv['DetailUV']
        assert [tuple(loop[secondary].uv) for f in live.faces for loop in f.loops] == uv_before
        assert bpy.ops.mesh.polygroups_split_narrow_islands(action='SPLIT', create_edges=True) == {'FINISHED'}
        live = bmesh.from_edit_mesh(obj.data)
        assert len(live.faces) > count
        adjacency, _, _ = module.island_graph(live)
        assert len(module.components(adjacency, adjacency)) == 2
finally:
    module.plan_cuts = original_plan
print('NARROW ROUTING PASSED')
