"""Run with Blender --background --factory-startup --python-exit-code 1 --python FILE."""
import sys
from pathlib import Path
import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from polygroups_generator.operators.split_narrow_islands import (
    plan_cuts, separate_uv, MESH_OT_polygroups_split_narrow_islands,
    IMAGE_PT_polygroups_narrow_islands,
)
from polygroups_generator.core.narrow_regions import components, filter_small_parts


def grid(cells, uv=True):
    bm = bmesh.new()
    vertices = {}
    for x, y in sorted(cells):
        corners = [(x, y), (x+1, y), (x+1, y+1), (x, y+1)]
        for corner in corners:
            if corner not in vertices:
                vertices[corner] = bm.verts.new((*corner, 0))
        bm.faces.new([vertices[corner] for corner in corners])
    if uv:
        layer = bm.loops.layers.uv.new('UVMap')
        for face in bm.faces:
            for loop in face.loops:
                loop[layer].uv = loop.vert.co.xy
    return bm


body = {(x, y) for x in range(20) for y in range(20)}
for width in range(1, 6):
    tail = {(x, y) for x in range(20, 40) for y in range(8, 8+width)}
    for bridge in (False, True):
        cells = body | tail
        if bridge:
            cells |= {(x, y) for x in range(40, 60) for y in range(20)}
        bm = grid(cells)
        cuts, regions, graph, edges = plan_cuts(bm, width=width)
        assert len(regions) == 1, (width, bridge, len(regions))
        assert cuts, (width, bridge)
        for index in cuts:
            bm.edges[index].seam = True
        moved = separate_uv(bm, graph, edges, cuts)
        assert moved == (2 if bridge else 1), (width, bridge, moved)
        # Both graph islands and actual UV coordinate discontinuities separate.
        for edge in bm.edges:
            edge.seam = False
        _, _, after, _ = plan_cuts(bm, width=width)
        assert len(components(after, after)) == moved + 1
        assert len(bm.faces) == len(cells)
        bm.free()

for cells in (body, {(x, y) for x in range(40) for y in range(3)}):
    bm = grid(cells)
    assert not plan_cuts(bm)[0], 'Plain rectangle or isolated ribbon must stay intact'
bm.free()

# Small appendages may pass face-count and width tests but still make UV scraps.
for tail_length in (12, 24):
    large_body = {(x, y) for x in range(30) for y in range(30)}
    bm = grid(large_body | {(x, 14) for x in range(30, 30 + tail_length)})
    legacy = plan_cuts(bm, width=1, max_width_percent=0, min_island_area_percent=0)[0]
    assert legacy
    filtered = plan_cuts(bm, width=1, max_width_percent=0, min_island_area_percent=2)[0]
    assert bool(filtered) == (tail_length == 24), tail_length
    assert not plan_cuts(bm, width=1, max_width_percent=0, min_island_area_percent=3)[0]
    bm.free()

# UV-area percentage follows UV space rather than physical mesh area.
bm = grid(body | {(x, y) for x in range(20, 32) for y in range(8, 13)})
layer = bm.loops.layers.uv.active
for face in bm.faces:
    for loop in face.loops:
        if loop.vert.co.x > 20:
            loop[layer].uv.x = 20 + (loop.vert.co.x - 20) * 0.1
assert not plan_cuts(bm, source='UV', width=5, max_width_percent=0,
                     min_island_area_percent=2)[0]
assert plan_cuts(bm, source='MESH', width=5, max_width_percent=0,
                 min_island_area_percent=2)[0]
bm.free()

# Two individually safe cuts can trap a tiny section between them.
chain = {0: {1}, 1: {0, 2}, 2: {1}}
candidates = [({1, 2}, {(1, 0)}), ({2}, {(2, 1)})]
accepted = filter_small_parts(chain, candidates, {0: 49, 1: 1, 2: 50}, 2)
assert len(accepted) == 1
assert filter_small_parts(chain, candidates, {0: 49, 1: 1, 2: 50}, 0) == candidates

# The same 12 face rows can mean very different real UV widths. A coarse,
# physically broad strip is rejected; a densely packed narrow strip survives.
for dense in (False, True):
    cells = body | {(x, y) for x in range(20, 60) for y in range(4, 16)}
    bm = grid(cells)
    if dense:
        for vertex in bm.verts:
            if vertex.co.x >= 20:
                vertex.co.y = 10 + (vertex.co.y - 10) * 0.15
        layer = bm.loops.layers.uv.active
        for face in bm.faces:
            for loop in face.loops:
                loop[layer].uv = loop.vert.co.xy
    for source in ('UV', 'MESH'):
        assert plan_cuts(bm, source=source, width=12, max_width_percent=0)[0]
        filtered, regions, _, _ = plan_cuts(bm, source=source, width=12, max_width_percent=35)
        assert bool(filtered) == dense, (source, dense, len(regions))
    bm.free()

# Morphological opening alone crops a square's corners at high face-row
# settings. The geometric elongation guard must leave them connected.
bm = grid(body)
for source in ('UV', 'MESH'):
    legacy_cuts, _, _, _ = plan_cuts(bm, source=source, width=12, max_width_percent=0)
    assert legacy_cuts, 'Fixture must exhibit the original corner false positive'
    assert not plan_cuts(bm, source=source, width=12, max_width_percent=35)[0]
bm.free()

