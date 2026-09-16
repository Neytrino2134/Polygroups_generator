"""Blender background regression for Batch Import's per-collection blend output."""

import sys
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators import import_queue


with tempfile.TemporaryDirectory() as directory:
    working_path = Path(directory) / "Original blend name.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(working_path))

    collection = bpy.data.collections.new("Generated.007")
    bpy.context.scene.collection.children.link(collection)
    mesh = bpy.data.meshes.new("GeneratedMesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("Highpoly_Generated.007", mesh)
    collection.objects.link(obj)
    retopo_mesh = mesh.copy()
    retopo = bpy.data.objects.new("Retopo_03_Highpoly_Generated.007", retopo_mesh)
    collection.objects.link(retopo)

    expected = Path(directory) / "Original blend name_Generated_007.blend"
    assert Path(import_queue.generated_collection_output_path(
        str(working_path), collection.name,
    )) == expected

    reports = []
    queue = SimpleNamespace(
        collection=collection,
        owned_objects={obj, retopo},
        owned_collections={collection},
        owned_meshes={mesh, retopo_mesh},
        owned_materials=set(),
        owned_images=set(),
        owned_gray_materials=set(),
        owned_bake_materials=set(),
        owned_bake_images=set(),
        file_objects=[obj, retopo],
        meshes=[obj, retopo],
        pass_sources=[obj],
        pass_outputs=[obj],
        result_meshes=[obj, retopo],
        separately_saved_count=0,
        separately_saved_object_count=0,
        report=lambda kind, message: reports.append((kind, message)),
    )
    import_queue.ImportQueue.save_and_clear_completed_collection(queue)

    assert expected.is_file()
    assert not collection.objects
    assert collection.name in bpy.data.collections
    assert collection not in queue.owned_collections
    assert queue.separately_saved_count == 1
    assert queue.separately_saved_object_count == 2
    assert not queue.file_objects and not queue.meshes

    with bpy.data.libraries.load(str(expected)) as (source, _target):
        assert "Generated.007" in source.collections
        assert "Scene" in source.scenes
        assert "Highpoly_Generated.007" in source.objects
        assert "Retopo_03_Highpoly_Generated.007" in source.objects

    working_snapshot = Path(directory) / "working_snapshot.blend"
    shutil.copy2(working_path, working_snapshot)
    with bpy.data.libraries.load(str(working_snapshot)) as (source, _target):
        assert "Generated.007" in source.collections
        assert "Highpoly_Generated.007" not in source.objects
        assert "Retopo_03_Highpoly_Generated.007" not in source.objects

    # Restore is repeatable and returns only Retopo_* into the empty placeholder.
    assert bpy.ops.object.polygroups_restore_separate_retopo() == {"FINISHED"}
    assert [item.name for item in collection.objects] == [
        "Retopo_03_Highpoly_Generated.007",
    ]
    assert bpy.data.objects.get("Highpoly_Generated.007") is None
    assert bpy.ops.object.polygroups_restore_separate_retopo() == {"FINISHED"}
    assert len([item for item in collection.objects if item.name.startswith("Retopo_")]) == 1

    # Exercise the complete queue handoff: successful processing writes one file,
    # empties the numbered placeholder, and advances normally.
    obj_path = Path(directory) / "queued.obj"
    obj_path.write_text("o Queued\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    settings = bpy.context.scene.polygroups_model_preparation_settings
    settings.batch_save_generated_separately = True
    settings.batch_auto_save = True  # Separate saving takes precedence.
    settings.batch_separate_collections = True
    settings.batch_auto_arrange_objects = False
    settings.batch_apply_weld = False
    settings.batch_stage_2_enabled = False
    settings.batch_stage_3_enabled = False
    settings.batch_stage_4_enabled = False
    settings.batch_stage_5_enabled = False
    settings.batch_narrow_island_enabled = False
    settings.batch_small_islands_enabled = False
    settings.batch_second_narrow_island_enabled = False
    settings.batch_second_small_islands_enabled = False
    settings.batch_autobake_enabled = False
    queue = import_queue.ImportQueue(
        bpy.context,
        [str(obj_path)],
        file_selection=False,
        report=lambda kind, message: reports.append((kind, message)),
    )
    queue.begin()
    for _step in range(50):
        queue.step(bpy.context)
        if queue.finished:
            break
    assert queue.finished and settings.batch_stage == "DONE"
    assert settings.batch_imported_count == 1
    assert queue.separately_saved_count == 1
    queued_collection = bpy.data.collections["Generated.001"]
    assert not queued_collection.objects
    queued_output = Path(directory) / "Original blend name_Generated_001.blend"
    assert queued_output.is_file()
    with bpy.data.libraries.load(str(queued_output)) as (source, _target):
        assert "Generated.001" in source.collections
        assert "Highpoly_Generated.001" in source.objects
        assert "Highpoly_Generated.007" not in source.objects

    # The separate result must open normally with its Generated.N linked into
    # the scene, while Save As Copy keeps the working path unchanged.
    assert bpy.ops.wm.open_mainfile(filepath=str(expected)) == {"FINISHED"}
    assert bpy.data.collections.get("Generated.007") is not None
    assert bpy.data.objects.get("Highpoly_Generated.007") is not None
    assert any(
        child.name == "Generated.007"
        for child in bpy.context.scene.collection.children
    )

print("batch separate save test passed")
