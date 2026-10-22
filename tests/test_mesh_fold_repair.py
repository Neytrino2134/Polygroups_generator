"""Run in Blender --background --factory-startup --python-exit-code 1.

Optionally open the user's blend before this script to exercise both real defects.
No input file is ever saved or changed by this test.
"""
from pathlib import Path
import sys

import addon_utils
import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import repair_local_folds, inspect_triangle_quality


def sphere_fold(scale=1):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=scale)
    bm.normal_update()
    face = max(bm.faces, key=lambda f: f.calc_center_median().z)
    a, c, d = list(face.verts)
    b = bm.verts.new(a.co * .4 + c.co * .4 + d.co * .2)
    e = bm.verts.new(b.co * .8 + d.co * .2)
    bm.faces.remove(face)
    patch = [bm.faces.new((a, c, b, e)), bm.faces.new((a, e, b)),
             bm.faces.new((a, b, c, d))]
    uv = bm.loops.layers.uv.new('UVMap')
    extra = bm.loops.layers.uv.new('SecondUV')
    color = bm.loops.layers.float_color.new('CornerColor')
    for face in bm.faces:
        for loop in face.loops:
            for layer in (uv, extra):
                loop[layer].uv = (loop.vert.co.x / scale, loop.vert.co.y / scale)
            loop[color] = (.2, .4, .6, 1)
    return bm, patch


def counts(bm):
    return len(bm.verts), len(bm.edges), len(bm.faces)


for scale in (1e-3, 1, 1000):
    bm, patch = sphere_fold(scale)
    initial = counts(bm)
    result = repair_local_folds(bm, fix_degenerate=False)
    assert result['folds'] == 1, result
    assert counts(bm) == tuple(n - delta for n, delta in zip(initial, (2, 4, 2)))
    assert all(e.is_manifold for e in bm.edges)
    assert repair_local_folds(bm)['folds'] == 0, 'Must be idempotent'
    bm.free()

for protected in ('hidden', 'uv_pin', 'seam', 'edge_pin', 'material'):
    bm, patch = sphere_fold()
    initial = counts(bm)
    if protected == 'hidden':
        patch[1].hide_set(True)
    elif protected == 'uv_pin':
        patch[1].loops[0][bm.loops.layers.uv.active].pin_uv = True
    elif protected == 'material':
        patch[1].material_index = 1
    else:
        edge = next(e for e in patch[1].edges if all(f in patch for f in e.link_faces))
        if protected == 'seam':
            edge.seam = True
        else:
            vertices = set(edge.verts)
            pin = bm.edges.layers.int.new('polygroups_pin_edge')
            next(e for e in bm.edges if set(e.verts) == vertices)[pin] = 1
    assert repair_local_folds(bm)['folds'] == 0, protected
    assert counts(bm) == initial
    bm.free()

# A valid closed surface and an ordinary small triangle must survive unchanged.
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1)
initial = counts(bm)
assert repair_local_folds(bm)['folds'] == 0
assert counts(bm) == initial
# Make one edge exactly zero on a triangulated local split.
edge = next(iter(bm.edges))
a = edge.verts[0]
_, duplicate = bmesh.utils.edge_split(edge, a, .5)
bmesh.ops.triangulate(bm, faces=list(duplicate.link_faces))
duplicate.co = a.co
result = repair_local_folds(bm)
assert result['collapsed'] == 1 and result['remaining_degenerate'] == 0, result
assert all(e.is_manifold for e in bm.edges)
bm.free()

actual = bpy.data.objects.get('Retopo_02_Highpoly_Generated.001')
if actual and len(actual.data.vertices) == 8492 and len(actual.data.polygons) == 8641:
    def actual_mesh():
        bm = bmesh.new()
        bm.from_mesh(actual.data)
        bm.faces.ensure_lookup_table()
        return bm

    bm = actual_mesh()
    uv = bm.loops.layers.uv.active
    snapshot = {f: (f.index, tuple(tuple(v.co) for v in f.verts),
                    tuple(tuple(l[uv].uv) for l in f.loops)) for f in bm.faces}
    result = repair_local_folds(bm)
    assert (result['folds'], result['collapsed'], result['remaining_degenerate']) == (2, 1, 0), result
    assert counts(bm) == (8488, 17123, 8637), counts(bm)
    assert all(e.is_manifold for e in bm.edges)
    unchanged = 0
    for face, (index, coords, uvs) in snapshot.items():
        if face.is_valid and index != 8510:  # This quad loses its zero-length edge.
            assert tuple(tuple(v.co) for v in face.verts) == coords, index
            assert tuple(tuple(l[uv].uv) for l in face.loops) == uvs, index
            unchanged += 1
    assert unchanged >= 8634, unchanged
    assert repair_local_folds(bm)['folds'] == 0
    bm.free()
    for options, expected in ((dict(fix_degenerate=False), (1, 0, 1)),
                              (dict(fix_folds=False), (0, 1, 0))):
        bm = actual_mesh()
        result = repair_local_folds(bm, **options)
        assert (result['folds'], result['collapsed'], result['remaining_degenerate']) == expected, result
        bm.free()
    for seed, expected in ((8411, (1, 0)), (8511, (1, 1))):
        bm = actual_mesh()
        for f in bm.faces:
            f.select_set(False)
        bm.faces[seed].select_set(True)
        result = repair_local_folds(bm, selected_only=True)
        assert (result['folds'], result['collapsed']) == expected, result
        bm.free()
    print('REAL_STONE_FOLD_REPAIR_OK', unchanged)