bm = grid(body | {(x, y) for x in range(20, 40) for y in range(8, 11)}, uv=False)
assert plan_cuts(bm, source='MESH')[0]
try:
    plan_cuts(bm)
    raise AssertionError('Missing UV must fail')
except ValueError:
    pass
assert not plan_cuts(bm, source='MESH', selected_only=True)[0]
bm.faces[0].select = True
assert plan_cuts(bm, source='MESH', selected_only=True)[0]
bm.free()

# UV-only selection and seam boundaries must be honored without new UV cuts.
bm = grid(body | {(x, y) for x in range(20, 40) for y in range(8, 11)})
for face in bm.faces:
    face.select = True
assert not plan_cuts(bm, selected_only=True, uv_selection=True)[0]
loop = next(iter(bm.faces)).loops[0]
if hasattr(loop, 'uv_select_vert_set'):
    loop.uv_select_vert_set(True)
else:
    loop[bm.loops.layers.uv.active].select = True
cuts, _, _, _ = plan_cuts(bm, selected_only=True, uv_selection=True)
assert cuts
for index in cuts:
    bm.edges[index].seam = True
assert not plan_cuts(bm)[0], 'Repeating seam analysis should not subdivide the detached ribbon'
bm.free()

for cls in (MESH_OT_polygroups_split_narrow_islands,
            IMAGE_PT_polygroups_narrow_islands):
    bpy.utils.register_class(cls)
obj = bpy.context.active_object
bm = grid(body | {(x, y) for x in range(20, 40) for y in range(8, 11)})
bm.to_mesh(obj.data)
bm.free()
original_uv = [tuple(loop.uv) for loop in obj.data.uv_layers.active.data]
assert bpy.ops.mesh.polygroups_split_narrow_islands(action='PREVIEW') == {'FINISHED'}
assert obj.mode == 'EDIT'
bm = bmesh.from_edit_mesh(obj.data)
assert any(edge.select for edge in bm.edges)
assert not any(edge.seam for edge in bm.edges)
layer = bm.loops.layers.uv.active
assert [tuple(loop[layer].uv) for face in bm.faces for loop in face.loops] == original_uv
assert bpy.ops.mesh.polygroups_split_narrow_islands(action='SPLIT', smart_relax=False) == {'FINISHED'}
assert any(edge.seam for edge in bm.edges)
bpy.ops.object.mode_set(mode='OBJECT')
assert len(obj.data.polygons) == 460

# Mesh mode must mark seams without requiring UV or changing geometry.
bm = grid(body | {(x, y) for x in range(20, 40) for y in range(8, 11)}, uv=False)
fresh_mesh = bpy.data.meshes.new('NoUV')
bm.to_mesh(fresh_mesh)
bm.free()
obj.data = fresh_mesh
assert bpy.ops.mesh.polygroups_split_narrow_islands(source='MESH', action='SEAMS', smart_relax=False) == {'FINISHED'}
assert any(edge.use_seam for edge in obj.data.edges)
assert not obj.data.uv_layers
assert len(obj.data.polygons) == 460
print('NARROW ISLAND TESTS PASSED')

# Selected-island scope survives Preview's switch from face to edge selection.
bpy.ops.object.mode_set(mode='EDIT')
live = bmesh.from_edit_mesh(obj.data)
for edge in live.edges:
    edge.seam = False
for face in live.faces:
    face.select_set(True)
assert bpy.ops.mesh.polygroups_split_narrow_islands(source='MESH', action='PREVIEW', selected_only=True) == {'FINISHED'}
assert not any(face.select for face in live.faces)
assert bpy.ops.mesh.polygroups_split_narrow_islands(source='MESH', action='SEAMS', selected_only=True, smart_relax=False) == {'FINISHED'}
assert any(edge.seam for edge in live.edges)
print('SELECTED PREVIEW/APPLY PASSED')

# An area-invalid reroute on one appendage must not discard a second valid cut.
from polygroups_generator.operators import split_narrow_islands as narrow_module
if obj.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')
two_tails = body | {(x, y) for x in range(-14, 0) for y in range(8, 11)}
two_tails |= {(x, y) for x in range(20, 40) for y in range(8, 11)}
bm = grid(two_tails, uv=False)
mesh = bpy.data.meshes.new('Two narrow tails')
bm.to_mesh(mesh)
obj.data = mesh
cuts, regions, _, pairs = plan_cuts(bm, source='MESH', width=3)
assert len(regions) == 2
left = min(regions, key=lambda region: min(bm.faces[index].calc_center_median().x
                                           for index in region[0]))
left_cuts = {index for pair in left[1] for index in pairs[frozenset(pair)]}
bm.free()
original_refine = narrow_module.refine_cuts
def reject_left(mesh, candidate_cuts, graph, *args):
    if candidate_cuts & left_cuts:
        raise narrow_module.UndersizedRerouteError(set(graph))
    return original_refine(mesh, candidate_cuts, graph, *args)
narrow_module.refine_cuts = reject_left
try:
    assert bpy.ops.mesh.polygroups_split_narrow_islands(
        source='MESH', action='SEAMS', width=3, create_edges=True, smart_relax=False,
    ) == {'FINISHED'}
finally:
    narrow_module.refine_cuts = original_refine
seam_centers = [sum(mesh.vertices[index].co.x for index in edge.vertices) / 2
                for edge in obj.data.edges if edge.use_seam]
assert seam_centers and all(x > 15 for x in seam_centers), seam_centers
print('OTHER VALID CUTS PRESERVED')
