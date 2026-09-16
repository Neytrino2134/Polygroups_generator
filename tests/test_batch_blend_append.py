"""Blender background regression for Batch Import's Blend append mode."""

import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)


def write_source(filepath, collection_name, object_names):
    collection = bpy.data.collections.new(collection_name)
    objects = []
    meshes = []
    for name in object_names:
        mesh = bpy.data.meshes.new(name + "Mesh")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        objects.append(obj)
        meshes.append(mesh)
    bpy.data.libraries.write(str(filepath), {collection})
    bpy.data.collections.remove(collection, do_unlink=True)
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in meshes:
        if mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)


with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    write_source(
        folder / "first.blend",
        "Generated",
        ("Highpoly_First", "Retopo_First"),
    )
    write_source(
        folder / "second.blend",
        "Generated.014",
        ("Highpoly_Second.014", "Retopo_Second.014"),
    )
    write_source(folder / "ignored.blend", "Other", ("Retopo_Ignored",))
    write_source(folder / "empty.blend", "Generated.003", ())
    write_source(folder / "misc.blend", "Generated.004", ("Helper_Mesh",))
    write_source(folder / "highonly.blend", "Generated.005", ("Highpoly_Only",))

    settings = bpy.context.scene.polygroups_model_preparation_settings
    settings.batch_import_directory = str(folder)
    settings.batch_import_format = "BLEND"
    settings.batch_include_subfolders = False
    settings.batch_append_include_highpoly = False

    assert bpy.ops.object.polygroups_scan_import_folder() == {"FINISHED"}
    assert settings.batch_total_count == 6
    assert bpy.ops.object.polygroups_append_generated_blends() == {"FINISHED"}
    assert bpy.data.collections.get("Generated.001") is not None
    assert bpy.data.collections.get("Generated.002") is not None
    assert bpy.data.objects.get("Retopo_First.001") is not None
    assert bpy.data.objects.get("Retopo_Second.002") is not None
    assert not any(obj.name.lower().startswith("highpoly_") for obj in bpy.data.objects)
    assert settings.batch_imported_count == 2
    assert settings.batch_imported_object_count == 2
    assert bpy.data.objects.get("Helper_Mesh") is None
    assert bpy.data.objects.get("Highpoly_Only") is None

    # A second append continues after the highest current index and can include HighPoly.
    settings.batch_append_include_highpoly = True
    assert bpy.ops.object.polygroups_append_generated_blends() == {"FINISHED"}
    assert bpy.data.collections.get("Generated.003") is not None
    assert bpy.data.collections.get("Generated.004") is not None
    assert bpy.data.objects.get("Highpoly_First.003") is not None
    assert bpy.data.objects.get("Retopo_First.003") is not None
    assert bpy.data.objects.get("Highpoly_Only.004") is not None
    assert bpy.data.collections.get("Generated.005") is not None
    assert bpy.data.objects.get("Highpoly_Second.005") is not None
    assert bpy.data.objects.get("Retopo_Second.005") is not None
    assert settings.batch_imported_count == 3

print("batch blend append test passed")
