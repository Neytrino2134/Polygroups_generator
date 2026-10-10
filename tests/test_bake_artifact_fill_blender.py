"""Pure fill fixtures and actual native bake/save acceptance in Blender."""
import json
import sys
import tempfile
from pathlib import Path
import addon_utils
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core.bake_artifact_fill import fill_region
from polygroups_generator.core.bake_autofill import AutofillPlan
from polygroups_generator.core.bake_projection import pixels, current_mask, META_PROP
from polygroups_generator.operators import baking
from polygroups_generator.custom_ui.schema import capture

mask = np.zeros((24, 24), bool)
mask[6:18, 6:18] = True
owners = np.ones(mask.shape, np.int32)
rgba = np.ones((*mask.shape, 4), np.float32)
rgba[..., :3] = (.2, .4, .7)
rgba[mask] = (1, 0, 0, 0)
result, filled, counts = fill_region(rgba, mask, owners, ~mask)
assert np.array_equal(result[~mask], rgba[~mask])
assert np.allclose(result[mask], (.2, .4, .7, 1))
assert np.array_equal(filled, mask) and counts['waves'] == 6
# Gaussian radius affects synthesized pixels only, with no directional bias.
rgba[..., 0] = np.indices(mask.shape)[1] / 24
sharp, _, _ = fill_region(rgba, mask, owners, ~mask, 0)
blurred, _, _ = fill_region(rgba, mask, owners, ~mask, 2)
assert not np.array_equal(sharp[mask], blurred[mask])
assert np.array_equal(blurred[~mask], rgba[~mask])
mirrored, _, _ = fill_region(rgba[:, ::-1], mask[:, ::-1], owners[:, ::-1], ~mask[:, ::-1])
assert np.allclose(mirrored[:, ::-1], blurred, atol=1e-6)
# Independent islands must not blend even across an adjacent masked boundary.
owners[:, 12:] = 2
rgba[:, :12, :3], rgba[:, 12:, :3] = (1, 0, 0), (0, 0, 1)
result, _, _ = fill_region(rgba, mask, owners, ~mask)
assert np.allclose(result[mask & (owners == 1), :3], (1, 0, 0))
assert np.allclose(result[mask & (owners == 2), :3], (0, 0, 1))
all_white = np.ones(mask.shape, bool)
result, filled, counts = fill_region(rgba, all_white, owners, ~all_white)
assert np.array_equal(result, rgba) and counts['filled'] == 0 and not filled.any()
owners[mask] = -1
result, filled, _ = fill_region(rgba, mask, owners, ~mask)
assert not filled.any() and np.array_equal(result, rgba)
owners[:] = 1
# Opposing healthy vectors need a finite unit fallback, including signed swizzles.
rgba[..., :3] = (.50001, .50001, 1)
rgba[:, 12:, :3] = (.50001, .50001, 0)
result, _, _ = fill_region(rgba, mask, owners, ~mask, normal_swizzle=('POS_X', 'POS_Y', 'NEG_Z'))
lengths = np.linalg.norm((result[..., :3] - .50001) * 2, axis=2)
assert np.isfinite(result).all() and np.allclose(lengths[mask], 1, atol=3e-5)
assert np.array_equal(result[~mask], rgba[~mask])
print('AUTOFILL_ARRAY_FIXTURES_OK', flush=True)

# Half the low plane misses the translated high plane: both maps must be repaired.
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2)
low = bpy.context.object
bpy.ops.mesh.primitive_plane_add(size=4, location=(2, 0, -.2))
high = bpy.context.object
high.rotation_euler.y = .2
mat = bpy.data.materials.new('Autofill colored source')
mat.use_nodes = True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (.2, .4, .7, 1)
high.data.materials.append(mat)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
s = scene.polygroups_baking_settings
assert s.bake_artifact_autofill and s.bake_artifact_autofill_blur == 2
s.bake_resolution = 64
s.bake_margin = 4
s.bake_artifact_radius = 2
s.bake_base_color = s.bake_normal = True
s.bake_background_mode = 'BLACK'
s.use_auto_cage = s.autogenerate_smart_cage = False
s.auto_pack_uv_before_bake = s.auto_save_textures_after_bake = False
s.disable_highpoly_after_bake = False
s.cage_extrusion = .1
s.ray_distance = 1

