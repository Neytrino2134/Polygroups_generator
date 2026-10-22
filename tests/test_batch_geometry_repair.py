"""Blender regression for unified end-of-pass geometry repair and JSON stats."""
from pathlib import Path
import json
import sys
import tempfile

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.import_queue import ImportQueue
from polygroups_generator.operators.mesh_export import _write_export_mesh_info
from polygroups_generator.core.mesh_fold_repair import inspect_triangle_quality
from polygroups_generator.custom_ui.schema import capture

settings = bpy.context.scene.polygroups_model_preparation_settings
queue = ImportQueue.__new__(ImportQueue)
queue.settings = settings
queue.batch_stages = True
queue.pass_method = 'QUAD'
queue.owned_meshes = set()


def fixture(name):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1)
    edge = next(iter(bm.edges))
    a = edge.verts[0]
    _, duplicate = bmesh.utils.edge_split(edge, a, .5)
    bmesh.ops.triangulate(bm, faces=list(duplicate.link_faces))
    duplicate.co = a.co
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def zeros(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        return inspect_triangle_quality(bm)[1]['zero_triangles']
    finally:
        bm.free()


for number in (2, 3, 4):
    queue.pass_number = number
    prop = 'batch_first_geometry_repair' if number == 2 else f'batch_stage_{number}_geometry_repair'
    assert getattr(settings, prop) is True
    obj = fixture(f'Pass{number}')
    assert zeros(obj) > 0
    shared = bpy.data.objects.new(f'Shared{number}', obj.data)
    bpy.context.collection.objects.link(shared)
    queue.repair_completed_pass_geometry(bpy.context, [obj])
    assert zeros(obj) == 0 and zeros(shared) > 0
    assert obj.data != shared.data and obj.data in queue.owned_meshes
    setattr(settings, prop, False)
    disabled = fixture(f'Disabled{number}')
    queue.repair_completed_pass_geometry(bpy.context, [disabled])
    assert zeros(disabled) > 0
    setattr(settings, prop, True)

# Exercise the queue transition itself: the completed pass is repaired before
# forwarding its outputs, and the third pass reaches packing/baking afterwards.
settings.batch_narrow_island_enabled = settings.batch_small_islands_enabled = False
settings.batch_second_narrow_island_enabled = settings.batch_second_small_islands_enabled = False
for number in (2, 3, 4):
    target = fixture(f'Transition{number}')
    queue.pass_number = number
    queue.pass_outputs = [target]
    queue.pass_sources = []
    queue.pass_index = 0
    queue.stage = 'COMPLETE_UNWRAP_PASS'
    queue.advance(bpy.context)
    assert zeros(target) == 0
    assert queue.result_meshes == queue.pass_sources == [target]
    assert queue.stage == 'PASS_SETUP'
queue.second_cleanup_done = True
queue.passes = [None]
settings.batch_stage_5_enabled = True
settings.batch_autobake_enabled = True
queue.advance(bpy.context)
assert queue.stage == 'PACK'
settings.batch_stage_5_enabled = False
queue.stage = 'PASS_SETUP'
queue.advance(bpy.context)
assert queue.stage == 'BAKE_SETUP'

# Property is available in the shared Batch Import UI tree.
settings.batch_expanded_stages = (1 << 12) - 1
model = capture(bpy.context, 1)
assert not model.errors, model.errors
props = {b[2] for b in model.bindings.values() if b[0] == 'property'}
assert {'batch_first_geometry_repair', 'batch_stage_3_geometry_repair',
        'batch_stage_4_geometry_repair'} <= props

entries = [dict(name='Rock_HIGH', triangles=100, vertices=60),
           dict(name='Rock_MID', triangles=50, vertices=30),
           dict(name='Rock_LOD0', triangles=20, vertices=15)]
with tempfile.TemporaryDirectory() as directory:
    for engine in ('Unity', 'Unreal'):
        _write_export_mesh_info(directory, 'JSON', entries, engine)
        document = json.loads((Path(directory) / 'MeshInfo.json').read_text())
        assert document['polygon_statistics']['HIGH_MID'] == dict(meshes=2, average=75, min=50, max=100)
print('BATCH_GEOMETRY_REPAIR_OK', flush=True)
