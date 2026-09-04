"""Blender background: ring fitting away from object bounds and with missed endpoints."""
import sys
from pathlib import Path
from types import SimpleNamespace
from math import cos, sin, tau, pi

import addon_utils
import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector
from bpy_extras import view3d_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.context.preferences.addons[ROOT.name].preferences.play_sound_after_operations = False
from polygroups_generator.operators import object_seam_cutter as c

settings = bpy.context.scene.polygroups_object_seam_cutter_settings
settings.cutter_local_ring_segments = 8
settings.cutter_auto_fix_mesh = False
settings.hide_cutters_after_apply = False
settings.delete_cutters_after_apply = False
region = SimpleNamespace(width=1000, height=1000)


def make_target():
    vertices, faces = [], []
    for x, y in ((0, -3), (4, 3)):
        base = len(vertices)
        for z in (-2, 2):
            vertices.extend((x + cos(tau * i / 64), y + .7 * sin(tau * i / 64), z)
                            for i in range(64))
        faces.extend((base+i, base+(i+1)%64, base+64+(i+1)%64, base+64+i) for i in range(64))
        faces.extend((tuple(base+i for i in reversed(range(64))), tuple(base+64+i for i in range(64))))
    mesh = bpy.data.meshes.new("Separated limbs")
    mesh.from_pydata(vertices, [], faces)
    target = bpy.data.objects.new("Separated limbs", mesh)
    bpy.context.collection.objects.link(target)
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    return target


for perspective in ("ORTHO", "PERSP"):
    for mode in ("VOLUME", "SURFACE"):
        for method in ("BOOLEAN", "KNIFE"):
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.object.delete(use_global=False)
            target = make_target()
            original = (len(target.data.vertices), len(target.data.polygons))
            camera = bpy.data.objects.new("View", bpy.data.cameras.new("View"))
            bpy.context.collection.objects.link(camera)
            camera.matrix_world = Matrix.Translation((0, -10, 0)) @ Quaternion((1, 0, 0), pi/2).to_matrix().to_4x4()
            camera.data.type = perspective
            camera.data.ortho_scale = 5
            bpy.context.view_layer.update()
            projection = camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(), x=1000, y=1000)
            view = camera.matrix_world.inverted()
            rv3d = SimpleNamespace(view_matrix=view, perspective_matrix=projection @ view,
                                   is_perspective=perspective == "PERSP", view_perspective=perspective)
            def screen(point):
                return view3d_utils.location_3d_to_region_2d(region, rv3d, Vector(point))
            # Both endpoints miss the limb. Its depth differs from the whole mesh center.
            start, end = screen((-1.5, -3, 0)), screen((1.5, -3, 0))
            center, a, b, radius = c._screen_local_ring_surface(None, region, rv3d, start, end, target, 0, mode)
            assert (center - Vector((0, -3, 0))).length < 1e-4, (mode, center)
            assert abs(a.dot(b)) < 1e-5
            assert radius * cos(pi / 8) >= 1
            if mode == "SURFACE":
                assert radius >= 1.49
            assert original == (len(target.data.vertices), len(target.data.polygons))
            cutter = c._create_cutter_local_ring("Fitted ring", center, a, b, radius, 8, .5, .0001)
            cutter.select_set(True)
            settings.cutter_apply_method = method
            assert bpy.ops.object.polygroups_apply_cutter_seams() == {"FINISHED"}
            bm = bmesh.new()
            bm.from_mesh(target.data)
            seams = [e for e in bm.edges if e.seam]
            assert seams and all(v.co.y < -1 for e in seams for v in e.verts)
            assert all(e.is_manifold for e in bm.edges)
            bm.free()
            print("PASS ring fit", perspective, mode, method, flush=True)

            # Never create a floating disk when the stroke misses the target.
            try:
                c._screen_local_ring_surface(None, region, rv3d, screen((7, -3, 0)),
                                             screen((8, -3, 0)), target, 0, mode)
            except ValueError as exc:
                assert "cross the visible surface" in str(exc)
            else:
                raise AssertionError("A missed stroke created a floating ring")

# A small slit opens the selected limb's section while the other limb is closed.
# Previously the closed-only search picked that other loop and raised the user's
# "indicated section is open or ambiguous" error instead of fitting the hit limb.
target = make_target()
bm = bmesh.new()
bm.from_mesh(target.data)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY")
bm.to_mesh(target.data)
bm.free()
bpy.context.view_layer.update()
before = (len(target.data.vertices), len(target.data.polygons))
for mode in ("VOLUME", "SURFACE"):
    center, a, b, radius = c._screen_local_ring_surface(
        None, region, rv3d, screen((-1.5, -3, 0)), screen((1.5, -3, 0)), target, 0, mode)
    assert (center - Vector((0, -3, 0))).length < .01, center
    assert radius >= 1
    assert before == (len(target.data.vertices), len(target.data.polygons))
    print("PASS open local section", mode, flush=True)

# A non-manifold fin creates a branch in the section. Coarse fitting should
# still use this limb rather than reject it in favor of the distant closed one.
target = make_target()
bm = bmesh.new()
bm.from_mesh(target.data)
bm.verts.ensure_lookup_table()
extra = bm.verts.new((1.4, -3, 1))
bm.verts.ensure_lookup_table()
bm.faces.new((bm.verts[1], bm.verts[65], extra))
bm.to_mesh(target.data)
bm.free()
bpy.context.view_layer.update()
for mode in ("VOLUME", "SURFACE"):
    center, a, b, radius = c._screen_local_ring_surface(
        None, region, rv3d, screen((-1.5, -3, 0)), screen((1.5, -3, 0)), target, 0, mode)
    assert abs(center.y + 3) < .1 and abs(center.x) < .4, center
    assert radius >= 1
    print("PASS branched local section", mode, flush=True)

# Sparse geometry falls back to the stroke's radius instead of failing the
# contour proximity check. The disk still includes the actual hit position.
from polygroups_generator.core.local_contour import fitted_ring_section
mesh = bpy.data.meshes.new("Single surface triangle")
mesh.from_pydata([(-.01, 0, -1), (.01, 0, -1), (0, 0, 1)], [], [(0, 1, 2)])
target = bpy.data.objects.new("Single surface triangle", mesh)
bpy.context.collection.objects.link(target)
bpy.context.view_layer.update()
center, a, b, radius = fitted_ring_section(
    target, bpy.context.evaluated_depsgraph_get(), Vector(), Vector((0, 0, 1)),
    Vector(), 16, 0, radius_hint=.5)
assert radius >= .5 and center.length < .01
print("Local ring fitting tests passed", flush=True)
