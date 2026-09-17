"""Blender regression and visual preview for the controllable studio rig."""
import sys
import math
import tempfile
from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.render_studio import TAG
from polygroups_generator.properties import SECTION_SUBSECTION_PROPERTIES
from polygroups_generator import ui

scene = bpy.context.scene
settings = scene.polygroups_render_settings
assert 'topic_render_6' in SECTION_SUBSECTION_PROPERTIES['show_render_section']
# Reordering preserves existing selection, per-view-layer hiding and exclusions.
original_active = bpy.context.view_layer.objects.active
original_active.hide_set(True)
old_collection = bpy.data.collections.new('Generated.321')
scene.collection.children.link(old_collection)
old_child = bpy.data.collections.new('Existing child')
old_collection.children.link(old_child)
layer = bpy.context.view_layer.layer_collection.children[old_collection.name]
layer.children[old_child.name].exclude = True
alternate = scene.view_layers.new('Alternate')
alternate.layer_collection.children[old_collection.name].exclude = True
assert settings.studio_collection_color_tag == 'COLOR_08'
original_objects = set(bpy.data.objects)
assert bpy.ops.render.polygroups_prepare_studio() == {'FINISHED'}
assert original_objects <= set(bpy.data.objects)
assert [collection.name for collection in scene.collection.children][:3] == ['Scene_Studio', 'Camera_Studio', 'Light_Studio']
assert bpy.context.view_layer.objects.active == original_active and original_active.hide_get()
assert bpy.context.view_layer.layer_collection.children[old_collection.name].children[old_child.name].exclude
assert alternate.layer_collection.children[old_collection.name].exclude
studio = [collection for collection in scene.collection.children if collection.get(TAG)]
assert all(collection.color_tag == 'COLOR_08' for collection in studio)
settings.studio_collection_color_tag = 'COLOR_03'
assert all(collection.color_tag == 'COLOR_03' for collection in studio)
settings.studio_collection_color_tag = 'NONE'
assert all(collection.color_tag == 'NONE' for collection in studio)
settings.studio_collection_color_tag = 'COLOR_08'

assert scene.camera == settings.studio_camera
assert tuple(scene.camera.location) == (0, -8, 0.5)
assert tuple(settings.studio_camera_aim.location) == (0, 0, 0.5)
assert len([obj for obj in bpy.data.objects if obj.get(TAG)]) == 9
assert {collection.name for collection in scene.collection.children} >= {
    'Scene_Studio', 'Camera_Studio', 'Light_Studio'}
