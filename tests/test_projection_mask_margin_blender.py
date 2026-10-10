"""Native mask padding: inherited margin + extra, UV gutters, save and shared UI."""
from pathlib import Path
import json
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
from polygroups_generator.core.bake_projection import pixels, current_mask, META_PROP, save_mask_png
from polygroups_generator.core.bake_artifact_mask import pad_reasons
from polygroups_generator.custom_ui.schema import capture

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2)
low = bpy.context.object
for item in low.data.uv_layers.active.data:
    item.uv = tuple(float(value) * .5 + .25 for value in item.uv)
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -.2))
high = bpy.context.object
high.rotation_euler.x = 3.141592653589793
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
settings = scene.polygroups_baking_settings
settings.bake_resolution = 64
settings.bake_base_color = False
settings.bake_normal = True
settings.bake_margin = 4
settings.bake_artifact_radius = 2
settings.auto_pack_uv_before_bake = False
settings.use_auto_cage = False
settings.autogenerate_smart_cage = False
settings.disable_highpoly_after_bake = False
settings.auto_save_textures_after_bake = False
settings.cage_extrusion = .1
settings.ray_distance = 1
assert settings.bake_artifact_inherit_margin

def run(margin, inherit, modal=False):
    settings.bake_margin = margin
    settings.bake_artifact_inherit_margin = inherit
    baking._select_sources_and_target(bpy.context, [high], low)
    op = bpy.ops.object.polygroups_bake_task if modal else bpy.ops.object.polygroups_bake_selected_to_active
    assert op() == {'FINISHED'}
    normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
    image = current_mask(low, normal)
    meta = json.loads(image[META_PROP])
    expected = margin + 2 if inherit else 2
    assert meta['radius'] == expected, meta
    assert meta['extra_padding'] == 2 and meta['inherit_margin'] == inherit
    assert meta['inherited_margin'] == (margin if inherit else 0)
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / 'mask.png')
        save_mask_png(image, path)
        saved = bpy.data.images.load(path, check_existing=False)
        saved.colorspace_settings.name = 'Non-Color'
        actual = pixels(saved)[..., 0] > .5
        assert np.array_equal(actual, pixels(image)[..., 0] > .5)
        bpy.data.images.remove(saved)
    return actual

unpadded = run(0, False)
settings.bake_artifact_radius = 0
baking._select_sources_and_target(bpy.context, [high], low)
assert bpy.ops.object.polygroups_bake_selected_to_active() == {'FINISHED'}
core = pixels(current_mask(low, bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]))[..., 0] > .5
settings.bake_artifact_radius = 2
six = run(4, True, modal=True)
eight = run(6, True)
two = run(6, False)
assert np.array_equal(unpadded, two)
cy, cx = np.nonzero(core)
for output, radius in ((six, 6), (eight, 8), (two, 2)):
    yy, xx = np.nonzero(output)
    assert (xx.min(), xx.max(), yy.min(), yy.max()) == (cx.min()-radius, cx.max()+radius, cy.min()-radius, cy.max()+radius)
    assert np.all(output[cy.min()-radius:cy.max()+radius+1, cx.min()-radius:cx.max()+radius+1])
    assert not np.any(core & ~output)
print('NATIVE_MARGIN_MASK_OK: 4+2=6, 6+2=8, disabled=2; PNG exact', flush=True)

# Neighboring unaffected islands must not receive padding; equidistant gutter ties stay black.
owners = np.zeros((32, 32), np.int32)
owners[12:20, 8:12] = 1
owners[12:20, 16:20] = 2
domain = owners > 0
reasons = np.zeros(owners.shape, np.uint8)
reasons[14:18, 10:12] = 1
output = pad_reasons(reasons, domain, owners, 6)
assert not np.any(output[owners == 2])
assert output[15, 12] and not output[15, 15]

# Same captured layout serves Custom and UI Panel; native panel draws these same props.
settings.bake_artifact_inherit_margin = True
settings.bake_margin = 4
model = capture(bpy.context, 9)
assert not model.errors, model.errors
assert any(binding[0] == 'property' and binding[2] == 'bake_artifact_inherit_margin' for binding in model.bindings.values())
assert any(binding[0] == 'property' and binding[2] == 'bake_artifact_radius' for binding in model.bindings.values())
print('PROJECTION_MARGIN_TESTS_OK', flush=True)
