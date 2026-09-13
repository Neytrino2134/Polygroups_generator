"""Run with Blender --background --factory-startup --python this_file."""
import sys
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import smart_cage, baking

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
settings = bpy.context.scene.polygroups_baking_settings
assert abs(settings.smart_cage_margin - .001) < 1e-7
assert abs(settings.smart_cage_started_clearance - .05) < 1e-7
for name in ("smart_cage_live_thickness", "smart_cage_live_clearance"):
    assert abs(settings.bl_rna.properties[name].step / 100 - .001) < 1e-8
settings.smart_cage_samples = 4000
settings.smart_cage_iterations = 30
settings.smart_cage_margin = .01
settings.smart_cage_started_clearance = .3

def sphere(name, radius, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=radius)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.context.view_layer.update()
    return obj

for scale in [(1, 1, 1), (2, .7, 1.3)]:
    low = sphere("Low", 1, scale)
    high = sphere("High", 1.12, scale)
    original = [v.co.copy() for v in low.data.vertices]
    cage = smart_cage.generate(bpy.context, low, [high], settings)
    assert len(cage.data.vertices) == len(low.data.vertices)
    assert all(a == b.co for a, b in zip(original, low.data.vertices))
    assert smart_cage.validate(bpy.context, cage, low, [high], settings), settings.smart_cage_status
    mod = cage.modifiers[smart_cage.MODIFIER]
    mod.strength = 0
    bpy.context.view_layer.update()
    assert not smart_cage.validate(bpy.context, cage, low, [high], settings)
    assert "100.00%" not in settings.smart_cage_status
    # Manual edits survive validation, and a fresh Generate preserves the old cage.
    new = smart_cage.generate(bpy.context, low, [high], settings)
    assert new != cage and cage.name in bpy.data.objects
    assert cage.modifiers[smart_cage.MODIFIER].strength == 0
    bpy.ops.object.select_all(action="DESELECT")
    for obj in (low, high, new):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = low
    assert baking._source_meshes(bpy.context, low) == [high]
    assert smart_cage.prepare_bake(bpy.context, low, [high], settings, lambda *_: None)
    baking._configure_bake_settings(bpy.context, settings, "NORMAL")
    assert bpy.context.scene.render.bake.cage_object == new
    settings.use_smart_cage = False
    baking._configure_bake_settings(bpy.context, settings, "NORMAL")
    assert not bpy.context.scene.render.bake.use_cage
    assert bpy.context.scene.render.bake.cage_object is None

# Exercise registered UI operators and retained source references.
assert bpy.ops.object.polygroups_generate_smart_cage() == {"FINISHED"}
bpy.ops.object.select_all(action="DESELECT")
settings.smart_cage_object.select_set(True)
bpy.context.view_layer.objects.active = settings.smart_cage_object
assert bpy.ops.object.polygroups_validate_smart_cage() == {"FINISHED"}

# A real tiny Cycles bake checks explicit cage use, including hide_render.
bpy.ops.object.select_all(action="DESELECT")
low.select_set(True)
high.select_set(True)
bpy.context.view_layer.objects.active = low
material = bpy.data.materials.new("Smart Cage Bake Test")
material.use_nodes = True
low.data.materials.clear()
low.data.materials.append(material)
image = bpy.data.images.new("Smart Cage Bake Test", width=16, height=16)
node = material.node_tree.nodes.new("ShaderNodeTexImage")
node.image = image
material.node_tree.nodes.active = node
bpy.context.scene.cycles.samples = 1
baking._configure_bake_settings(bpy.context, settings, "NORMAL")
assert bpy.ops.object.bake(type="NORMAL") == {"FINISHED"}
assert max(image.pixels[:]) > .5

