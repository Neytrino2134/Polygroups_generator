"""Blender background integration tests for direction-aware seam routing."""
import sys
from pathlib import Path
from importlib import import_module
import bmesh
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
route = import_module(ROOT.name + '.core.smart_seam_routing').route_seams


def fixture(warp=False):
    bm = bmesh.new()
    verts = {(x,y): bm.verts.new((x,y,0.04*x*y if warp else 0))
             for y in range(-3,4) for x in range(-3,4)}
    uv = bm.loops.layers.uv.new('UVMap')
    tag = bm.faces.layers.int.new('region_test')
    for y in range(-3,3):
        for x in range(-3,3):
            f = bm.faces.new([verts[x,y],verts[x+1,y],verts[x+1,y+1],verts[x,y+1]])
            f.select_set(True)
            f.material_index = len(bm.faces)-1
            f[tag] = f.material_index+10
            for loop in f.loops:
                loop[uv].uv = (loop.vert.co.x+f.material_index*3,loop.vert.co.y)
    path = [(-3,-1),(-2,-1),(-1,-1),(-1,0),(0,0),(0,1),(1,1),(2,1),(3,1)]
    for a,b in zip(path,path[1:]):
        bm.edges.get((verts[a],verts[b])).seam = True
    for e in bm.edges:
        if e.is_boundary:
            e.seam = True
    bm.normal_update()
    return bm, uv, tag


def seam_length(bm):
    return sum(e.calc_length() for e in bm.edges if e.seam and e.is_manifold)


for warp in (False,True):
    for enabled in (False,True):
        bm, uv, tag = fixture(warp)
        original = {v: v.co.copy() for v in bm.verts}
        old_length = seam_length(bm)
        counts = len(bm.verts),len(bm.edges),len(bm.faces)
        borders = {e for e in bm.edges if e.is_boundary}
        rerouted,cuts = route(bm,0.785,create_edges=enabled)
        print('ROUTE',warp,enabled,rerouted,cuts,old_length,seam_length(bm))
        if enabled:
            assert cuts > 0, 'Diagonal mode must cut the staircase, including warped quads'
            assert seam_length(bm) < old_length - 0.1
            assert len(bm.faces) > counts[2]
        else:
            assert cuts == 0
            assert counts == (len(bm.verts),len(bm.edges),len(bm.faces))
        assert all(v.co == co for v,co in original.items())
        assert all(e.seam for e in borders)
        assert all(len(e.link_faces) in (1,2) for e in bm.edges)
        assert all(f.calc_area()>1e-8 for f in bm.faces)
        for f in bm.faces:
            assert f[tag] == f.material_index+10
            for loop in f.loops:
                assert abs(loop[uv].uv.x-loop.vert.co.x-f.material_index*3)<1e-5
                assert abs(loop[uv].uv.y-loop.vert.co.y)<1e-5
        # Interior route stays unbranched and attached to both border endpoints.
        for v in bm.verts:
            if not v.is_boundary:
                assert sum(e.seam for e in v.link_edges) in (0,2)
        bm.free()

bm,_,_ = fixture(True)
seams = {e for e in bm.edges if e.seam}
assert route(bm,0.785,create_edges=True,protected=seams) == (0,0)
assert seams == {e for e in bm.edges if e.seam}
bm.free()

