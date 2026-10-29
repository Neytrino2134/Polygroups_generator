"""HIGH/LOD filters through Scan Queue and actual modal multiview rendering."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import render_queue as rq
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator import ui

scene = bpy.context.scene
s = scene.polygroups_render_settings
assert bpy.ops.render.polygroups_prepare_studio() == {'FINISHED'}
roots = [getattr(s, 'studio_' + role + '_position') for role in ('camera', 'light', 'scene')]
for index, root in enumerate(roots):
    root.location = (index + 1, -2, 3)
bpy.context.view_layer.update()
studio_matrices = [root.matrix_world.copy() for root in roots]
unrelated = bpy.data.objects['Cube']
unrelated.hide_render = False
collection = bpy.data.collections.new('RenderLOD_19_01_Collection')
scene.collection.children.link(collection)
objects = {}
for suffix in ('LOW', 'MID', 'High', *(f'LOD{i}' for i in range(6))):
    bpy.ops.mesh.primitive_cube_add(size=.4)
    obj = bpy.context.object
    obj.name = 'SM_RenderLOD_19_01_' + suffix
    for previous in list(obj.users_collection):
        previous.objects.unlink(obj)
    collection.objects.link(obj)
    objects[suffix.upper()] = obj
    obj.location = (len(objects) * 7, 4, 2)
s.render_low = s.render_mid = False
s.render_high = True
s.render_lod_enabled = True
s.render_lod_level = 'LOD0'
s.multiview_render = True
s.multiview_render_hero = True
s.render_engine = 'EEVEE'
s.max_samples = 1
s.resolution_x = s.resolution_y = 16
s.resolution_scale = 100
s.transparent_background = False
s.freestyle_as_render_pass = False
scene.camera = bpy.data.objects['Camera']
scene.camera.location = (0, -5, 2)
scene.camera.rotation_euler = (-scene.camera.location).to_track_quat('-Z', 'Y').to_euler()
model = capture(bpy.context, ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_render))
assert not model.errors, model.errors
for prop in ('render_high', 'render_lod_enabled', 'render_lod_level'):
    assert any(b[0] == 'property' and b[2] == prop for b in model.bindings.values()), prop
original_render = rq._render_current_job
def checked_render(context, settings, job):
    source = bpy.data.objects[job['object']]
    views = [obj for obj in scene.objects if obj.get(rq.MULTIVIEW_PROP)
             and obj.get(rq.MULTIVIEW_SOURCE_PROP) == source.name]
    front = next((obj for obj in views if obj.name.endswith('_MV_Front')), source)
    assert all((root.matrix_world.translation - front.matrix_world.translation).length < 1e-5 for root in roots)
    assert unrelated.hide_render and unrelated.hide_viewport
    assert not s.studio_backdrop.hide_render
    assert all(obj.hide_render for obj in objects.values() if obj != source)
    return original_render(context, settings, job)
rq._render_current_job = checked_render
with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'Render.blend'))
    s.output_directory = str(Path(directory) / 'Filters')
    for i in range(6):
        s.render_lod_level = f'LOD{i}'
        queue, count = rq._scan_render_queue(s)
        assert count == 1 and len(queue) == 4
        assert {job['variant'] for job in queue} == {'HIGH', f'LOD{i}'}
        lod_jobs = [job for job in queue if job['variant'].startswith('LOD')]
        assert all(Path(job['output_path']).stem.endswith('_LOW') for job in lod_jobs)
        assert len({job['output_path'] for job in queue}) == len(queue)
        assert rq._lod_low_conflicts(queue)
    s.render_low = True
    assert not s.render_lod_enabled
    assert {j['variant'] for j in rq._scan_render_queue(s)[0]} == {'HIGH', 'LOW'}
    s.render_lod_enabled = True
    assert not s.render_low
    # Custom editable High suffix remains recognized from rename metadata.
    high = objects['HIGH']
    high.name = 'SM_RenderLOD_19_01_Original'
    high['unreal_lod_asset'] = 'RenderLOD_19_01'
    high['unreal_lod_index'] = -1
    assert rq._render_object_suffix(high) == 'HIGH'
    high.name = 'SM_RenderLOD_19_01_HIGH'
    s.render_lod_level = 'LOD0'
    for freestyle in (False, True):
        s.freestyle_edges = freestyle
        s.output_directory = str(Path(directory) / str(freestyle))
        assert bpy.ops.object.polygroups_scan_render_queue() == {'FINISHED'}
        queue = rq._load_queue(s)
        assert len(queue) == 4 and {j['variant'] for j in queue} == {'HIGH', 'LOD0'}
        assert {j['view_mode'] for j in queue} == {'Multiview', 'Hero'}
        assert bpy.ops.object.polygroups_start_render_queue('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
        task = rq._ACTIVE_QUEUE_TASK
        for _ in range(len(queue)):
            assert task.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'RUNNING_MODAL'}, s.status
        assert task.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'FINISHED'}
        assert not s.is_running and s.queue_index == 4
        assert all(Path(j['output_path']).is_file() for j in queue)
        assert all(root.matrix_world == matrix for root, matrix in zip(roots, studio_matrices))
        assert not unrelated.hide_render and not unrelated.hide_viewport
        # Scan must not pick up the multiview duplicates created by rendering.
        assert len(rq._scan_render_queue(s)[0]) == 4
    # Clear Freestyle After Render (default on) removes the queue's marks at the end.
    assert s.clear_freestyle_after_render
    assert not any(item.value for key in ('HIGH', 'LOD0') for item in objects[key].data.attributes['freestyle_edge'].data)
    assert objects['LOD1'].data.attributes.get('freestyle_edge') is None
    s.multiview_render = False
    s.freestyle_edges = False
    s.output_directory = str(Path(directory) / 'Single')
    assert bpy.ops.object.polygroups_start_render_queue('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    task = rq._ACTIVE_QUEUE_TASK
    queue = rq._load_queue(s)
    assert len(queue) == 2
    for _ in queue:
        assert task.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'RUNNING_MODAL'}
    assert task.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'FINISHED'}
    assert all(Path(j['output_path']).is_file() for j in queue)
    assert all(root.matrix_world == matrix for root, matrix in zip(roots, studio_matrices))
    # Stopping after one completed job also restores the original visibility.
    s.output_directory = str(Path(directory) / 'Stopped')
    assert bpy.ops.object.polygroups_start_render_queue('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    task = rq._ACTIVE_QUEUE_TASK
    assert task.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'RUNNING_MODAL'}
    s.stop_requested = True
    assert task.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'CANCELLED'}
    assert not unrelated.hide_render and not unrelated.hide_viewport
    assert all(root.matrix_world == matrix for root, matrix in zip(roots, studio_matrices))
    # A failed render must restore both studio transforms and unrelated meshes.
    def failed_render(context, settings, job):
        assert unrelated.hide_render
        raise RuntimeError('intentional positioning recovery test')
    rq._render_current_job = failed_render
    s.output_directory = str(Path(directory) / 'Failure')
    assert bpy.ops.object.polygroups_start_render_queue('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    assert rq._ACTIVE_QUEUE_TASK.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'CANCELLED'}
    assert all(root.matrix_world == matrix for root, matrix in zip(roots, studio_matrices))
    assert not unrelated.hide_render and not unrelated.hide_viewport
    rq._render_current_job = original_render
print('RENDER_HIGH_LOD_QUEUE_PASSED')