def bake(enabled, modal=False):
    s.bake_artifact_autofill = enabled
    baking._select_sources_and_target(bpy.context, [high], low)
    op = bpy.ops.object.polygroups_bake_task if modal else bpy.ops.object.polygroups_bake_selected_to_active
    assert op() == {'FINISHED'}
    normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
    image = current_mask(low, normal)
    assert image is not None
    return pixels(image), pixels(normal), pixels(bpy.data.images[low[baking.BAKE_BASE_COLOR_IMAGE_PROP]]), json.loads(image[META_PROP])

raw_mask, raw_normal, raw_base, meta = bake(False)
fixed_mask, normal, base, meta = bake(True)
white = fixed_mask[..., 0] > .5
print('AUTOFILL_DIAGNOSTICS', meta['autofill'], raw_base[white].mean(axis=0), base[white].mean(axis=0), base[~white].mean(axis=0), flush=True)
assert np.array_equal(raw_mask, fixed_mask), 'repair must not change diagnosis'
assert np.array_equal(raw_normal[~white], normal[~white])
assert np.array_equal(raw_base[~white], base[~white])
assert not np.allclose(raw_base[white], base[white])
assert not np.allclose(raw_normal[white], normal[white])
assert np.allclose(base[white, :3], base[~white, :3].mean(axis=0), atol=.01)
assert np.allclose(normal[white, :3], normal[~white, :3].mean(axis=0), atol=.01)
for kind in ('normal', 'base_color'):
    assert meta['autofill']['textures'][kind]['filled'] == np.count_nonzero(white)
    assert meta['autofill']['textures'][kind]['unfilled'] == 0
assert meta['autofill']['blur_radius'] == 2
print('AUTOFILL_NATIVE_SYNC_OK', meta['autofill'], flush=True)
fixed_modal, modal_normal, modal_base, meta = bake(True, modal=True)
assert np.array_equal(fixed_modal, fixed_mask)
assert np.allclose(modal_base, base) and np.allclose(modal_normal, normal)
print('AUTOFILL_NATIVE_TASK_OK', flush=True)

# The smaller prepared output mask controls repair at native texture resolution.
s.bake_artifact_match_normal = False
s.bake_artifact_resolution = 16
small, normal, base, meta = bake(True)
native_white = np.repeat(np.repeat(small[..., 0] > .5, 4, axis=0), 4, axis=1)
assert meta['autofill']['textures']['base_color']['filled'] == np.count_nonzero(native_white)
assert np.allclose(base[native_white, :3], base[~native_white, :3].mean(axis=0), atol=.01)
print('AUTOFILL_MANUAL_MASK_OK', flush=True)

# Actual exported maps contain repaired pixels and normal hash remains valid.
with tempfile.TemporaryDirectory() as folder:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(folder) / 'Autofill.blend'))
    assert bpy.ops.object.polygroups_save_bake_textures() == {'FINISHED'}
    saved = list(Path(folder).rglob('*.png'))
    assert len(saved) >= 4, saved
    for key in (baking.BAKE_NORMAL_IMAGE_PROP, baking.BAKE_BASE_COLOR_IMAGE_PROP):
        texture = bpy.data.images[low[key]]
        loaded = bpy.data.images.load(bpy.path.abspath(texture.filepath), check_existing=False)
        loaded.colorspace_settings.name = texture.colorspace_settings.name
        assert np.allclose(pixels(loaded), pixels(texture), atol=.012)
        bpy.data.images.remove(loaded)
        texture.pack()
    assert current_mask(low, bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]) is not None