for role in ('camera', 'key', 'fill', 'rim'):
    obj = getattr(settings, 'studio_' + role)
    target = getattr(settings, 'studio_' + role + '_aim')
    constraint = obj.constraints['Studio Aim']
    assert constraint.target == target
    assert constraint.track_axis == 'TRACK_NEGATIVE_Z' and constraint.up_axis == 'UP_Y'
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    direction = (target.location - obj.location).normalized()
    actual = (evaluated.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    assert actual.dot(direction) > 0.9999

# Arrow controls move each controller exactly 0.1m and obey camera axis limits.
assert settings.studio_key.data.energy == settings.studio_fill.data.energy == 50
assert settings.studio_rim.data.energy == 100
for role in ('camera', 'camera_aim', 'key', 'key_aim', 'fill', 'fill_aim', 'rim', 'rim_aim'):
    obj = getattr(settings, 'studio_' + role)
    original = obj.matrix_world.translation.copy()
    for axis in ('YZ' if role.startswith('camera') else 'XYZ'):
        index = 'XYZ'.index(axis)
        assert bpy.ops.render.polygroups_move_studio(target=role, axis=axis, direction='POSITIVE') == {'FINISHED'}
        assert abs(obj.matrix_world.translation[index] - original[index] - 0.1) < 1e-5
        assert bpy.ops.render.polygroups_move_studio(target=role, axis=axis, direction='NEGATIVE') == {'FINISHED'}
        assert (obj.matrix_world.translation - original).length < 1e-5
assert bpy.ops.render.polygroups_move_studio(target='camera', axis='X') == {'CANCELLED'}
assert bpy.ops.render.polygroups_move_studio(target='camera_aim', axis='X') == {'CANCELLED'}
# One shared metre step applies to both objects and Aim controllers.
settings.studio_move_step = 1
for role in ('camera', 'camera_aim', 'key', 'key_aim', 'fill', 'fill_aim', 'rim', 'rim_aim'):
    obj = getattr(settings, 'studio_' + role)
    before = obj.matrix_world.translation.z
    bpy.ops.render.polygroups_move_studio(target=role, axis='Z', direction='POSITIVE')
    assert abs(obj.matrix_world.translation.z - before - 1) < 1e-5
    bpy.ops.render.polygroups_move_studio(target=role, axis='Z', direction='NEGATIVE')
settings.studio_move_step = 0.1

# The step is in metres even in scenes using a different unit scale.
scene.unit_settings.scale_length = 0.01
before = settings.studio_camera.matrix_world.translation.y
assert bpy.ops.render.polygroups_move_studio(target='camera', axis='Y', direction='POSITIVE') == {'FINISHED'}
assert abs(settings.studio_camera.matrix_world.translation.y - before - 10) < 1e-4
bpy.ops.render.polygroups_move_studio(target='camera', axis='Y', direction='NEGATIVE')
scene.unit_settings.scale_length = 1

# The panel remains searchable with all actual rig controls present.
probe = ui._probe_panel(ui.VIEW3D_PT_polygroups_render, bpy.context, 'Scene Setup')
assert probe.section_match
assert any('topic_render_6' in key for key in probe.groups)

# Settings update mesh and shader immediately, including oversized bend radii.
settings.studio_width = 14
settings.studio_distance = 4
settings.studio_radius = 100
settings.studio_color = (0.3, 0.2, 0.1)
mesh = settings.studio_backdrop.data
assert abs(max(v.co.x for v in mesh.vertices) - 7) < 1e-5
assert abs(max(v.co.y for v in mesh.vertices) - 4) < 1e-5
assert all(poly.area > 0 for poly in mesh.polygons)
assert tuple(mesh.materials[0].diffuse_color)[:3] == tuple(settings.studio_color)

# A repeated preparation preserves tuned camera and light parameters.
settings.studio_camera.location.y = -7
settings.studio_key.data.energy = 123
settings.studio_fill.hide_render = True
counts = (len(bpy.data.objects), len(bpy.data.collections), len(bpy.data.materials))
assert bpy.ops.render.polygroups_prepare_studio() == {'FINISHED'}
assert counts == (len(bpy.data.objects), len(bpy.data.collections), len(bpy.data.materials))
assert settings.studio_camera.location.y == -7
assert settings.studio_key.data.energy == 123
assert settings.studio_fill.hide_render

# Deleting a controller is repaired without duplicating its light or constraint.
bpy.data.objects.remove(settings.studio_key_aim, do_unlink=True)
assert bpy.ops.render.polygroups_prepare_studio() == {'FINISHED'}
assert len(settings.studio_key.constraints) == 1
assert settings.studio_key.constraints[0].target == settings.studio_key_aim
assert counts == (len(bpy.data.objects), len(bpy.data.collections), len(bpy.data.materials))

# Palettes change only light colors, retaining tuned power, transforms and visibility.
lights = [settings.studio_key, settings.studio_fill, settings.studio_rim]
snapshot = [(light.matrix_world.copy(), light.data.energy, light.data.size, light.hide_render)
            for light in lights]
backdrop_color = tuple(settings.studio_color)
for preset in ('WARM_COOL', 'COOL_WARM', 'SUNSET', 'CYAN_MAGENTA', 'GOLD_VIOLET', 'NEUTRAL'):
    assert bpy.ops.render.polygroups_studio_light_colors(preset=preset) == {'FINISHED'}
    for light, (matrix, power, size, hidden) in zip(lights, snapshot):
        assert light.matrix_world == matrix
        assert (light.data.energy, light.data.size, light.hide_render) == (power, size, hidden)
        assert all(math.isfinite(channel) and 0 <= channel <= 1 for channel in light.data.color)
    assert tuple(settings.studio_color) == backdrop_color
assert all(tuple(light.data.color) == (1, 1, 1) for light in lights)
bpy.ops.render.polygroups_studio_light_colors(preset='WARM_COOL')
assert settings.studio_key.data.color.r > settings.studio_key.data.color.b
assert settings.studio_rim.data.color.b > settings.studio_rim.data.color.r

# Scoped resets restore defaults without touching other studio sections.
settings.studio_camera.location = (4, -12, 3)
settings.studio_camera_aim.location = (1, 2, 3)
settings.studio_camera.data.type = 'ORTHO'
settings.studio_camera.data.lens = 35
settings.studio_key.location = (3, 4, 5)
settings.studio_key.data.energy = 456
settings.studio_fill.data.energy = 789
settings.studio_color = (0.1, 0.2, 0.3)
settings.studio_width = 19
assert bpy.ops.render.polygroups_reset_studio(scope='CAMERA') == {'FINISHED'}
assert tuple(settings.studio_camera.location) == (0, -8, 0.5)
assert tuple(settings.studio_camera_aim.location) == (0, 0, 0.5)
assert settings.studio_camera.data.type == 'PERSP' and settings.studio_camera.data.lens == 85
assert settings.studio_key.data.energy == 456 and settings.studio_width == 19
assert bpy.ops.render.polygroups_reset_studio(scope='KEY') == {'FINISHED'}
assert tuple(settings.studio_key.location) == (-2, -3, 3)
assert settings.studio_key.data.energy == 50 and settings.studio_fill.data.energy == 789
settings.studio_rim.data.color = (1, 0, 0)
settings.studio_rim.hide_render = True
settings.studio_rim_aim.location = (1, 2, 3)
assert bpy.ops.render.polygroups_reset_studio(scope='LIGHTS') == {'FINISHED'}
assert settings.studio_fill.data.energy == 50 and settings.studio_rim.data.energy == 100
assert tuple(settings.studio_rim.data.color) == (1, 1, 1)
assert not settings.studio_rim.hide_render
assert tuple(settings.studio_rim_aim.location) == (0, 0, 0.5)
assert settings.studio_width == 19
settings.studio_camera.data.lens = 40
settings.studio_fill.data.energy = 321
settings.studio_backdrop.location = (1, 2, 3)
settings.studio_backdrop.scale = (2, 2, 2)
assert bpy.ops.render.polygroups_reset_studio(scope='SCENE') == {'FINISHED'}
assert settings.studio_width == 12
assert tuple(settings.studio_color) == tuple(settings.bl_rna.properties['studio_color'].default_array)
assert tuple(settings.studio_backdrop.location) == (0, 0, 0)
assert tuple(settings.studio_backdrop.scale) == (1, 1, 1)
assert settings.studio_camera.data.lens == 40 and settings.studio_fill.data.energy == 321
settings.studio_move_step = 1
assert bpy.ops.render.polygroups_reset_studio(scope='ALL') == {'FINISHED'}
assert abs(settings.studio_move_step - 0.1) < 1e-6
assert settings.studio_camera.data.lens == 85 and settings.studio_fill.data.energy == 50
assert counts == (len(bpy.data.objects), len(bpy.data.collections), len(bpy.data.materials))
bpy.data.objects.remove(settings.studio_camera_aim, do_unlink=True)
assert bpy.ops.render.polygroups_reset_studio(scope='CAMERA') == {'FINISHED'}
assert settings.studio_camera.constraints['Studio Aim'].target == settings.studio_camera_aim
assert counts == (len(bpy.data.objects), len(bpy.data.collections), len(bpy.data.materials))

# Preview a one-metre object without touching the user's open scene.
for obj in original_objects:
    obj.hide_render = True
settings.studio_radius = 1
settings.studio_width = 12
settings.studio_distance = 3
settings.studio_color = (0.18, 0.18, 0.18)
settings.studio_camera.location.y = -8
settings.studio_key.data.energy = 50
settings.studio_fill.hide_render = False
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0, 0, 0.5))
for poly in bpy.context.object.data.polygons:
    poly.use_smooth = True
