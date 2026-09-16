"""Blender background tests for tiny malformed UV island cleanup."""
import sys
from pathlib import Path
import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.uv_artifacts import find_uv_artifacts


def fixture():
    if bpy.context.object and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new('UVMap')
    faces = []
    for offset, material in ((0.0, 1), (3.0, 2)):
        verts = [bm.verts.new((offset+x, y, 0)) for x, y in ((0,0),(1,0),(1,1),(0,1))]
        face = bm.faces.new(verts)
        face.material_index = material
        faces.append(face)
    for loop in faces[0].loops:
        loop[uv].uv = (loop.vert.co.x, loop.vert.co.y)
    needle = ((0,0), (10,0), (10,.001), (0,.001))
    for loop, value in zip(faces[1].loops, needle):
        loop[uv].uv = value
    mesh = bpy.data.meshes.new('UVArtifactTest')
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new('UVArtifactTest', mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    return obj


obj = fixture()
bm = bmesh.from_edit_mesh(obj.data)
artifacts = find_uv_artifacts(bm, max_faces=7, stretch_threshold=8, compactness_threshold=10)
assert len(artifacts) == 1
assert {face.material_index for face in artifacts[0]['faces']} == {2}
assert bpy.ops.mesh.polygroups_uv_artifact_cleanup(action='SELECT') == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
assert {face.material_index for face in bm.faces if face.select} == {2}

obj = fixture()
assert bpy.ops.mesh.polygroups_uv_artifact_cleanup(action='APPLY', method='DELETE') == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()
assert len(bm.faces) == 1 and bm.faces[0].material_index == 1

obj = fixture()
before_verts = len(bmesh.from_edit_mesh(obj.data).verts)
assert bpy.ops.mesh.polygroups_uv_artifact_cleanup(action='APPLY', method='MERGE_CENTER') == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
assert len(bm.verts) < before_verts
assert any(face.material_index == 1 for face in bm.faces)

# Integrated cleanup must still commit when there is no cylindrical stretch region.
obj = fixture()
assert bpy.ops.mesh.polygroups_repair_uv_stretch(
    cleanup_artifacts=True, artifact_method='DELETE',
    artifact_max_faces=7, artifact_stretch=8, artifact_compactness=10) == {'FINISHED'}
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()
assert len(bm.faces) == 1 and bm.faces[0].material_index == 1
print('UV_ARTIFACT_CLEANUP_PASSED')
