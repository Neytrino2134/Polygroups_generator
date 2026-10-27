"""Topology preparation shared by resculpting and ZBrush export."""
import bmesh
import bpy


def ngon_count(mesh):
    return sum(polygon.loop_total > 4 for polygon in mesh.polygons)


def triangulated_ngon_copy(mesh):
    """Return a private mesh with only n-gons triangulated; keep tris/quads."""
    if not ngon_count(mesh):
        return None
    if mesh.shape_keys:
        raise ValueError('Cannot triangulate n-gons on a mesh with shape keys before Resculpting')
    result = mesh.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(result)
        faces = [face for face in bm.faces if len(face.verts) > 4]
        bmesh.ops.triangulate(bm, faces=faces, quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.to_mesh(result)
        result.update()
        if ngon_count(result):
            raise RuntimeError('N-gon triangulation did not remove every face with more than four sides')
    except Exception:
        bpy.data.meshes.remove(result)
        raise
    finally:
        bm.free()
    return result


def triangulate_result_ngons(obj):
    """Replace only a completed remesh result containing n-gons."""
    original = obj.data
    prepared = triangulated_ngon_copy(original)
    if prepared is None:
        return 0
    count = ngon_count(original)
    obj.data = prepared
    if original.users == 0 and not original.library:
        bpy.data.meshes.remove(original)
    return count
