"""Blender smoke test for native Voxel Remesh used by Import queues."""

from pathlib import Path
import sys

import bpy


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
import polygroups_generator as addon
from polygroups_generator.core.remesh_job import VoxelRemeshJob
from polygroups_generator.operators.import_queue import ImportQueue


addon.register()
try:
    settings = bpy.context.scene.polygroups_model_preparation_settings
    assert settings.file_import_auto_remesh and settings.batch_auto_remesh
    assert settings.file_import_clear_material and settings.batch_clear_material
    assert settings.file_import_remesh_preset == "HIGH"
    assert settings.batch_remesh_preset == "HIGH"
    assert abs(settings.file_import_voxel_size - 0.003) < 1e-7
    assert abs(settings.batch_voxel_size - 0.003) < 1e-7

    settings.batch_remesh_method = "VOXEL"
    queue = ImportQueue(bpy.context, [], False, print)
    assert queue.remesh_method == "VOXEL" and queue.backend is None

    settings.remesh_pregenerate_polygroups = False
    settings.remesh_auto_generate_seams = False
    settings.remesh_auto_unwrap_checker = False
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    source = bpy.context.object
    source.name = "Voxel_Source"
    source_mesh = source.data

    job = VoxelRemeshJob(0.1, print)
    job.start(bpy.context)
    assert job.poll() == (True, 1.0)
    outputs = job.finish(bpy.context)
    assert len(outputs) == 1
    result = outputs[0]
    assert result.name == "Retopo_Voxel_Source"
    assert result.data != source_mesh
    assert not result.modifiers
    assert len(result.data.polygons) > 0
    assert source.hide_get()
    assert bpy.context.active_object == result and result.select_get()

    bpy.data.objects.remove(result, do_unlink=True)
    bpy.data.objects.remove(source, do_unlink=True)
    if source_mesh.users == 0:
        bpy.data.meshes.remove(source_mesh)
    print("VOXEL_IMPORT_REMESH_OK", flush=True)
finally:
    addon.unregister()
