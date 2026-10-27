"""Run with Blender --background --factory-startup --python-exit-code 1."""
from pathlib import Path
import sys
import bmesh
from mathutils import Vector, Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds, _plan, inspect_triangle_quality


def fixture(scale=1, rotation=0, ordinary=False):
    # Four local coordinates reproduce the non-planar ear, not an asset-sized
    # mesh. A tetrahedral shell closes the patch without any degree-two tips.
    coordinates = [Vector(p) for p in (
        (.0419568606, .0017019160, .9663040042),
        (.0414119363, .0006719106, .9682462215),
        (.0404107012, -.0014217409, .9707894921),
        (.0390468054, -.0033205841, .9733807445))]
    origin = coordinates[0].copy()
    span = (coordinates[2] - origin).length
    transform = Matrix.Rotation(rotation, 3, 'Y')
    coordinates = [transform @ ((p - origin) / span) * scale for p in coordinates]
    a, b, c, tip = coordinates
    if ordinary:
        tip = (a + b + c) / 3
    normal = (b - a).cross(c - a).normalized()
    d = (a + b + c) / 3 - normal * scale
    bm = bmesh.new()
    a, b, c, tip, d = [bm.verts.new(p) for p in (a, b, c, tip, d)]
    triangle = bm.faces.new((a, tip, c))
    quad = bm.faces.new((tip, a, b, c))
    for vertices in ((a, d, b), (b, d, c), (c, d, a)):
        bm.faces.new(vertices)
    for name in ('UVMap', 'ExtraUV'):
        layer = bm.loops.layers.uv.new(name)
        for face in bm.faces:
            for loop in face.loops:
                loop[layer].uv = (loop.vert.co.x / scale, loop.vert.co.z / scale)
        for loop in triangle.loops:
            loop[layer].uv += Vector((4, 4))
    bm.normal_update()
    return bm, tip, triangle, quad


for scale, rotation in ((.001, 0), (1, 0), (1000, 0), (1, 1.3)):
    bm, tip, triangle, quad = fixture(scale, rotation)
    layers = list(bm.loops.layers.uv.values())
    assert _plan({triangle, quad}, layers, scale * 1e-7, True) is not None
    coordinates = {v: v.co.copy() for v in bm.verts if v != tip}
    uv_snapshot = {f: [(l.vert, [l[u].uv.copy() for u in layers]) for l in f.loops]
                   for f in bm.faces if f not in {triangle, quad}}
    for face in bm.faces:
        face.select_set(face == triangle)
    result = repair_local_folds(bm, selected_only=True)
    assert result['folds'] == 1, result
    assert not tip.is_valid
    assert all(v.is_valid and v.co == p for v, p in coordinates.items())
    assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (4, 6, 4)
    assert all(e.is_manifold for e in bm.edges)
    for face, snapshot in uv_snapshot.items():
        assert face.is_valid
        for loop, (vertex, uvs) in zip(face.loops, snapshot):
            assert loop.vert == vertex
            assert all(loop[u].uv == p for u, p in zip(layers, uvs))
    for face in bm.faces:
        face.select_set(face == quad)
    assert not inspect_triangle_quality(bm, selected_only=True)[0]
    assert repair_local_folds(bm)['folds'] == 0
    bm.free()

for protection in ('hidden', 'seam', 'edge_pin', 'uv_pin', 'material', 'ordinary', 'unselected'):
    bm, tip, triangle, quad = fixture(ordinary=protection == 'ordinary')
    if protection == 'hidden':
        triangle.hide_set(True)
    elif protection == 'seam':
        next(iter(tip.link_edges)).seam = True
    elif protection == 'edge_pin':
        pin = bm.edges.layers.int.new('polygroups_pin_edge')
        next(iter(tip.link_edges))[pin] = 1
    elif protection == 'uv_pin':
        quad.loops[0][bm.loops.layers.uv.active].pin_uv = True
    elif protection == 'material':
        triangle.material_index = 1
    for face in bm.faces:
        face.select_set(False)
    result = repair_local_folds(bm, selected_only=protection == 'unselected')
    assert result['folds'] == 0, (protection, result)
    assert tip.is_valid
    bm.free()
print('TWISTED_EAR_TESTS_OK')