scene.render.engine = 'CYCLES'
scene.cycles.samples = 16
scene.render.resolution_x = 256
scene.render.resolution_y = 256
scene.render.resolution_percentage = 100
preview = Path(tempfile.gettempdir()) / 'polygroups_studio_preview.png'
scene.render.filepath = str(preview)
bpy.ops.render.render(write_still=True)

with tempfile.TemporaryDirectory() as directory:
    saved_path = str(Path(directory) / 'studio.blend')
    bpy.ops.wm.save_as_mainfile(filepath=saved_path)
    bpy.ops.wm.open_mainfile(filepath=saved_path)
    settings = bpy.context.scene.polygroups_render_settings
    assert bpy.context.scene.camera == settings.studio_camera
    assert settings.studio_key.constraints[0].target == settings.studio_key_aim
    settings.studio_width = 10
    assert max(vertex.co.x for vertex in settings.studio_backdrop.data.vertices) == 5
# Delete custom prefix collections and arbitrary nested children, preserving assets.
scene = bpy.context.scene
settings = scene.polygroups_render_settings
asset_collection = bpy.data.collections.new('Generated.999')
scene.collection.children.link(asset_collection)
asset = bpy.data.objects.new('Protected Asset', bpy.data.meshes.new('Protected Mesh'))
asset_collection.objects.link(asset)
for prefix in ('Scene_', 'Camera_', 'Light_'):
    collection = bpy.data.collections.new(prefix + 'Custom')
    scene.collection.children.link(collection)
    child = bpy.data.collections.new(prefix + 'Nested')
    collection.children.link(child)
    grandchild = bpy.data.collections.new('Arbitrary ' + prefix + ' Child')
    child.children.link(grandchild)
    obj = bpy.data.objects.new('Delete ' + prefix, None)
    grandchild.objects.link(obj)
    # A multiply linked object must survive in its Generated collection.
    child.objects.link(asset)
remaining_objects = {obj.name for obj in scene.collection.all_objects
                     if not obj.get(TAG) and not obj.name.startswith('Delete ')}
assert bpy.ops.render.polygroups_delete_studio_scenes() == {'FINISHED'}
assert not any(c.name.startswith(('Scene_', 'Camera_', 'Light_', 'Arbitrary ')) for c in bpy.data.collections)
assert asset.name in asset_collection.objects
assert remaining_objects <= set(bpy.data.objects.keys())
assert bpy.context.scene.camera is None
assert all(getattr(settings, 'studio_' + role) is None for role in (
    'backdrop', 'camera', 'camera_aim', 'key', 'key_aim', 'fill', 'fill_aim', 'rim', 'rim_aim'))
assert bpy.ops.render.polygroups_delete_studio_scenes() == {'FINISHED'}
assert bpy.ops.render.polygroups_prepare_studio() == {'FINISHED'}
assert len([obj for obj in bpy.data.objects if obj.get(TAG)]) == 9
print('studio rig test passed')