print('AUTOFILL_SAVE_OK', flush=True)

# A failed second image write restores the first image, too.
base_image = bpy.data.images[low[baking.BAKE_BASE_COLOR_IMAGE_PROP]]
normal_image = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
alpha_image = bpy.data.images[low[baking.BAKE_ALPHA_IMAGE_PROP]]
baseline = [(image, pixels(image)) for image in (base_image, normal_image, alpha_image)]
plan = AutofillPlan(low, low['polygroups_projection_run'], (slice(0, 64), slice(0, 64)), (64, 64),
    native_white, np.ones((64, 64), np.int32), ~native_white, ('POS_X', 'POS_Y', 'POS_Z'),
    base_image.name, normal_image.name, 2)
real_write = baking._write_pixels
writes = []
def fail_once(image, data):
    writes.append(image.name)
    if len(writes) == 2:
        raise RuntimeError('Injected Autofill write failure')
    return real_write(image, data)
baking._write_pixels = fail_once
try:
    try:
        plan.apply(lambda *args: None)
        raise AssertionError('write failure must propagate')
    except RuntimeError as error:
        assert 'Injected' in str(error)
finally:
    baking._write_pixels = real_write
for image, data in baseline:
    assert np.array_equal(pixels(image), data), image.name
print('AUTOFILL_WRITE_ROLLBACK_OK', flush=True)

# Base-only workflow uses the private normal diagnostic but does not alter a stale normal.
s.bake_normal = False
baking._select_sources_and_target(bpy.context, [high], low)
assert bpy.ops.object.polygroups_bake_selected_to_active() == {'FINISHED'}
image = current_mask(low, None)
assert image is not None
assert set(json.loads(image[META_PROP])['autofill']['textures']) == {'base_color'}
assert np.array_equal(pixels(normal_image), baseline[1][1])
print('AUTOFILL_BASE_ONLY_OK', flush=True)

s.bake_artifact_autofill = True
model = capture(bpy.context, 9)
assert not model.errors, model.errors
for name in ('bake_artifact_autofill', 'bake_artifact_autofill_blur'):
    assert any(binding[0] == 'property' and binding[2] == name for binding in model.bindings.values())
print('AUTOFILL_SHARED_UI_OK', flush=True)

# Interior inverted shading, rather than misses: healthy opposite half repairs both maps.
s.bake_normal = True
s.bake_artifact_match_normal = True
mesh = bpy.data.meshes.new('Mixed reversed projection')
mesh.from_pydata([(-2,-2,-.2), (0,-2,-.2), (0,2,-.2), (-2,2,-.2),
                   (2,-2,-.2), (2,2,-.2)], [], [(3,2,1,0), (1,4,5,2)])
mesh.update()
high.data = mesh
high.location = (0, 0, 0)
high.rotation_euler = (0, 0, 0)
red = bpy.data.materials.new('Reversed red source')
red.use_nodes = True
red.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (.8, .05, .05, 1)
mesh.materials.append(red)
mesh.materials.append(mat)
mesh.polygons[1].material_index = 1
raw_mask, raw_normal, raw_base, raw_meta = bake(False)
fixed_mask, normal, base, meta = bake(True)
white = fixed_mask[..., 0] > .5
assert raw_meta['reversed'] > 0 and raw_meta['misses'] == 0
assert np.array_equal(raw_mask, fixed_mask)
assert np.array_equal(raw_normal[~white], normal[~white])
assert np.array_equal(raw_base[~white], base[~white])
assert raw_normal[32, 8, 2] < .1 and normal[32, 8, 2] > .99
assert not np.allclose(raw_base[white], base[white])
assert np.allclose(base[white, :3], base[~white, :3].mean(axis=0), atol=.01)
print('AUTOFILL_REVERSED_NORMAL_AND_COLOR_OK', flush=True)
