"""Real native Cycles regression: saved masks, misses, reversals, rollback, swizzle."""
import json
from math import pi
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
from polygroups_generator.operators import baking
from polygroups_generator.core.bake_projection import (ProjectionSession, invalidate, current_mask, pixels, save_mask_png, META_PROP, RUN_PROP)
from polygroups_generator.core.bake_artifact_mask import classify, canonical_z, conservative_resize

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2)
low = bpy.context.object
low.name = 'Projection Low'
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -.2))
high = bpy.context.object
high.name = 'Projection High'
source_mat = bpy.data.materials.new('Original high material')
source_mat.use_nodes = True
high.data.materials.append(source_mat)
settings = bpy.context.scene.polygroups_baking_settings
settings.bake_resolution = 64
settings.bake_margin = 4
settings.bake_base_color = False
settings.bake_normal = True
settings.bake_artifact_mask = True
settings.bake_artifact_radius = 2
settings.use_auto_cage = False
settings.autogenerate_smart_cage = False
settings.auto_pack_uv_before_bake = False
settings.auto_save_textures_after_bake = False
settings.disable_highpoly_after_bake = False
settings.use_selected_to_active = True
settings.cage_extrusion = .1
settings.ray_distance = 1
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 1
scene.cycles.device = 'CPU'


def select():
    baking._select_sources_and_target(bpy.context, [high], low)


def bake_case(name, z, angle, modal=False):
    high.location.z = z
    high.rotation_euler.x = angle
    bpy.context.view_layer.update()
    select()
    result = (bpy.ops.object.polygroups_bake_task(prepare_materials=True) if modal
              else bpy.ops.object.polygroups_bake_selected_to_active())
    assert result == {'FINISHED'}, (name, result)
    normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
    image = current_mask(low, normal)
    assert image is not None, name
    meta = json.loads(image[META_PROP])
    assert tuple(image.size) == tuple(normal.size) == (64, 64)
    data = pixels(image)
    assert np.all(data[..., 3] == 1)
    assert np.all((data[..., :3] == 0) | (data[..., :3] == 1))
    assert high.active_material == source_mat
    assert high.material_slots[0].link == 'DATA'
    assert scene.render.bake.margin == settings.bake_margin
    assert not [m for m in bpy.data.materials if m.name.startswith('Projection diagnostic')]
    assert not [i for i in bpy.data.images if i.name.startswith('Projection private')]
    center = data[32, 32, 0]
    assert center == (0 if name == 'valid' else 1), (name, center, meta)
    if name == 'reversed':
        assert meta['reversed'] > 0 and meta['misses'] == 0
    if name == 'miss':
        assert meta['misses'] > 0 and meta['reversed'] == 0
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / 'ArtifactMask.png')
        save_mask_png(image, path)
        saved = bpy.data.images.load(path, check_existing=False)
        saved.colorspace_settings.name = 'Non-Color'
        assert np.array_equal(pixels(saved), data)
        bpy.data.images.remove(saved)
        assert json.loads(Path(path + '.json').read_text())['run'] == low[RUN_PROP]
    print('PROJECTION_CASE_OK', name, meta['reversed'], meta['misses'], flush=True)
    return image


bake_case('valid', -.2, 0)
bake_case('reversed', -.2, pi)
bake_case('miss', .2, 0, modal=True)
# Negative Z mapped to another channel must still be detected.
scene.render.bake.normal_r = 'NEG_Z'
scene.render.bake.normal_b = 'POS_X'
bake_case('reversed', -.2, pi)
scene.render.bake.normal_r = 'POS_X'
scene.render.bake.normal_b = 'POS_Z'
# Private normal pass when only color is requested.
settings.bake_normal = False
settings.bake_base_color = True
bake_case('reversed', -.2, pi, modal=True)
settings.bake_normal = True
settings.bake_base_color = False

# Failure after a material override must restore slots, nodes, bake settings, selection.
select()
normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
invalidate(low)
baking._configure_bake_settings(bpy.context, settings, 'NORMAL')
session = ProjectionSession(bpy.context, low, [high], settings, normal)
original_active = low.active_material.node_tree.nodes.active
try:
    session.prepare('HIT')
    assert high.active_material != source_mat
    high.location.x += .1
    bpy.context.view_layer.update()
    try:
        session.validate()
        raise AssertionError('Changed geometry accepted')
    except ValueError:
        pass
finally:
    session.close()
    high.location.x -= .1
assert high.active_material == source_mat
assert low.active_material.node_tree.nodes.active == original_active
assert bpy.context.active_object == low and high.select_get()
assert current_mask(low, normal) is None

# Mathematical border/ownership containment and single-pixel downsampling.
z = np.ones((16, 16), np.float32)
z[4:8, 4:8] = .02
z[5, 5] = -1
hit = np.ones(z.shape, bool)
hit[12, 12] = False
domain = np.ones(z.shape, bool)
owners = np.ones(z.shape, np.int32)
owners[:, 8:] = 2
reason = classify(z, hit, domain, owners, radius=2)
assert np.all(reason[4:8, 4:8] != 0)
assert reason[12, 12] & 2
assert reason[5, 8] == 0
single = np.zeros((64, 64), bool)
single[31, 31] = True
assert conservative_resize(single, 16).any()
assert canonical_z(np.array([[[1, .5, .5]]]), ('NEG_Z', 'POS_Y', 'POS_X'))[0, 0] < -.99
print('PROJECTION_ARTIFACT_MASK_OK', flush=True)
