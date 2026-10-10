"""Isolated research probe: native tangent normals and native hit coverage."""
from math import pi
import bpy

bpy.context.preferences.use_preferences_save = False
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2)
low = bpy.context.object
low.name = 'Probe Low'
lowmat = bpy.data.materials.new('Probe Target')
lowmat.use_nodes = True
low.data.materials.append(lowmat)
image_node = lowmat.node_tree.nodes.new('ShaderNodeTexImage')
lowmat.node_tree.nodes.active = image_node
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -.2))
high = bpy.context.object
high.name = 'Probe High'
highmat = bpy.data.materials.new('Probe White Emission')
highmat.use_nodes = True
highmat.node_tree.nodes.clear()
emit = highmat.node_tree.nodes.new('ShaderNodeEmission')
emit.inputs['Color'].default_value = (1, 1, 1, 1)
output = highmat.node_tree.nodes.new('ShaderNodeOutputMaterial')
highmat.node_tree.links.new(emit.outputs[0], output.inputs['Surface'])
high.data.materials.append(highmat)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 1
scene.cycles.device = 'CPU'
bake = scene.render.bake
bake.use_selected_to_active = True
bake.use_cage = False
bake.cage_extrusion = .1
bake.max_ray_distance = 1
bake.normal_space = 'TANGENT'
bake.margin = 0
bake.use_clear = True
bpy.ops.object.select_all(action='DESELECT')
low.select_set(True)
high.select_set(True)
bpy.context.view_layer.objects.active = low
results = {}
for case, z, angle in [('valid', -.2, 0), ('reversed_hit', -.2, pi), ('miss', .2, 0)]:
    high.location.z = z
    high.rotation_euler.x = angle
    bpy.context.view_layer.update()
    results[case] = {}
    for bake_type in ('NORMAL', 'EMIT'):
        image = bpy.data.images.new(case+bake_type, width=32, height=32, alpha=True, float_buffer=True)
        image.colorspace_settings.name = 'Non-Color'
        image.generated_color = (0, 0, 0, 0)
        image_node.image = image
        assert bpy.ops.object.bake(type=bake_type) == {'FINISHED'}
        index = (16*32+16)*4
        results[case][bake_type] = tuple(round(v, 6) for v in image.pixels[index:index+4])
print('NATIVE_PROJECTION_PROBE', results, flush=True)
assert results['valid']['NORMAL'][2] > .99
assert results['reversed_hit']['NORMAL'][2] < .01
assert results['valid']['EMIT'][0] > .99 and results['reversed_hit']['EMIT'][0] > .99
assert results['miss']['EMIT'][0] < .01
print('NATIVE_PROJECTION_PROBE_PASSED', flush=True)
