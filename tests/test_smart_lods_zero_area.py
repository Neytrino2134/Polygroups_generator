"""Blender integration: Smart LOD zero-area cleanup, default, and opt-out."""
from pathlib import Path
import sys

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import smart_lods


def add_zero_triangle(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    verts = [bm.verts.new(p) for p in ((2, 0, 0), (3, 0, 0), (4, 0, 0))]
    bm.faces.new(verts)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


# A collinear face is removed, while a nonzero sliver and its UVs survive.
mesh = bpy.data.meshes.new('ZeroAreaFixture')
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, .00001, 0)], [], [(0, 1, 2)])
mesh.uv_layers.new(name='UVMap')
for loop, uv in zip(mesh.uv_layers.active.data, ((0, 0), (1, 0), (0, 1))):
    loop.uv = uv
obj = bpy.data.objects.new('ZeroAreaFixture', mesh)
bpy.context.collection.objects.link(obj)
add_zero_triangle(mesh)
assert smart_lods._clean_zero_area_lod(obj) == 1
assert len(mesh.polygons) == 1
assert [tuple(l.uv) for l in mesh.uv_layers.active.data] == [(0, 0), (1, 0), (0, 1)]
assert smart_lods._clean_zero_area_lod(obj) == 0

bpy.ops.mesh.primitive_cube_add()
source = bpy.context.object
source.name = 'ZeroAreaLODSource'
settings = bpy.context.scene.polygroups_mesh_finalization_settings
assert settings.smart_lods_remove_zero_area is True
settings.smart_lods_count = 2
settings.smart_lods_target_1 = settings.smart_lods_target_2 = 100
settings.smart_lods_auto_arrange = False
settings.smart_lods_create_text = False
before = tuple(tuple(v.co) for v in source.data.vertices)
calls = []
original = smart_lods._clean_zero_area_lod


def cleanup_after_modifiers(lod):
    assert not lod.modifiers, 'Cleanup must run after decimation/triangulation'
    calls.append(lod.name)
    add_zero_triangle(lod.data)  # Simulate a topology modifier leaving a degenerate face.
    assert original(lod) == 1
    return 1


smart_lods._clean_zero_area_lod = cleanup_after_modifiers
try:
    assert bpy.ops.object.polygroups_generate_smart_lods(active_only=True) == {'FINISHED'}
    assert calls == [source.name + '.LOD.1', source.name + '.LOD.2']
    for name in calls:
        lod = bpy.data.objects[name]
        bm = bmesh.new()
        bm.from_mesh(lod.data)
        assert all((b.vert.co - a.vert.co).cross(c.vert.co - a.vert.co).length > 0
                   for a, b, c in bm.calc_loop_triangles())
        bm.free()
    assert tuple(tuple(v.co) for v in source.data.vertices) == before
    bpy.ops.mesh.primitive_cube_add()
    second = bpy.context.object
    second.name = 'ZeroAreaCleanupDisabled'
    settings.smart_lods_remove_zero_area = False
    assert bpy.ops.object.polygroups_generate_smart_lods(active_only=True) == {'FINISHED'}
    assert len(calls) == 2, 'Disabled option must bypass cleanup'
finally:
    smart_lods._clean_zero_area_lod = original
print('SMART_LODS_ZERO_AREA_OK', flush=True)
