"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
from pathlib import Path
import addon_utils
import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.context.preferences.addons[ROOT.name].preferences.play_sound_after_operations = False
from polygroups_generator.operators import object_seam_cutter as c

# Extrude and Solidify must remain independent on both new and existing curves.
settings = bpy.context.scene.polygroups_object_seam_cutter_settings
path = c._create_cutter_path('Settings', [
    {'location': Vector((-3, 0, 0)), 'normal': Vector((0, 0, 1))},
    {'location': Vector((3, 0, 0)), 'normal': Vector((0, 0, 1))},
], 12, .5, .5, thickness=.01)
modifier = path.modifiers[c.CUTTER_SOLIDIFY_MODIFIER_NAME]
assert abs(modifier.thickness - .01) < 1e-7
settings.cutter_thickness = .02
assert abs(modifier.thickness - .02) < 1e-7
assert abs(path.data.extrude - .5) < 1e-7
settings.cutter_extrude = .3
assert abs(path.data.extrude - .3) < 1e-7
assert abs(modifier.thickness - .02) < 1e-7
path.select_set(True)
settings.cutter_path_render_u = 24
assert abs(path.data.extrude - .3) < 1e-7
settings.cutter_thickness = 0
assert abs(settings.cutter_thickness - .0001) < 1e-8
assert abs(modifier.thickness - .0001) < 1e-8
settings.cutter_thickness = .002

for method in ('KNIFE', 'BOOLEAN'):
    for solver in ('FLOAT', 'EXACT'):
        for kind in ('LOCAL_RING', 'ARC', 'PATH'):
            bpy.ops.object.select_all(action='SELECT')
            bpy.ops.object.delete(use_global=False)
            bpy.ops.mesh.primitive_cube_add()
            target = bpy.context.object
            if kind == 'LOCAL_RING':
                cutter = c._create_cutter_local_ring('Ring', Vector(), Vector((1,0,0)), Vector((0,1,0)), 3, 32, .5, .002)
            elif kind == 'ARC':
                cutter = c._create_cutter_arc('Arc', [Vector((-3,0,0)), Vector((0,.2,0)), Vector((3,0,0))], Vector((0,0,1)), 6, .5, .002)
            else:
                cutter = c._create_cutter_path('Path', [{'location': Vector((-3,0,0)), 'normal': Vector((0,0,1))}, {'location': Vector((3,0,0)), 'normal': Vector((0,0,1))}], 12, 3, .5)
            settings = bpy.context.scene.polygroups_object_seam_cutter_settings
            settings.cutter_apply_method = method
            settings.cutter_boolean_solver = solver
            settings.cutter_auto_fix_mesh = False
            settings.hide_cutters_after_apply = False
            settings.delete_cutters_after_apply = False
            bpy.ops.object.select_all(action='DESELECT')
            target.select_set(True)
            cutter.select_set(True)
            bpy.context.view_layer.objects.active = target
            assert bpy.ops.object.polygroups_apply_cutter_seams() == {'FINISHED'}
            bm = bmesh.new()
            bm.from_mesh(target.data)
            seams = [e for e in bm.edges if e.seam]
            print('CASE', method, solver, kind, 'seams', len(seams), 'open', sum(not e.is_manifold for e in bm.edges), flush=True)
            assert len(seams) >= 4, (method, solver, kind)
            assert all(e.is_manifold for e in bm.edges), (method, solver, kind, 'open edges')
            assert all(sum(e.seam for e in v.link_edges) == 2 for v in bm.verts if any(e.seam for e in v.link_edges)), 'seam must be a closed loop'
            assert abs(abs(bm.calc_volume()) - 8) < .05
            assert not target.data.materials
            bm.free()
# Repeated cuts keep the previous seam selected, preserve materials and open borders.
for method in ('KNIFE', 'BOOLEAN'):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add()
    target = bpy.context.object
    material = bpy.data.materials.new('Original')
    target.data.materials.append(material)
    bm = bmesh.new()
    bm.from_mesh(target.data)
    # An unrelated open triangle must not be welded or marked.
    verts = [bm.verts.new(co) for co in ((10,0,0), (10.00001,0,0), (10,1,0))]
    bm.faces.new(verts)
    bm.to_mesh(target.data)
    bm.free()
    settings.cutter_apply_method = method
    for z in (-.4, .4):
        cutter = c._create_cutter_local_ring('Ring', Vector((0,0,z)), Vector((1,0,0)), Vector((0,1,0)), 3, 16, .5, .002)
        c._apply_cutters_to_mesh(bpy.context, target, [cutter])
    seams = [e for e in target.data.edges if e.use_seam]
    assert seams and all(e.select for e in seams)
    assert set(round(target.data.vertices[e.vertices[0]].co.z, 1) for e in seams) == {-.4, .4}
    assert list(target.data.materials) == [material]
    bm = bmesh.new()
    bm.from_mesh(target.data)
    assert sum(e.is_boundary for e in bm.edges) == 3
    assert not any(e.seam for e in bm.edges if e.is_boundary)
    bm.free()
    # A cutter that misses must leave existing topology and seams unchanged.
    before = (len(target.data.vertices), len(target.data.edges), len(target.data.polygons), sum(e.use_seam for e in target.data.edges))
    cutter = c._create_cutter_local_ring('Miss', Vector((0,0,5)), Vector((1,0,0)), Vector((0,1,0)), 3, 16, .5, .002)
    assert c._apply_cutters_to_mesh(bpy.context, target, [cutter]) == 0
    assert before == (len(target.data.vertices), len(target.data.edges), len(target.data.polygons), sum(e.use_seam for e in target.data.edges))
print('Cutter seam integration tests passed', flush=True)
addon_utils.disable(ROOT.name)

