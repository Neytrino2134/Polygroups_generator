"""Run with Blender --background --factory-startup --python this_file."""
import math
import sys
from pathlib import Path
import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.repair_uv_stretch import analyze
from polygroups_generator.pin_edges import pin_layer, is_pinned


def cylinder(distorted=True):
    if bpy.context.object and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bm = bmesh.new()
    rows, columns = 9, 16
    verts = [[bm.verts.new((math.cos(2*math.pi*j/columns), math.sin(2*math.pi*j/columns), i*.4))
              for j in range(columns)] for i in range(rows)]
    layer = bm.loops.layers.uv.new('UVMap')
    for i in range(rows-1):
        for j in range(columns):
            face = bm.faces.new((verts[i][j], verts[i][(j+1)%columns],
                                 verts[i+1][(j+1)%columns], verts[i+1][j]))
            for loop, row, col in zip(face.loops, (i,i,i+1,i+1), (j,j+1,j+1,j)):
                if distorted:
                    radius = .45 * math.exp(-row*.6)
                    loop[layer].uv = (.5 + radius*math.cos(2*math.pi*col/columns),
                                      .5 + radius*math.sin(2*math.pi*col/columns))
                else:
                    loop[layer].uv = (col/columns, row*.4/(2*math.pi))
    mesh = bpy.data.meshes.new('RepairTest')
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new('RepairTest', mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    return obj


obj = cylinder(False)
bm = bmesh.from_edit_mesh(obj.data)
assert not analyze(bm, 4, 1.8, 6, 2, math.radians(75)), 'Healthy cylinder falsely detected'

obj = cylinder(True)
bm = bmesh.from_edit_mesh(obj.data)
regions = analyze(bm, 4, 1.8, 6, 2, math.radians(75))
assert regions, 'Compressed cylinder missed'
uv = bm.loops.layers.uv.active
before = [tuple(l[uv].uv) for f in bm.faces for l in f.loops]
assert bpy.ops.mesh.polygroups_repair_uv_stretch(action='SELECT') == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
assert not any(e.seam for e in bm.edges)
assert before == [tuple(l[uv].uv) for f in bm.faces for l in f.loops]

for create_edges in (False, True):
    obj = cylinder(True)
    bm = bmesh.from_edit_mesh(obj.data)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        for l in f.loops:
            l[uv].pin_uv = True
    assert bpy.ops.mesh.polygroups_repair_uv_stretch(create_edges=create_edges) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(obj.data)
    assert any(e.seam for e in bm.edges), 'No seams generated'
    assert all(is_pinned(e, pin_layer(bm)) for e in bm.edges if e.seam)
    uv = bm.loops.layers.uv.active
    assert all(l[uv].pin_uv for f in bm.faces for l in f.loops), 'UV pin flags lost'
    selected = [f for f in bm.faces if f.select]
    assert selected
    assert all(math.isfinite(value) for f in selected for l in f.loops for value in l[uv].uv)
    assert not analyze(bm, 4, 1.8, 6, 2, math.radians(75)), 'Repair left critical distortion'

obj = cylinder(True)
bpy.ops.mesh.select_all(action='DESELECT')
assert bpy.ops.mesh.polygroups_repair_uv_stretch(selected_only=True) == {'FINISHED'}
assert not any(e.seam for e in bmesh.from_edit_mesh(obj.data).edges)
print('UV_REPAIR_TESTS_PASSED')

# Unaffected UVs, hidden faces and old seams must survive; exercise Smart Relax.
obj = cylinder(True)
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
v = [bm.verts.new((x, y, 10)) for x, y in ((0,0),(1,0),(1,1),(0,1))]
outside = bm.faces.new(v)
outside.material_index = 7
for loop in outside.loops:
    loop[uv].uv = (loop.vert.co.x + 3, loop.vert.co.y + 3)
outside.edges[0].seam = True
outside.hide_set(True)
outside_uv = [tuple(l[uv].uv) for l in outside.loops]
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_repair_uv_stretch(smart_relax=True, pin_generated=False) == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
outside = next(f for f in bm.faces if f.material_index == 7)
uv = bm.loops.layers.uv.active
assert outside.hide and outside_uv == [tuple(l[uv].uv) for l in outside.loops]
assert any(e.seam for e in outside.edges)
assert not any(is_pinned(e, pin_layer(bm)) for e in bm.edges)

# One boundary (capped tube/cone) needs a cut from its boundary to its interior.
from polygroups_generator.operators.repair_uv_stretch import longitudinal_cut
obj = cylinder(True)
bm = bmesh.from_edit_mesh(obj.data)
top = [v for v in bm.verts if abs(v.co.z-3.2) < 1e-5]
top.sort(key=lambda v: math.atan2(v.co.y, v.co.x))
bm.faces.new(top)
bm.normal_update()
bm.edges.index_update()
boundary, cut = longitudinal_cut(bm, set(bm.faces), 3)
assert boundary and cut
assert any(v in {v for e in boundary for v in e.verts} for e in cut for v in e.verts)

# Roll back the entire mesh if the post-commit relaxation/unwrap stage fails.
from polygroups_generator.operators import repair_uv_stretch as module
obj = cylinder(True)
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
snapshot = [tuple(l[uv].uv) for f in bm.faces for l in f.loops]
old_relax = module.relax_seams
def fail(*args, **kwargs):
    raise RuntimeError('intentional rollback test')
module.relax_seams = fail
try:
    try:
        bpy.ops.mesh.polygroups_repair_uv_stretch(smart_relax=True)
    except RuntimeError as error:
        assert 'intentional rollback test' in str(error)
finally:
    module.relax_seams = old_relax
assert obj.mode == 'EDIT'
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
assert snapshot == [tuple(l[uv].uv) for f in bm.faces for l in f.loops]
assert not any(e.seam for e in bm.edges)
print('UV_REPAIR_EXTENDED_TESTS_PASSED')

# A visible, correctly mapped island with a different density stays untouched.
obj = cylinder(True)
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
verts = [bm.verts.new((x, y, 15)) for x, y in ((0,0),(1,0),(1,1),(0,1))]
outside = bm.faces.new(verts)
outside.material_index = 8
for loop in outside.loops:
    loop[uv].uv = (10 + loop.vert.co.x*.001, 10 + loop.vert.co.y*.001)
before = [tuple(l[uv].uv) for l in outside.loops]
bm.normal_update()
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_repair_uv_stretch() == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
outside = next(f for f in bm.faces if f.material_index == 8)
assert not outside.select
assert before == [tuple(l[uv].uv) for l in outside.loops], 'Unrelated visible UVs changed'
assert not any(e.seam for e in outside.edges)

# A second run should be a no-op after the first successful repair.
seams = sum(e.seam for e in bm.edges)
before = [tuple(l[uv].uv) for f in bm.faces for l in f.loops]
assert bpy.ops.mesh.polygroups_repair_uv_stretch() == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
assert seams == sum(e.seam for e in bm.edges)
assert before == [tuple(l[uv].uv) for f in bm.faces for l in f.loops]
print('UV_REPAIR_ISOLATION_AND_REPEAT_PASSED')

# Local merger uses the repaired selection's total area and may remove only
# explicitly generated seams.
from polygroups_generator.operators.small_islands import plan_merge
bm = bmesh.new()
grid = [[bm.verts.new((x, y, 0)) for x in range(3)] for y in range(6)]
faces = []
for y in range(5):
    for x in range(2):
        face = bm.faces.new((grid[y][x], grid[y][x+1], grid[y+1][x+1], grid[y+1][x]))
        face.select_set(True)
        faces.append(face)
bm.faces.new(tuple(bm.verts.new((20+x, y, 0)) for x, y in ((0,0),(100,0),(100,100),(0,100))))
corner = faces[0]
border = {edge for edge in corner.edges if edge.is_manifold}
for edge in border:
    edge.seam = True
bm.edges.index_update()
allowed = {edge.index for edge in border}
removed, total, small, merged = plan_merge(
    bm, 11.0, protect_sharp=False, selected_only=True, protect_pinned=False,
    threshold_basis='TOTAL', removable_edges=allowed)
assert (total, small, merged) == (2, 1, 1)
assert removed == allowed
removed, _, _, merged = plan_merge(
    bm, 11.0, protect_sharp=False, selected_only=True, protect_pinned=False,
    threshold_basis='TOTAL', removable_edges={min(allowed)})
assert not removed and merged == 0, 'A seam outside the generated set was removed'
bm.free()

# Local merge must execute before generated edge pins are written.
obj = cylinder(True)
events = []
old_plan_merge = module.plan_merge
old_set_pinned = module.set_pinned
def observe_merge(*args, **kwargs):
    events.append('merge')
    return old_plan_merge(*args, **kwargs)
def observe_pin(*args, **kwargs):
    events.append('pin')
    return old_set_pinned(*args, **kwargs)
module.plan_merge = observe_merge
module.set_pinned = observe_pin
try:
    assert bpy.ops.mesh.polygroups_repair_uv_stretch(
        merge_small_islands=True, small_island_threshold=3.0,
        pin_generated=True) == {'FINISHED'}
finally:
    module.plan_merge = old_plan_merge
    module.set_pinned = old_set_pinned
assert events and events[0] == 'merge' and events[-1] == 'pin', events
print('UV_REPAIR_LOCAL_MERGER_PASSED')

# Whole-mesh Average Islands Scale and native packing run after local unwrap,
# include unrelated islands, and restore the repaired-region selection.
obj = cylinder(True)
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
verts = [bm.verts.new((x, y, 20)) for x, y in ((0,0),(1,0),(1,1),(0,1))]
outside = bm.faces.new(verts)
outside.material_index = 9
for loop in outside.loops:
    loop[uv].uv = (20 + loop.vert.co.x * .01, 20 + loop.vert.co.y * .01)
bm.normal_update()
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.mesh.polygroups_repair_uv_stretch(
    average_island_scale=True, native_pack=True) == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
uv = bm.loops.layers.uv.active
all_uvs = [value for face in bm.faces for loop in face.loops for value in loop[uv].uv]
assert min(all_uvs) >= -1e-5 and max(all_uvs) <= 1.00001, (min(all_uvs), max(all_uvs))
outside = next(face for face in bm.faces if face.material_index == 9)
assert not outside.select, 'Whole-mesh UV post-process did not restore repaired selection'
assert any(face.select for face in bm.faces if face is not outside)
print('UV_REPAIR_AVERAGE_AND_PACK_PASSED')
