"""Real native Cycles regression: saved masks, misses, reversals, rollback, swizzle."""
import json
import os
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
from polygroups_generator.core.bake_projection import uv_ownership
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
    baking._select_sources_and_target(bpy.context, [high, *extra_sources], low)


extra_sources = []


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

# Mixed good hits and misses: the mask covers the missing half, leaving valid normals black.
high.rotation_euler.x = 0
high.location.x = 2
high.location.z = -.2
select()
assert bpy.ops.object.polygroups_prepare_and_bake() == {'FINISHED'}
normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
data = pixels(current_mask(low, normal))
assert np.all(data[4:-4, 4:28, 0] == 1)
assert np.all(data[4:-4, 38:-4, 0] == 0)
if os.environ.get('AIRETOPO_MASK_VALIDATION_OUTPUT'):
    directory = Path(os.environ['AIRETOPO_MASK_VALIDATION_OUTPUT'])
    directory.mkdir(parents=True, exist_ok=True)
    baking._save_image_as_png(normal, str(directory / 'partial-normal.png'))
    save_mask_png(current_mask(low, normal), str(directory / 'partial-mask.png'))
high.location.x = 0

# Multiple sources: nearest native ray hit wins, independent of source list order.
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -.1))
nearest = bpy.context.object
extra_sources.append(nearest)
bake_case('valid', -.2, pi)
nearest.rotation_euler.x = pi
bake_case('reversed', -.2, 0)
extra_sources.clear()
bpy.data.objects.remove(nearest, do_unlink=True)

# Cage origin entirely inside a closed high mesh: no boundary intersection required.
bpy.ops.mesh.primitive_cube_add(size=4)
enclosing = bpy.context.object
extra_sources.append(enclosing)
settings.ray_distance = 3
bake_case('reversed', 5, 0)
extra_sources.clear()
bpy.data.objects.remove(enclosing, do_unlink=True)

# Legitimate near-tangent normal region must not seed an artifact by itself.
high.scale = (100, 100, 1)
settings.ray_distance = 0
settings.cage_extrusion = 200
bake_case('valid', -.2, pi/2-.01)
high.scale = (1, 1, 1)
settings.ray_distance = 1
settings.cage_extrusion = .1

# Custom shading normals are taken from the actual normal bake, not face winding.
high.data.normals_split_custom_set([(0, 0, -1)] * len(high.data.loops))
bake_case('reversed', -.2, 0)
high.data.normals_split_custom_set([(0, 0, 1)] * len(high.data.loops))

# Explicit cage and mirrored/nonuniform transforms use the same native projection.
high.rotation_euler.x = pi
high.location.z = -.2
low.scale = (1.5, .75, 1)
high.scale = (2, 2, 1)
bpy.context.view_layer.update()
cage = low.copy()
cage.data = low.data.copy()
bpy.context.collection.objects.link(cage)
cage.location.z = .1
settings.smart_cage_object = cage
settings.autogenerate_smart_cage = True
select()
material, base, node = baking._ensure_bake_material(low, settings)
low.active_material = material
invalidate(low)
baking._bake_to_node(bpy.context, low, node, 'NORMAL', settings)
image, meta = baking._generate_bake_artifact_mask(bpy.context, low, [high], settings)
assert meta['cage'] == cage.name and meta['reversed'] > 0 and meta['misses'] == 0
settings.autogenerate_smart_cage = False
settings.smart_cage_object = None
bpy.data.objects.remove(cage, do_unlink=True)
low.scale = (1, 1, 1)
high.scale = (1, 1, 1)

low.scale = (-1.5, .75, 1)
high.scale = (-2, 2, 1)
for obj in (low, high):
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
bake_case('reversed', -.2, pi)
low.scale = (1, 1, 1)
high.scale = (1, 1, 1)

# Fast mode intentionally does not promise ray-miss coverage.
settings.bake_artifact_mode = 'NORMAL_ONLY'
image = bake_case('valid', .2, 0)
assert json.loads(image[META_PROP])['misses'] == 0
settings.bake_artifact_mode = 'FULL'

