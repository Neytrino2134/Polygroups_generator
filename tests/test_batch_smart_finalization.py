"""Blender regression for batch finalization and newest-Retopo decimation."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import batch_import, import_queue
from polygroups_generator.operators.smart_decimate import latest_generated_retopo
from polygroups_generator.operators.smart_lods import _triangle_count
from polygroups_generator import ui

settings = bpy.context.scene.polygroups_model_preparation_settings
final = bpy.context.scene.polygroups_mesh_finalization_settings
assert settings.batch_smart_decimate_triangle_limit == 3000
assert settings.bl_rna.properties['batch_smart_decimate_triangle_limit'].step == 1000
settings.batch_smart_decimate_enabled = True
assert not settings.batch_smart_lods_enabled
settings.batch_smart_lods_enabled = True
assert not settings.batch_smart_decimate_enabled
settings.batch_smart_decimate_enabled = True
assert not settings.batch_smart_lods_enabled
settings.batch_expanded_stages = 0
for number in (11, 12):
    assert bpy.ops.object.polygroups_toggle_batch_stage(stage=number) == {'FINISHED'}
assert settings.batch_expanded_stages == (1 << 10) | (1 << 11)

assert settings.batch_smart_lods_count == final.smart_lods_count == 5
for group, prefix in ((settings, 'batch_smart_lods'), (final, 'smart_lods')):
    assert [getattr(group, f'{prefix}_target_{i}') for i in range(1, 6)] == [3000, 1500, 1000, 500, 150]

# Use real seam-aware operators while avoiding the external Quad Remesher engine.
settings.batch_save_generated_separately = True
settings.batch_auto_save = False
settings.batch_separate_collections = True
settings.batch_auto_arrange_objects = False
settings.batch_apply_weld = False
for name in ('batch_stage_2_enabled', 'batch_stage_3_enabled', 'batch_stage_4_enabled',
             'batch_stage_5_enabled', 'batch_narrow_island_enabled', 'batch_small_islands_enabled',
             'batch_second_narrow_island_enabled', 'batch_second_small_islands_enabled',
             'batch_autobake_enabled'):
    setattr(settings, name, False)


def fake_import(filepath):
    count = 2 if 'lods' in filepath else 1
    for _ in range(count):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        obj = bpy.context.object
        if 'bad' not in filepath:
            for edge in obj.data.edges:
                edge.use_seam = all(abs(obj.data.vertices[i].co.y) < 1e-5 for i in edge.vertices)
    return {'FINISHED'}


def run(files):
    queue = import_queue.ImportQueue(bpy.context, files, False, lambda level, message: None)
    queue.begin()
    with patch.object(batch_import, 'find_import_operator', return_value=fake_import):
        for _step in range(150):
            queue.step(bpy.context)
            if queue.finished:
                break
    assert queue.finished
    records = json.loads((queue.batch_report.directory / 'files.json').read_text())
    return queue, records


with tempfile.TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'Batch.blend'))
    settings.batch_smart_decimate_triangle_limit = 200
    queue, records = run([str(Path(directory) / 'bad.obj'), str(Path(directory) / 'good.obj')])
    assert settings.batch_failed_count == settings.batch_imported_count == 1
    assert records[0]['failed_stage'] == 'SMART_DECIMATE' and records[0]['failed_pass'] == 11
    assert records[1]['output_tris'] <= 200 < records[1]['input_tris']
    with bpy.data.libraries.load(records[1]['output_file']) as (source, _target):
        assert len([name for name in source.collections if name.startswith('Generated.')]) == 1

    settings.batch_stage_2_enabled = True
    settings.batch_auto_remesh = False
    settings.batch_auto_smart_uv_project = False
    settings.batch_first_remove_small_loose_parts = False
    settings.batch_first_uv_repair_enabled = False
    settings.batch_smart_lods_enabled = True
    settings.batch_smart_lods_count = 5
    settings.batch_smart_lods_target_1 = 150
    settings.batch_smart_lods_target_2 = 80
    settings.batch_smart_lods_target_3 = 60
    settings.batch_smart_lods_target_4 = 40
    settings.batch_smart_lods_target_5 = 20
    settings.batch_smart_lods_final_decimate = True
    settings.batch_smart_lods_triangulate_all = True
    original_final = {name: getattr(final, name) for name in (
        'smart_lods_count', 'smart_lods_target_1', 'smart_lods_target_2',
        'smart_lods_target_3', 'smart_lods_target_4', 'smart_lods_target_5',
        'smart_lods_final_decimate', 'smart_lods_triangulate_all', 'smart_lods_auto_arrange')}
    queue, records = run([str(Path(directory) / 'lods.obj')])
    assert settings.batch_failed_count == 0 and settings.batch_imported_count == 1
    assert len(records[0]['finalization']) == 2  # Both source meshes finish exactly once.
    assert all(len(record['lods']) == 5 for record in records[0]['finalization'])
    assert original_final == {name: getattr(final, name) for name in original_final}
    for record in records[0]['finalization']:
        assert record['lods'][0]['output_tris'] <= 150
        assert record['lods'][1]['output_tris'] <= 80
        assert record['lods'][4]['output_tris'] <= 20
    # Load the saved collection to check applied triangulation and output ownership.
    output = records[0]['output_file']
    with bpy.data.libraries.load(output) as (source, target):
        target.collections = [name for name in source.collections if name.startswith('Generated.')]
    collection = target.collections[0]
    bpy.context.scene.collection.children.link(collection)
    lods = [obj for obj in collection.all_objects if '.LOD.' in obj.name]
    assert len(lods) == 10
    assert all(not obj.modifiers and all(len(poly.vertices) == 3 for poly in obj.data.polygons) for obj in lods)

# Latest-generation selection ignores LODs and decimated copies and reveals hidden assets.
collection = bpy.data.collections.new('Generated.099')
bpy.context.scene.collection.children.link(collection)
objects = []
for name in ('Retopo_Highpoly_Generated.099', 'Retopo_09_Highpoly_Generated.099',
             'Retopo_10_Highpoly_Generated.099', 'Retopo_11_Highpoly_Generated.099.LOD.1',
             'Retopo_12_Highpoly_Generated_SmartDecimated.099', 'Retopo_20_Highpoly_Generated.098'):
    fake_import('good.obj')
    obj = bpy.context.object
    obj.name = name
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    objects.append(obj)
assert latest_generated_retopo(collection) == objects[2]
layer = bpy.context.view_layer.layer_collection.children[collection.name]
sibling = bpy.data.collections.new('Untouched Sibling')
bpy.context.scene.collection.children.link(sibling)
sibling_layer = bpy.context.view_layer.layer_collection.children[sibling.name]
sibling_layer.exclude = True
layer.exclude = True
collection.hide_viewport = True
objects[2].hide_viewport = True
final.smart_decimate_triangle_limit = 200
final.smart_decimate_duplicate_and_apply = False
assert bpy.ops.object.polygroups_smart_decimate_all_generated() == {'FINISHED'}
assert len(objects[2].modifiers) == 2
assert all(not obj.modifiers for obj in objects if obj != objects[2])
assert layer.exclude and collection.hide_viewport and objects[2].hide_viewport
assert sibling_layer.exclude
layer.exclude = False
collection.hide_viewport = False
objects[2].hide_viewport = False
assert _triangle_count(objects[2], bpy.context.evaluated_depsgraph_get()) <= 200
# Show All LOW reveals only the latest original, including its collection path.
for obj in objects:
    obj.hide_viewport = True
objects[2].hide_set(True)
layer.exclude = True
collection.hide_viewport = True
assert bpy.ops.object.polygroups_show_all_low() == {'FINISHED'}
assert not layer.exclude and not collection.hide_viewport
assert not objects[2].hide_viewport and not objects[2].hide_get()
assert all(obj.hide_viewport for obj in objects if obj != objects[2])
assert sibling_layer.exclude

# Both single and all-generated decimation can hide originals, keeping copies visible.
final.smart_decimate_duplicate_and_apply = True
final.smart_decimate_hide_source = True
original_mesh = objects[2].data
assert bpy.ops.object.polygroups_smart_decimate_all_generated() == {'FINISHED'}
assert objects[2].hide_viewport
copies = [obj for obj in bpy.data.objects if obj.get('polygroups_smart_decimated')]
assert copies and all(not obj.hide_viewport for obj in copies)
copy_mesh_names = [obj.data.name for obj in copies]
# An older copy with only the naming suffix also gets removed.
legacy_name = objects[4].name
assert '_SmartDecimated' in legacy_name
assert bpy.ops.object.polygroups_delete_all_decimated() == {'FINISHED'}
assert legacy_name not in bpy.data.objects
assert not any(obj.get('polygroups_smart_decimated') for obj in bpy.data.objects)
assert all(name not in bpy.data.meshes for name in copy_mesh_names)
assert objects[2].data == original_mesh and objects[2].name in bpy.data.objects
assert bpy.ops.object.polygroups_show_all_low() == {'FINISHED'}
assert not objects[2].hide_viewport
# No-seam failures must not hide the original LOW.
fake_import('bad.obj')
no_seams = bpy.context.object
assert bpy.ops.object.polygroups_smart_decimate(duplicate_and_apply=True, hide_source=True) == {'CANCELLED'}
assert not no_seams.hide_viewport
assert bpy.ops.object.polygroups_delete_all_decimated() == {'FINISHED'}

probe = ui._probe_panel(ui.VIEW3D_PT_polygroups_batch_import, bpy.context, 'Smart Decimate')
assert probe.section_match
print('BATCH_SMART_FINALIZATION_OK')
