"""Real Batch AutoBake handoff, exported PNG and separate blend reopen."""
import json
from pathlib import Path
import sys
import tempfile
import addon_utils
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import import_queue, baking
from polygroups_generator.core.bake_projection import pixels, current_mask, META_PROP

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
collection = bpy.data.collections.new('Generated.001')
bpy.context.scene.collection.children.link(collection)
def plane(name, size, z):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0,0,z))
    obj = bpy.context.object
    obj.name = name
    for original in list(obj.users_collection):
        original.objects.unlink(obj)
    collection.objects.link(obj)
    return obj
high = plane('Highpoly_Generated.001', 4, -.2)
high.rotation_euler.x = 3.141592653589793
low = plane('Retopo_03_Highpoly_Generated.001', 2, 0)
scene = bpy.context.scene
settings = scene.polygroups_baking_settings
settings.bake_resolution = 64
settings.bake_base_color = False
settings.bake_normal = True
settings.auto_pack_uv_before_bake = False
settings.disable_highpoly_after_bake = False
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
scene.polygroups_model_preparation_settings.batch_autobake_cage_mode = 'AUTO'
with tempfile.TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'batch.blend'))
    queue = import_queue.ImportQueue(bpy.context, [], False, lambda *_args: None)
    queue.file_objects = [high, low]
    queue.start_auto_bake(bpy.context, low)
    assert settings.bake_task_stage == 'DONE', settings.bake_task_message
    normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
    image = current_mask(low, normal)
    assert image is not None
    assert json.loads(image[META_PROP])['reversed'] == 4096
    paths = list(Path(directory).rglob('*_Bake_ArtifactMask.png'))
    assert len(paths) == 1
    saved = bpy.data.images.load(str(paths[0]), check_existing=False)
    saved.colorspace_settings.name = 'Non-Color'
    assert np.all(pixels(saved) == 1)
    bpy.data.images.remove(saved)
    queue.collect_bake_created()
    queue.restore_bake_settings()
    separate = Path(directory) / 'separate.blend'
    import_queue.write_collection_blend(str(separate), collection)
    bpy.ops.wm.open_mainfile(filepath=str(separate))
    low = bpy.data.objects['Retopo_03_Highpoly_Generated.001']
    normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
    assert current_mask(low, normal) is not None
    assert not bpy.context.scene.polygroups_baking_settings.bake_task_is_running
print('PROJECTION_BATCH_REOPEN_OK', flush=True)