# Manual downsampling remains binary and keeps detected defects.
settings.bake_artifact_match_normal = False
settings.bake_artifact_resolution = 16
high.location.z = .2
select()
assert bpy.ops.object.polygroups_bake_selected_to_active() == {'FINISHED'}
assert tuple(bpy.data.images[low[baking.BAKE_ARTIFACT_IMAGE_PROP]].size) == (16, 16)
settings.bake_artifact_match_normal = True

# Stale masks and externally edited normal images are rejected before export.
image = bake_case('reversed', -.2, pi)
normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
values = pixels(normal)
values[0, 0, 0] = 0
normal.pixels.foreach_set(values.ravel())
normal.update()
try:
    current_mask(low, normal)
    raise AssertionError('Edited normal was accepted')
except ValueError:
    pass

# Failed disk verification preserves an existing PNG and restores image path/format.
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'preserved.png'
    path.write_bytes(b'previous-output')
    previous = image.filepath_raw, image.file_format
    values = pixels(image)
    values[0, 0, 3] = 0
    image.pixels.foreach_set(values.ravel())
    try:
        save_mask_png(image, str(path))
        raise AssertionError('Non-opaque mask saved')
    except ValueError:
        pass
    assert path.read_bytes() == b'previous-output'
    assert (image.filepath_raw, image.file_format) == previous

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

# Object-linked and data-linked slots, including shared source material, restore exactly.
second = source_mat.copy()
low.data.materials.append(second)
high.data.materials.append(second)
before_slots = [(o, o.active_material_index, [(s.link, s.material) for s in o.material_slots]) for o in (low, high)]
session = ProjectionSession(bpy.context, low, [high], settings, normal)
session.prepare('HIT')
assert all(slot.material not in (source_mat, second) for slot in high.material_slots)
session.close()
for obj, index, slots in before_slots:
    assert obj.active_material_index == index
    assert [(s.link, s.material) for s in obj.material_slots] == slots

# Displacement graph is kept when the diagnostic replaces Surface with emission.
output = next(n for n in source_mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
displace = source_mat.node_tree.nodes.new('ShaderNodeDisplacement')
source_mat.node_tree.links.new(displace.outputs[0], output.inputs['Displacement'])
session = ProjectionSession(bpy.context, low, [high], settings, normal)
session.prepare('HIT')
temporary_output = next(n for n in high.active_material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
assert temporary_output.inputs['Displacement'].is_linked
session.close()
assert output.inputs['Displacement'].is_linked

# Native cancel notification is honored even when Esc did not reach the outer modal.
handler_count = len(bpy.app.handlers.object_bake_cancel)
session = ProjectionSession(bpy.context, low, [high], settings, normal)
session.prepare('HIT')
for handler in list(session.handlers):
    handler(low)
try:
    session.complete()
    raise AssertionError('Cancelled native pass accepted')
except RuntimeError:
    pass
session.close()
assert len(bpy.app.handlers.object_bake_cancel) == handler_count

# UDIM is rejected explicitly rather than producing a black success result.
uv = low.data.uv_layers.active.data[0]
previous_uv = tuple(uv.uv)
uv.uv.x += 2
bpy.context.view_layer.update()
try:
    ProjectionSession(bpy.context, low, [high], settings, normal)
    raise AssertionError('UDIM UV accepted')
except ValueError as error:
    assert 'UDIM' in str(error)
uv.uv = previous_uv
bpy.context.view_layer.update()

# Two unrelated UV islands at the same coordinates must be reported as ambiguous.
mesh = bpy.data.meshes.new('Overlap fixture')
mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0),(2,0,0),(3,0,0),(3,1,0),(2,1,0)], [], [(0,1,2,3),(4,5,6,7)])
uvs = mesh.uv_layers.new()
for i, value in enumerate(((0,0),(1,0),(1,1),(0,1))*2):
    uvs.data[i].uv = value
overlap = bpy.data.objects.new('Overlap fixture', mesh)
bpy.context.collection.objects.link(overlap)
bpy.context.view_layer.update()
assert np.count_nonzero(uv_ownership(bpy.context, overlap, 32, 32) == -1) > 900
bpy.data.objects.remove(overlap, do_unlink=True)

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
