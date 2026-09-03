"""Blender --background --factory-startup --python-exit-code 1 --python tests/test_local_contour.py"""
import sys
from pathlib import Path
from math import cos, sin, tau
import addon_utils
import bmesh
import bpy
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.context.preferences.addons[ROOT.name].preferences.play_sound_after_operations = False
from polygroups_generator.core.local_contour import fitted_section
from polygroups_generator.operators import object_seam_cutter as c


def target_mesh():
    verts, faces = [], []
    for center in (0, 3.0):
        base = len(verts)
        for z in (-2, 2):
            for i in range(96):
                angle = tau * i / 96
                radius = 1 + .15 * cos(angle * 3)
                verts.append((center + radius * cos(angle), .65 * radius * sin(angle), z))
        for i in range(96):
            j = (i + 1) % 96
            faces.append((base+i, base+j, base+96+j, base+96+i))
        faces.extend([tuple(base+i for i in reversed(range(96))), tuple(base+96+i for i in range(96))])
    mesh = bpy.data.meshes.new('Two nearby limbs')
    mesh.from_pydata(verts, [], faces)
    target = bpy.data.objects.new('Two nearby limbs', mesh)
    bpy.context.collection.objects.link(target)
    return target


for method in ('KNIFE', 'BOOLEAN'):
    for solver, tilt in ((solver, tilt) for solver in ('FLOAT', 'EXACT') for tilt in (0, .23)):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        target = target_mesh()
        bpy.context.view_layer.update()
        original = (len(target.data.vertices), len(target.data.polygons))
        seed, normal = Vector((1.15,0,0)), Vector((tilt,tilt*.5,1)).normalized()
        verts, faces = fitted_section(target, bpy.context.evaluated_depsgraph_get(), seed, normal, seed, 64, .01)
        assert len(verts) == 64 and len(faces) == 1
        assert max(p.x for p in verts) < 1.3
        assert max(p.y for p in verts) < .8  # follows the non-circular outline
        assert original == (len(target.data.vertices), len(target.data.polygons))
        mesh = bpy.data.meshes.new('Contour')
        mesh.from_pydata(verts, [], faces)
        cutter = bpy.data.objects.new('Contour', mesh)
        bpy.context.collection.objects.link(cutter)
        cutter[c.CUTTER_PROP] = True
        cutter[c.CUTTER_TYPE_PROP] = 'LOCAL_CONTOUR'
        c._add_solidify_modifier(cutter, .002)
        settings = bpy.context.scene.polygroups_object_seam_cutter_settings
        settings.cutter_apply_method = method
        settings.cutter_boolean_solver = solver
        settings.cutter_auto_fix_mesh = False
        settings.hide_cutters_after_apply = False
        bpy.context.view_layer.objects.active = target
        target.select_set(True)
        cutter.select_set(True)
        assert bpy.ops.object.polygroups_apply_cutter_seams() == {'FINISHED'}
        bm = bmesh.new()
        bm.from_mesh(target.data)
        seams = [e for e in bm.edges if e.seam]
        assert seams
        assert all(v.co.x < 1.3 for e in seams for v in e.verts), 'neighbor limb was cut'
        if not all(e.is_manifold for e in bm.edges):
            print('BAD EDGES', [(e.index, [tuple(v.co) for v in e.verts], len(e.link_faces)) for e in bm.edges if not e.is_manifold], flush=True)
        assert all(e.is_manifold for e in bm.edges)
        assert all(sum(e.seam for e in v.link_edges) == 2 for v in bm.verts if any(e.seam for e in v.link_edges))
        bm.free()
        print('PASS local contour', method, solver, 'tilt', tilt, flush=True)

# World transforms, exact point count, outward clearance, and evaluated geometry.
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
target = target_mesh()
target.matrix_world = Matrix.Translation((2,3,1)) @ Matrix.Rotation(.4,4,'Y') @ Matrix.Diagonal((1.2,.7,1.4,1))
bpy.context.view_layer.update()
seed = target.matrix_world @ Vector((1.15,0,0))
normal = target.matrix_world.to_3x3().inverted().transposed() @ Vector((0,0,1))
for count in (16,64,128):
    verts, faces = fitted_section(target, bpy.context.evaluated_depsgraph_get(), seed, normal, seed, count, .02)
    assert len(verts) == count
    assert all(abs((p-seed).dot(normal)) < 1e-5 for p in verts)
# Refuse overlap with the other limb instead of cutting it too.
try:
    fitted_section(target, bpy.context.evaluated_depsgraph_get(), seed, normal, seed, 64, 2)
except ValueError as exc:
    assert 'another section' in str(exc) or 'reduce Contour Offset' in str(exc)
else:
    raise AssertionError('overlapping local cutter was accepted')
# Exercise the actual two-screen-point creation path in both viewport modes.
from types import SimpleNamespace
from math import pi
from mathutils import Quaternion
from bpy_extras import view3d_utils
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
target = target_mesh()
bpy.context.view_layer.objects.active = target
target.select_set(True)
bpy.context.view_layer.update()
# Use real Blender camera projection matrices without requiring a GPU viewport.
region = SimpleNamespace(width=1000, height=1000)
camera = bpy.data.objects.new('Test View', bpy.data.cameras.new('Test View'))
bpy.context.collection.objects.link(camera)
camera.matrix_world = Matrix.Translation((0,-8,0)) @ Quaternion((1,0,0), pi / 2).to_matrix().to_4x4()
for perspective in ('ORTHO', 'PERSP'):
    camera.data.type = perspective
    camera.data.ortho_scale = 5
    bpy.context.view_layer.update()
    view = camera.matrix_world.inverted()
    projection = camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(), x=1000, y=1000)
    rv3d = SimpleNamespace(view_matrix=view, perspective_matrix=projection @ view,
                          is_perspective=perspective == 'PERSP', view_perspective=perspective)
    start, end = [view3d_utils.location_3d_to_region_2d(region, rv3d, Vector(p))
                  for p in ((-1.4,0,0), (1.4,0,0))]
    operator = SimpleNamespace(_start_pos=start, _start_region=region, _start_rv3d=rv3d)
    cutter = c.OBJECT_OT_polygroups_draw_cutter_local_contour._create_cutter(
        operator, bpy.context, target, end, settings,
    )
    assert cutter[c.CUTTER_TYPE_PROP] == 'LOCAL_CONTOUR'
    assert len(cutter.data.vertices) == settings.cutter_contour_points
    assert len(cutter.data.polygons) == 1
    assert c.CUTTER_SOLIDIFY_MODIFIER_NAME in cutter.modifiers
    bpy.context.view_layer.update()
    assert max((cutter.matrix_world @ v.co).x for v in cutter.data.vertices) < 1.3
    print('PASS two-click creation', perspective, flush=True)
print('Local contour tests passed', flush=True)
addon_utils.disable(ROOT.name)