# Full add-on registration, operator execution, and both captured UI trees.
addon_utils.enable('polygroups_generator', default_set=False)
from polygroups_generator.custom_ui.schema import capture
for section, prefix in ((2, 'prepare_1'), (3, 'seam_prep_1')):
    model = capture(bpy.context, section)
    assert not model.errors, model.errors
    ops = [binding[1] for binding in model.bindings.values() if binding[0] == 'operator']
    assert ops.count('mesh.polygroups_repair_mesh_folds') == 3, (section, ops)
    assert any(binding[0] == 'property' and binding[2] == 'topic_' + prefix + '_manual'
               for binding in model.bindings.values())
    assert any(binding[0] == 'property' and binding[2] == 'topic_' + prefix + '_auto'
               for binding in model.bindings.values())

mesh = bpy.data.meshes.new('FoldRepairTest')
bm, patch = sphere_fold()
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new('FoldRepairTest', mesh)
bpy.context.collection.objects.link(obj)
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
for o in bpy.context.selected_objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
initial = (len(mesh.vertices), len(mesh.edges), len(mesh.polygons))
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT') == {'FINISHED'}
assert obj.mode == 'EDIT'
assert counts(bmesh.from_edit_mesh(mesh)) == initial
assert any(f.select for f in bmesh.from_edit_mesh(mesh).faces)
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR') == {'FINISHED'}
assert obj.mode == 'EDIT'
assert counts(bmesh.from_edit_mesh(mesh)) == tuple(n - d for n, d in zip(initial, (2, 4, 2)))
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR') == {'FINISHED'}
unchanged_counts = counts(bmesh.from_edit_mesh(mesh))
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT_QUALITY') == {'FINISHED'}
assert counts(bmesh.from_edit_mesh(mesh)) == unchanged_counts

# Optional real pack: exact zero-edge repair must retain every surviving corner
# in all five LODs of both models, including seam and pinned-edge flags.
for model in ('02', '06'):
    for lod in range(5):
        name = f'SM_GraveStones_02_{model}_LOD{lod}'
        asset = bpy.data.objects.get(name)
        if asset is None:
            continue
        bm = bmesh.new()
        bm.from_mesh(asset.data)
        _, quality_before = inspect_triangle_quality(bm)
        assert quality_before['zero_triangles'] == 2, (name, quality_before)
        layers = list(bm.loops.layers.uv.values())
        snapshot = {f: (tuple(tuple(v.co) for v in f.verts),
                        [tuple(tuple(l[u].uv) for l in f.loops) for u in layers])
                    for f in bm.faces}
        coords_before = {tuple(v.co) for v in bm.verts}
        # Geometric keys remain stable when identical endpoints are welded.
        pin = bm.edges.layers.int.get('polygroups_pin_edge')
        flags = {}
        for edge in bm.edges:
            key = frozenset(tuple(v.co) for v in edge.verts)
            seam, sharp, pinned = flags.get(key, (False, False, False))
            flags[key] = (seam or edge.seam, sharp or not edge.smooth,
                          pinned or (pin is not None and bool(edge[pin])))
        invalid_before = sum(not e.is_manifold for e in bm.edges)
        result = repair_local_folds(bm, fix_folds=False, fix_degenerate=False, fix_zero_area=True)
        _, quality_after = inspect_triangle_quality(bm)
        assert result['collapsed'] == 1 and quality_after['zero_triangles'] == 0, (name, result)
        assert sum(not e.is_manifold for e in bm.edges) == invalid_before
        assert {tuple(v.co) for v in bm.verts} == coords_before
        assert len(bm.faces) == len(snapshot) - 2
        for face, (coords, uvs) in snapshot.items():
            if face.is_valid:
                assert tuple(tuple(v.co) for v in face.verts) == coords, name
                assert [tuple(tuple(l[u].uv) for l in face.loops) for u in layers] == uvs, name
        for edge in bm.edges:
            key = frozenset(tuple(v.co) for v in edge.verts)
            assert (edge.seam, not edge.smooth,
                    pin is not None and bool(edge[pin])) == flags[key], (name, key)
        assert repair_local_folds(bm, fix_folds=False, fix_degenerate=False,
                                  fix_zero_area=True)['collapsed'] == 0
        print('GRAVESTONES_LOD_ZERO_AREA_OK', name, quality_before, quality_after)
        bm.free()
print('MESH_FOLD_REPAIR_TESTS_OK', flush=True)
