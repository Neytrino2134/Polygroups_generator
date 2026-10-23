"""Native blend scan/append/name repair, queue handoff and real Phase 2 bake."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators import phase2_processing as phase2, safety_checks, baking
from polygroups_generator.custom_ui.schema import capture, walk

context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
bake = context.scene.polygroups_baking_settings
assert settings.phase2_auto_bake and settings.phase2_repair_artifacts
assert bake.bake_artifact_mask and bake.bake_artifact_autofill


def mesh(collection, name, z=0):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(-1, -1, z), (1, -1, z), (1, 1, z), (-1, 1, z)], [], [(0, 1, 2, 3)])
    uv = data.uv_layers.new()
    for loop, xy in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = xy
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    return obj


def source_file(path, stages=(2, 2, 12), name='Generated.007'):
    col = bpy.data.collections.new(name)
    mesh(col, 'Highpoly_Generated.099', .05)
    for stage in stages:
        mesh(col, f'Retopo_{stage:02d}_Highpoly_Generated.099')
    bpy.data.libraries.write(str(path), {col})
    for obj in list(col.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(data)
    bpy.data.collections.remove(col)


def run(queue):
    queue.begin()
    for _ in range(100):
        queue.step(context)
        if queue.finished:
            return
    raise AssertionError((queue.stage, queue.index))


with TemporaryDirectory() as directory:
    root = Path(directory)
    working = root / 'Working.blend'
    existing = bpy.data.collections.new('Generated.001')
    context.scene.collection.children.link(existing)
    original = mesh(existing, 'Highpoly_Generated.001')
    bpy.ops.wm.save_as_mainfile(filepath=str(working))
    separated = root / 'Working_Generated_007.blend'
    source_file(separated)
    subfolder = root / 'nested'
    subfolder.mkdir()
    source_file(subfolder / 'Other.blend', stages=(4,), name='Generated.007.001')
    source_file(root / 'Unrelated.blend', stages=(1,))
    (root / 'Ignored.blend1').write_text('not a blend')

    before = set(bpy.data.objects), set(bpy.data.collections)
    files, entries, errors = phase2.scan_separated_files(str(working))
    assert len(files) == len(entries) == 1 and not errors
    assert before == (set(bpy.data.objects), set(bpy.data.collections))
    files_all, entries_all, errors = phase2.scan_separated_files(str(working), True)
    assert len(files_all) == len(entries_all) == 3 and not errors
    assert str(working).lower() not in [path.lower() for path in files_all]

    # Appending twice must retain the old data and allocate consecutive free N.
    imported = phase2.restore_collection(*entries[0], context.scene)
    assert imported.name == 'Generated.002'
    assert set(obj.name for obj in imported.objects) == {
        'Highpoly_Generated.002', 'Retopo_02_Highpoly_Generated.002',
        'Retopo_03_Highpoly_Generated.002', 'Retopo_12_Highpoly_Generated.002'}
    assert original.name == 'Highpoly_Generated.001'
    assert phase2.bake_pair(imported)[1].name == 'Retopo_12_Highpoly_Generated.002'
    imported2 = phase2.restore_collection(*entries[0], context.scene)
    assert imported2.name == 'Generated.003'
    # An object outside Generated collections also reserves its index.
    other = bpy.data.collections.new('Keep Me')
    context.scene.collection.children.link(other)
    reserved = mesh(other, 'Retopo_77_Highpoly_Generated.004')
    imported3 = phase2.restore_collection(*entries[0], context.scene)
    assert imported3.name == 'Generated.005'
    nested = next(entry for entry in entries_all if Path(entry[0]).parent == subfolder)
    nested_collection = phase2.restore_collection(*nested, context.scene)
    assert nested_collection.name == 'Generated.006'
    assert {obj.name for obj in nested_collection.objects} == {
        'Highpoly_Generated.006', 'Retopo_04_Highpoly_Generated.006'}

    # Clearing Generated trees retains objects also linked to a normal collection.
    other.objects.link(original)
    settings.phase2_auto_bake = False
    settings.phase2_clear_generated = True
    assert bpy.ops.object.polygroups_phase2_restore() == {'FINISHED'}
    assert original in set(bpy.data.objects) and original in set(other.objects)
    assert reserved in set(bpy.data.objects)
    assert settings.phase2_done_count == 1 and not settings.phase2_is_running
    # Shared/unlinked names are respected even after clearing old collections.
    restored = next(col for col in context.scene.collection.children if col.name.startswith('Generated.'))
    assert restored.name == 'Generated.002' and restored.color_tag == 'COLOR_02'

    # Missing/malformed input never damages existing data.
    before = set(bpy.data.objects), set(bpy.data.collections)
    try:
        phase2.restore_collection(str(separated), 'Generated.999', context.scene)
    except ValueError:
        pass
    else:
        raise AssertionError('Missing collection must fail')
    assert before == (set(bpy.data.objects), set(bpy.data.collections))
    with patch.object(phase2, 'scan', return_value=[]), patch.object(phase2, 'clear_generated_collections') as clear:
        assert bpy.ops.object.polygroups_phase2_restore() == {'CANCELLED'}
        clear.assert_not_called()
    assert before == (set(bpy.data.objects), set(bpy.data.collections))

    # Queue waits for each native bake before restoring the next collection.
    calls = []
    real_bpy = safety_checks.bpy
    def fake_bake(*args, **kwargs):
        calls.append((context.active_object.name, sorted(obj.name for obj in context.selected_objects)))
        assert bake.bake_artifact_mask and bake.bake_artifact_autofill
        assert bake.bake_artifact_mode == 'FULL'
        assert bake.auto_save_textures_after_bake and bake.use_selected_to_active
        bake.bake_task_is_running = True
        bake.bake_task_stage = 'BAKING'
        return {'RUNNING_MODAL'}
    bake.bake_artifact_mask = bake.bake_artifact_autofill = False
    bake.auto_save_textures_after_bake = bake.use_selected_to_active = False
    proxy = SimpleNamespace(app=real_bpy.app, ops=SimpleNamespace(object=SimpleNamespace(polygroups_bake_task=fake_bake)))
    queue = phase2.Phase2Queue(context, entries*2, True, True, lambda *_: None)
    queue.begin()
    with patch.object(safety_checks, 'bpy', proxy):
        queue.step(context)
        queue.step(context)
        assert queue.stage == 'BAKE_WAIT' and len(calls) == 1
        assert calls[0][0].startswith('Retopo_12_') and len(calls[0][1]) == 2
        queue.step(context)
        assert queue.index == 0 and len(calls) == 1
        bake.bake_task_is_running = False
        bake.bake_task_stage = 'DONE'
        completed = queue.collection
        queue.step(context)
        assert queue.index == 1 and completed.color_tag == 'COLOR_02'
        assert not bake.bake_artifact_mask and not bake.bake_artifact_autofill
        queue.step(context)
        queue.step(context)
        failed = queue.collection
        bake.bake_task_is_running = False
        bake.bake_task_stage = 'FAILED'
        bake.bake_task_message = 'injected error'
        queue.step(context)
        queue.step(context)
        assert queue.finished and failed.color_tag == 'COLOR_05'
        assert settings.phase2_done_count == settings.phase2_failed_count == 1

        # Stop must wait for the in-flight bake, retain its success and skip
        # the next restore instead of modifying inputs during the native task.
        queue = phase2.Phase2Queue(context, entries*2, True, True, lambda *_: None)
        queue.begin()
        queue.step(context)
        queue.step(context)
        stopping_collection = queue.collection
        queue.stop_requested = True
        queue.step(context)
        assert not queue.finished and queue.index == 0
        bake.bake_task_is_running = False
        bake.bake_task_stage = 'DONE'
        queue.step(context)
        queue.step(context)
        assert queue.finished and queue.index == 1
        assert settings.phase2_done_count == 1 and settings.phase2_failed_count == 0
        assert stopping_collection.color_tag == 'COLOR_02'

    # Real CPU Cycles normal rebake with full artifact mask + Autofill enabled.
    bake.bake_resolution = 32
    bake.bake_normal = True
    bake.bake_base_color = False
    bake.auto_pack_uv_before_bake = False
    bake.disable_highpoly_after_bake = False
    context.scene.render.engine = 'CYCLES'
    context.scene.cycles.device = 'CPU'
    context.scene.cycles.samples = 1
    settings.phase2_delete_high_after_bake = True
    settings.phase2_delete_lower_retopo = True
    real_queue = phase2.Phase2Queue(context, entries, True, True, lambda *_: None)
    run(real_queue)
    assert settings.phase2_done_count == 1 and settings.phase2_failed_count == 0, real_queue.results
    targets = [obj for obj in bpy.data.objects if obj.name.startswith('Retopo_12_') and obj.get(baking.BAKE_NORMAL_IMAGE_PROP)]
    assert targets
    from polygroups_generator.core.bake_projection import current_mask
    target = targets[-1]
    completed = next(col for col in target.users_collection if phase2.NUMBERED.fullmatch(col.name))
    assert not any(phase2.HIGH.fullmatch(obj.name) for obj in completed.all_objects)
    assert [obj for obj in completed.all_objects if phase2.LOW.fullmatch(obj.name)] == [target]
    assert completed.hide_render and completed.hide_viewport

    normal = bpy.data.images[target[baking.BAKE_NORMAL_IMAGE_PROP]]
    assert current_mask(target, normal) is not None
    assert list(root.rglob('*_Normal.png'))
    assert list(root.rglob('*_Bake_ArtifactMask.png'))

    for language in ('EN', 'RU'):
        context.preferences.addons[ROOT.name].preferences.interface_language = language
        model = capture(context, 1)
        assert not model.errors, model.errors
        groups = [node for node in walk(model.node) if node['kind'] == 'group']
        assert any(node['id'].endswith('.topic_batch_5') for node in groups)
    settings.phase2_scan_subfolders = True
    settings.phase2_clear_generated = settings.phase2_auto_bake = False
    assert bpy.ops.object.polygroups_phase2_restore() == {'FINISHED'}
    assert settings.phase2_done_count == settings.phase2_scanned_files == 3
    assert settings.phase2_failed_count == 0

print('PHASE2_PROCESSING_PASSED', flush=True)
