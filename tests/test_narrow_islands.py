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
from polygroups_generator.core.narrow_regions import components


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
assert bpy.ops.mesh.polygroups_split_narrow_islands(action='SPLIT') == {'FINISHED'}
assert any(edge.seam for edge in bm.edges)
bpy.ops.object.mode_set(mode='OBJECT')
assert len(obj.data.polygons) == 460

# Mesh mode must mark seams without requiring UV or changing geometry.
bm = grid(body | {(x, y) for x in range(20, 40) for y in range(8, 11)}, uv=False)
fresh_mesh = bpy.data.meshes.new('NoUV')
bm.to_mesh(fresh_mesh)
bm.free()
obj.data = fresh_mesh
assert bpy.ops.mesh.polygroups_split_narrow_islands(source='MESH', action='SEAMS') == {'FINISHED'}
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
assert bpy.ops.mesh.polygroups_split_narrow_islands(source='MESH', action='SEAMS', selected_only=True) == {'FINISHED'}
assert any(edge.seam for edge in live.edges)
print('SELECTED PREVIEW/APPLY PASSED')