# Triangle-level intersections are checked even if sparse sample coverage looks good.
from mathutils import Vector
points = [Vector(p) for p in [(-1,-1,0), (1,-1,0), (0,1,0), (0,-.5,-1), (0,-.5,1), (0,.5,0)]]
triangles = [(0,1,2), (3,4,5)]
_, _, pairs, _ = smart_cage.conflicts(points, triangles, smart_cage.tree(points, triangles))
assert pairs == [(0,1)]
assert not smart_cage.closed(triangles)

# Separate masks and a persistent negative self-intersection correction.
cross_mesh = bpy.data.meshes.new("Crossing cage mesh")
cross_mesh.from_pydata([tuple(p) for p in points], [], triangles)
cross_low = bpy.data.objects.new("Crossing low", cross_mesh)
bpy.context.scene.collection.objects.link(cross_low)
cross_cage = bpy.data.objects.new("Crossing cage", cross_mesh.copy())
bpy.context.scene.collection.objects.link(cross_cage)
smart_cage.validate(bpy.context, cross_cage, cross_low, [high], settings)
self_group = cross_cage.vertex_groups[smart_cage.SELF_CONFLICTS]
high_group = cross_cage.vertex_groups[smart_cage.HIGH_CONFLICTS]
assert self_group != high_group
assert all(abs(self_group.weight(i) - 1) < 1e-7 for i in range(6))
reducer = cross_cage.modifiers[smart_cage.REDUCE_SELF]
assert reducer.vertex_group == self_group.name and abs(reducer.strength + .005) < 1e-7
settings.smart_cage_object = cross_cage
assert abs(settings.smart_cage_reduce_self + .005) < 1e-7
assert abs(settings.bl_rna.properties["smart_cage_reduce_self"].step / 100 - .001) < 1e-8
settings.smart_cage_reduce_self = -.006
assert abs(reducer.strength + .006) < 1e-7
settings.smart_cage_reduce_self = -2
assert settings.smart_cage_reduce_self == -1
settings.smart_cage_reduce_self = 1
assert settings.smart_cage_reduce_self == 0
settings.smart_cage_reduce_self = -.005
smart_cage.validate(bpy.context, cross_cage, cross_low, [high], settings)
assert all(abs(self_group.weight(i) - 1) < 1e-7 for i in range(6))

# Local protrusions must produce genuinely different weights.
low = sphere("Adaptive Low", 1)
high = sphere("Adaptive High", 1.02)
for vertex in high.data.vertices:
    if vertex.co.x > .2:
        vertex.co *= 1.2
bpy.context.view_layer.update()
cage = smart_cage.generate(bpy.context, low, [high], settings)
assert smart_cage.validate(bpy.context, cage, low, [high], settings), settings.smart_cage_status
weights = cage.vertex_groups[smart_cage.WEIGHTS]
values = [weights.weight(i) for i in range(len(cage.data.vertices))]
assert max(values) > 2 * min(values), "Offset is not adaptive"

# Two close surfaces: preserve the gap while covering both highpoly shells.
def pair(name, radius):
    a = sphere(name + " A", radius)
    b = sphere(name + " B", radius)
    a.location.x = -1.12
    b.location.x = 1.12
    bpy.ops.object.select_all(action="DESELECT")
    a.select_set(True)
    b.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()
    bpy.context.view_layer.update()
    return a

low = pair("Gap Low", 1)
high = pair("Gap High", 1.08)
cage = smart_cage.generate(bpy.context, low, [high], settings)
assert smart_cage.validate(bpy.context, cage, low, [high], settings), settings.smart_cage_status

settings.smart_cage_max = .001
try:
    smart_cage.generate(bpy.context, low, [high], settings)
except ValueError:
    pass
else:
    raise AssertionError("Contradictory limits accepted")

