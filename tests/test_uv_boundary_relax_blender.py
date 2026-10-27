"""Pinned UV coordinates, real interior relaxation, seams, secondary maps and passes."""
from pathlib import Path
import sys
from unittest.mock import patch
import bpy
import bmesh
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
assert addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import uv_boundary_relax as repair, smart_lods

ctx = bpy.context
mesh = bpy.data.meshes.new('Distorted UV Grid')
vertices = [(x, y, 0) for y in range(5) for x in range(5)]
faces = [(y*5+x, y*5+x+1, (y+1)*5+x+1, (y+1)*5+x) for y in range(4) for x in range(4)]
mesh.from_pydata(vertices, [], faces)
uv = mesh.uv_layers.new(name='Color')
for loop in mesh.loops:
    x, y, _ = vertices[loop.vertex_index]
    uv.data[loop.index].uv = (.8, .2) if (x, y) == (2, 2) else (x/4, y/4)
    if (x, y) == (1, 1):
        uv.data[loop.index].pin_uv = True
second = mesh.uv_layers.new(name='Lightmap')
for index, value in enumerate(second.data):
    value.uv = (.1 + index*.002, .9 - index*.003)
mesh.uv_layers.active_index = 0
obj = bpy.data.objects.new('Distorted UV Grid', mesh)
ctx.collection.objects.link(obj)
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
ctx.view_layer.objects.active = obj
ctx.view_layer.update()


def boundaries(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    pinned, edges = repair.boundary_loops(bm, bm.loops.layers.uv.active)
    snapshot = {(loop.face.index, list(loop.face.loops).index(loop)): tuple(loop[bm.loops.layers.uv.active].uv) for loop in pinned}
    bm.free()
    return snapshot


before = boundaries(obj)
pins = [data.pin_uv for data in mesh.uv_layers[0].data]
secondary = [tuple(data.uv) for data in mesh.uv_layers[1].data]
seams = [edge.use_seam for edge in mesh.edges]
selected_before = [face.select for face in mesh.polygons]
assert repair.relax_uv_boundaries(ctx, obj) == len(before)
assert boundaries(obj) == before
assert [data.pin_uv for data in mesh.uv_layers[0].data] == pins
assert [tuple(data.uv) for data in mesh.uv_layers[1].data] == secondary
assert [edge.use_seam for edge in mesh.edges] == seams
assert [face.select for face in mesh.polygons] == selected_before
centers = [mesh.uv_layers[0].data[loop.index].uv for loop in mesh.loops if loop.vertex_index == 12]
assert all((center - __import__('mathutils').Vector((.5, .5))).length < .02 for center in centers), centers
assert obj.mode == 'OBJECT' and ctx.active_object == obj
# Discontinuous UV corners are boundaries even without marked seams.
for face in mesh.polygons:
    if face.center.x > 2:
        for index in face.loop_indices:
            mesh.uv_layers[0].data[index].uv.x += 2
before = boundaries(obj)
assert len(before) > 16
repair.relax_uv_boundaries(ctx, obj)
assert boundaries(obj) == before
assert not any(edge.use_seam for edge in mesh.edges)

# Verify both real passes run on the current object and every generated LOD.
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12)
source = ctx.object
source.name = 'UV_Decimate_Source'
for edge in source.data.edges:
    edge.use_seam = all(abs(source.data.vertices[i].co.y) < 1e-5 for i in edge.vertices)
original_vertices = len(source.data.vertices)
calls = []
real = repair.relax_uv_boundaries
def checked(context, target):
    before = boundaries(target)
    count = real(context, target)
    assert boundaries(target) == before
    calls.append(target.name)
    return count
with patch.object(repair, 'relax_uv_boundaries', checked):
    assert bpy.ops.object.polygroups_smart_decimate(ratio=.6, seams_ratio=.9) == {'FINISHED'}
assert calls == [source.name, source.name]
assert ctx.active_object == source and len(source.data.vertices) < original_vertices
assert not source.modifiers
settings = ctx.scene.polygroups_mesh_finalization_settings
settings.smart_lods_count = 2
settings.smart_lods_target_1, settings.smart_lods_target_2 = 200, 100
settings.smart_lods_auto_arrange = settings.smart_lods_create_text = False
calls.clear()
source_uv = [tuple(data.uv) for data in source.data.uv_layers.active.data]
with patch.object(smart_lods, 'relax_uv_boundaries', checked):
    assert bpy.ops.object.polygroups_generate_smart_lods(active_only=True) == {'FINISHED'}
assert len(set(calls)) == 2 and all(calls.count(name) >= 2 for name in set(calls))
assert [tuple(data.uv) for data in source.data.uv_layers.active.data] == source_uv

# A failed UV repair restores the pre-apply topology and its decimation stack.
before_vertices = len(source.data.vertices)
before_uv = [tuple(data.uv) for data in source.data.uv_layers.active.data]
def failure(context, target):
    target.data.uv_layers.active.data[0].uv = (50, 50)
    raise RuntimeError('Injected UV solver failure')
with patch.object(repair, 'relax_uv_boundaries', failure):
    assert bpy.ops.object.polygroups_smart_decimate(ratio=.5) == {'CANCELLED'}
assert len(source.data.vertices) == before_vertices
assert [tuple(data.uv) for data in source.data.uv_layers.active.data] == before_uv
assert len(source.modifiers) == 2
print('UV_BOUNDARY_RELAX_AND_PASS_INTEGRATION_PASSED')