# Real operator must expose and exercise the new routing stage.
module = import_module(ROOT.name + '.operators.smart_angle_seams')
original_segment = module.segment_surfaces
try:
    for enabled in (False,True):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bm,_,_ = fixture(True)
        # Derive two labels from the manually supplied staircase.
        labels = bm.faces.layers.int.new('fixture_region')
        unseen = set(bm.faces)
        number = 0
        while unseen:
            stack = [unseen.pop()]
            while stack:
                f = stack.pop()
                f[labels] = number
                for e in f.edges:
                    if not e.seam:
                        for other in e.link_faces:
                            if other in unseen:
                                unseen.remove(other)
                                stack.append(other)
            number += 1
        mesh=bpy.data.meshes.new('route')
        bm.to_mesh(mesh)
        bm.free()
        obj=bpy.data.objects.new('route',mesh)
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        bpy.context.view_layer.objects.active=obj
        bpy.ops.object.mode_set(mode='EDIT')
        module.segment_surfaces=lambda bm,faces,*args: {f:f[bm.faces.layers.int['fixture_region']] for f in faces}
        settings=bpy.context.scene.polygroups_seam_preparation_settings
        settings.smart_seam_create_edges=enabled
        assert bpy.ops.mesh.polygroups_mark_smart_angle_seams()=={'FINISHED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        assert (len(mesh.polygons)>36) == enabled
finally:
    module.segment_surfaces=original_segment
print('SMART SEAM ROUTING TESTS PASSED')

# Triangular corridor must also admit paths across edges, not only quad diagonals.
bm,uv,tag=fixture(True)
bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='ALTERNATE')
bm.normal_update()
old_length=seam_length(bm)
counts=(len(bm.verts),len(bm.faces))
rerouted,cuts=route(bm,0.785,create_edges=True)
print('TRIANGLE ROUTE',rerouted,cuts,old_length,seam_length(bm),counts,(len(bm.verts),len(bm.faces)))
assert rerouted > 0
assert seam_length(bm) < old_length
assert all(len(e.link_faces) in (1,2) for e in bm.edges)
for f in bm.faces:
    assert f[tag] == f.material_index+10
    for loop in f.loops:
        assert abs(loop[uv].uv.x-loop.vert.co.x-f.material_index*3)<1e-5
        assert abs(loop[uv].uv.y-loop.vert.co.y)<1e-5
bm.free()


# Strong edge preference must suppress optional diagonal shortcuts.
bm,_,_=fixture(True)
_,cuts=route(bm,0.785,create_edges=True,edge_preference=5.0)
assert cuts == 0
bm.free()

# Junctions remain anchored; a route cannot swallow a branching vertex.
bm,_,_=fixture(True)
by_xy={(round(v.co.x),round(v.co.y)):v for v in bm.verts}
for a,b in [((0,1),(0,2)),((0,2),(0,3))]:
    bm.edges.get((by_xy[a],by_xy[b])).seam=True
junction=by_xy[0,1]
route(bm,0.785,create_edges=True)
assert sum(e.seam for e in junction.link_edges)==3
bm.free()

# No selection/hidden boundary can be crossed or cut.
for hidden in (False,True):
    bm,_,_=fixture(True)
    for face in bm.faces:
        if face.calc_center_median().y < -1:
            if hidden:
                face.hide_set(True)
            else:
                face.select_set(False)
    untouched={e:e.seam for e in bm.edges if any(f.hide or not f.select for f in e.link_faces)}
    route(bm,0.785,create_edges=True)
    assert all(e.is_valid and e.seam==flag for e,flag in untouched.items())
    bm.free()
print('PREFERENCE, JUNCTION AND SELECTION PROTECTIONS PASSED')

# End-to-end geometric detection on a slanted fold, without segmentation stubs.
results=[]
for enabled in (False,True):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bm,_,_=fixture()
    for v in bm.verts:
        v.co.z=0.9*abs(v.co.y-0.45*v.co.x-0.15)
    for e in bm.edges:
        e.seam=False
    bm.normal_update()
    mesh=bpy.data.meshes.new('slanted_fold')
    bm.to_mesh(mesh)
    bm.free()
    obj=bpy.data.objects.new('slanted_fold',mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode='EDIT')
    settings=bpy.context.scene.polygroups_seam_preparation_settings
    settings.smart_seam_create_edges=enabled
    assert bpy.ops.mesh.polygroups_mark_smart_angle_seams()=={'FINISHED'}
    edit=bmesh.from_edit_mesh(mesh)
    results.append((len(edit.faces),seam_length(edit)))
    bpy.ops.object.mode_set(mode='OBJECT')
print('DETECTED FOLD',results)
assert results[1][0]>results[0][0], 'Real fold detection must enable useful cuts'
assert results[1][1]<results[0][1]