# An already covered highpoly must leave every adaptive weight at its seed.
settings.smart_cage_max = 0
settings.smart_cage_margin = .001
settings.smart_cage_started_clearance = .05
settings.smart_cage_iterations = 20
low = sphere("Seed Low", 1)
high = sphere("Seed High", .9)
cage = smart_cage.generate(bpy.context, low, [high], settings)
assert abs(cage.modifiers[smart_cage.BASE].strength - .001) < 1e-6
assert abs(cage.modifiers[smart_cage.MODIFIER].strength - .05) < 1e-6
weights = cage.vertex_groups[smart_cage.WEIGHTS]
assert all(abs(weights.weight(i) - .001) < 1e-7 for i in range(len(cage.data.vertices)))
assert smart_cage.validate(bpy.context, cage, low, [high], settings)
for prop, mod_name in (("smart_cage_live_thickness", smart_cage.MODIFIER),
                       ("smart_cage_live_clearance", smart_cage.TRIM)):
    before = getattr(settings, prop)
    setattr(settings, prop, before + .001)
    assert abs(cage.modifiers[mod_name].strength - before - .001) < 1e-6
    cage.modifiers[mod_name].strength = .123
    assert abs(getattr(settings, prop) - .123) < 1e-6
high = sphere("Growing High", 1.12)
settings.smart_cage_started_clearance = .2
cage = smart_cage.generate(bpy.context, low, [high], settings)
assert smart_cage.validate(bpy.context, cage, low, [high], settings), settings.smart_cage_status
assert max(cage.vertex_groups[smart_cage.WEIGHTS].weight(i) for i in range(len(cage.data.vertices))) > .001

# Generated.N naming, sibling placement, and independent transforms.
generated = bpy.data.collections.new("Generated.001")
bpy.context.scene.collection.children.link(generated)
low = sphere("Retopo_04_Highpoly_Generated.001", 1)
high = sphere("Naming High", 1.01)
for owner in tuple(low.users_collection):
    owner.objects.unlink(low)
generated.objects.link(low)
settings.smart_cage_started_clearance = .05
assert smart_cage.cage_name(low) == "Retopo_04_Highpoly_Generated_Cage.001"
cage = smart_cage.generate(bpy.context, low, [high], settings)
assert cage.name == "Retopo_04_Highpoly_Generated_Cage.001"
assert cage.parent is None and tuple(cage.users_collection) == (generated,)
old_location = cage.matrix_world.translation.copy()
low.location.x += 2
bpy.context.view_layer.update()
assert (cage.matrix_world.translation - old_location).length < 1e-8
next_cage = smart_cage.generate(bpy.context, low, [high], settings)
assert next_cage.name == "Retopo_04_Highpoly_Generated_Cage.002"
assert next_cage.parent is None and tuple(next_cage.users_collection) == (generated,)

# Generate with only a lowpoly selected uses AutoBake's exact collection lookup.
low.location.x = 0
matched_high = sphere("Highpoly_Generated.001", 1.01)
for owner in tuple(matched_high.users_collection):
    owner.objects.unlink(matched_high)
generated.objects.link(matched_high)
bpy.ops.object.select_all(action="DESELECT")
low.select_set(True)
bpy.context.view_layer.objects.active = low
matched_high.hide_viewport = True
matched_high.hide_render = True
assert bpy.ops.object.polygroups_generate_smart_cage() == {"FINISHED"}
assert matched_high.select_get() and low.select_get()
assert not matched_high.hide_viewport and not matched_high.hide_render
assert settings.smart_cage_object.get("smart_cage_sources")["0"] == matched_high

missing = sphere("Retopo_05_Highpoly_Generated.002", 1)
for owner in tuple(missing.users_collection):
    owner.objects.unlink(missing)
generated.objects.link(missing)
bpy.ops.object.select_all(action="DESELECT")
missing.select_set(True)
bpy.context.view_layer.objects.active = missing
previous_cage = settings.smart_cage_object
assert bpy.ops.object.polygroups_generate_smart_cage() == {"CANCELLED"}
assert settings.smart_cage_object == previous_cage
assert list(bpy.context.selected_objects) == [missing]
print("SMART_CAGE_TESTS_OK")
