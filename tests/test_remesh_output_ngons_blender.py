"""Every Quad Remesher preset triangulates n-gons on completed output only."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core.remesh_defaults import get_remesh_preset_counts
from polygroups_generator.core.remesh_job import RemeshJob, VoxelRemeshJob
from polygroups_generator.core.mesh_ngons import ngon_count

context = bpy.context
presets = [name for name, _count in get_remesh_preset_counts(context)]
assert presets == ['LOW', 'MID', 'HIGH', 'ULTRA']


def make_mesh(name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (2, 1, 0), (1, 2, 0),
                      (0, 2, 0), (-1, 1, 0), (0, 0, 1), (1, 0, 1),
                      (1, 1, 1), (0, 1, 1)], [],
                     [(0, 1, 2, 3, 4, 5), (6, 7, 8, 9)])
    uv = mesh.uv_layers.new(name='UVMap')
    for polygon in mesh.polygons:
        for index in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[index].vertex_index]
            uv.data[index].uv = (vertex.co.x, vertex.co.y)
    return mesh


for preset in presets:
    source = bpy.data.objects.new(f'Retopo_01_{preset}', make_mesh(f'Source {preset}'))
    context.scene.collection.objects.link(source)
    source_count = ngon_count(source.data)

    class Backend:
        @staticmethod
        def doRemeshing_Finish(_state, _context):
            result = bpy.data.objects.new(f'Raw {preset}', make_mesh(f'Output {preset}'))
            context.scene.collection.objects.link(result)

    job = RemeshJob(Backend, lambda *_: None)
    job.source = source
    job.source_name = source.name
    job.source_collections = tuple(source.users_collection)
    job.auto_generate_seams = False
    job.auto_unwrap_checker = False
    outputs = job.finish(context)
    assert len(outputs) == 1
    result = outputs[0]
    assert result.name == f'Retopo_02_{preset}'
    assert ngon_count(result.data) == 0
    assert sorted(len(face.vertices) for face in result.data.polygons) == [3, 3, 3, 3, 4]
    assert result.data.uv_layers.active is not None
    assert ngon_count(source.data) == source_count == 1
    assert source.hide_viewport and source.hide_render

bpy.ops.mesh.primitive_cube_add()
voxel_source = context.object
voxel_source.name = 'Voxel source'
settings = context.scene.polygroups_model_preparation_settings
settings.remesh_pregenerate_polygroups = False
settings.remesh_auto_generate_seams = False
settings.remesh_auto_unwrap_checker = False
voxel = VoxelRemeshJob(.25, lambda *_: None)
voxel.start(context)
voxel_result = voxel.finish(context)[0]
assert voxel_result != voxel_source and voxel_result.type == 'MESH'
assert len(voxel_result.data.polygons) > 0 and ngon_count(voxel_result.data) == 0

print('QUAD_REMESH_ALL_PRESETS_OUTPUT_NGONS_OK', flush=True)
