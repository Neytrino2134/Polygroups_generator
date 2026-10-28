"""UV-preserving mesh simplification through the bundled meshoptimizer library.

meshoptimizer collapses edges into existing vertices, so every remaining vertex keeps
its original position and UV. Vertices are split into wedges by UV and material:
those splits become attribute discontinuities that are only collapsed along themselves.
"""
import ctypes
from math import radians
from pathlib import Path

import bmesh

DLL_PATH = Path(__file__).resolve().parents[1] / "lib" / "meshoptimizer.dll"

SIMPLIFY_LOCK_BORDER = 1 << 0
VERTEX_LOCK = 1 << 0
VERTEX_PRIORITY = 1 << 2
SEAM_FLAGS = {"LOCK": VERTEX_LOCK, "PRIORITY": VERTEX_PRIORITY, "FREE": 0}
SEAM_MODE_ITEMS = (
    ("LOCK", "Lock Seams", "Seam and island border vertices never move; best texture fidelity"),
    ("PRIORITY", "Prefer Seams", "Seam vertices are kept as long as possible; reaches lower budgets"),
    ("FREE", "Free Seams", "Seams may collapse along themselves; lowest geometric error"),
)

_library = None


class MeshoptUnavailable(RuntimeError):
    pass


def library():
    global _library
    if _library is None:
        if not DLL_PATH.is_file():
            raise MeshoptUnavailable(f"meshoptimizer library not found: {DLL_PATH}")
        try:
            loaded = ctypes.CDLL(str(DLL_PATH))
        except OSError as error:
            raise MeshoptUnavailable(f"meshoptimizer library failed to load: {error}") from error
        function = loaded.meshopt_simplifyWithAttributes
        function.restype = ctypes.c_size_t
        function.argtypes = [
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_float), ctypes.c_size_t, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_float), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_float), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t, ctypes.c_float, ctypes.c_uint, ctypes.POINTER(ctypes.c_float),
        ]
        _library = loaded
    return _library


def is_available():
    try:
        library()
    except MeshoptUnavailable:
        return False
    return True


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def _build_wedges(mesh):
    """One wedge per (vertex, all UV layers, material, smooth); returns wedge data and index buffer."""
    mesh.calc_loop_triangles()
    layers = [layer.data for layer in mesh.uv_layers]
    active = mesh.uv_layers.active_index
    loop_polygon = [0] * len(mesh.loops)
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            loop_polygon[loop_index] = polygon.index
    wedge_of, loop_wedge = {}, [0] * len(mesh.loops)
    wedges = []  # (vertex, uvs per layer, material, smooth)
    for loop in mesh.loops:
        polygon = mesh.polygons[loop_polygon[loop.index]]
        uvs = tuple((layer[loop.index].uv.x, layer[loop.index].uv.y) for layer in layers)
        key = (loop.vertex_index, tuple((round(u, 6), round(v, 6)) for u, v in uvs),
               polygon.material_index, polygon.use_smooth)
        wedge = wedge_of.get(key)
        if wedge is None:
            wedge = wedge_of[key] = len(wedges)
            wedges.append((loop.vertex_index, uvs, polygon.material_index, polygon.use_smooth))
        loop_wedge[loop.index] = wedge
    indices = [loop_wedge[index] for triangle in mesh.loop_triangles for index in triangle.loops]
    return wedges, indices, active


def _seam_vertices(mesh, wedges):
    """Vertices on UV/material splits, marked seams and open edges."""
    counts = {}
    for vertex, *_ in wedges:
        counts[vertex] = counts.get(vertex, 0) + 1
    result = {vertex for vertex, count in counts.items() if count > 1}
    edge_faces = {}
    for polygon in mesh.polygons:
        for key in polygon.edge_keys:
            edge_faces[key] = edge_faces.get(key, 0) + 1
    result.update(vertex for key, count in edge_faces.items() if count == 1 for vertex in key)
    result.update(vertex for edge in mesh.edges if edge.use_seam for vertex in edge.vertices)
    return result


def simplify_mesh(mesh, target_triangles, seam_mode="LOCK", uv_weight=1.0, max_error=1.0,
                  lock_open_borders=False, join_triangles=True, join_angle=radians(60)):
    """Simplify mesh in place to target_triangles. Returns a statistics dict.

    Preserves positions, all UV layers, materials, smooth flags, vertex groups and seams.
    Other attributes (colors, custom normals, sharp edges) are not carried over.
    """
    if not mesh.uv_layers:
        raise ValueError("Mesh has no UV map")
    lib = library()
    source_triangles = triangle_count(mesh)
    wedges, indices, active_uv = _build_wedges(mesh)
    count = len(wedges)
    positions = (ctypes.c_float * (count * 3))()
    attributes = (ctypes.c_float * (count * 2))()
    for wedge, (vertex, uvs, _, _) in enumerate(wedges):
        positions[wedge * 3:wedge * 3 + 3] = tuple(mesh.vertices[vertex].co)
        attributes[wedge * 2:wedge * 2 + 2] = uvs[active_uv]
    flag = SEAM_FLAGS[seam_mode]
    seam_vertices = _seam_vertices(mesh, wedges) if flag else set()
    lock = (ctypes.c_ubyte * count)(*[flag if wedge[0] in seam_vertices else 0 for wedge in wedges])
    source = (ctypes.c_uint * len(indices))(*indices)
    destination = (ctypes.c_uint * len(indices))()
    weights = (ctypes.c_float * 2)(uv_weight, uv_weight)
    error = ctypes.c_float()
    options = SIMPLIFY_LOCK_BORDER if lock_open_borders else 0
    result_count = lib.meshopt_simplifyWithAttributes(
        destination, source, len(indices), positions, count, 12, attributes, 8, weights, 2,
        lock, min(target_triangles, source_triangles) * 3, max_error, options, ctypes.byref(error))

    uv_names = [layer.name for layer in mesh.uv_layers]
    seam_edges = {edge.key for edge in mesh.edges if edge.use_seam}
    groups = {vertex.index: [(group.group, group.weight) for group in vertex.groups]
              for vertex in mesh.vertices}

    bm = bmesh.new()
    uv_layers = [bm.loops.layers.uv.new(name) for name in uv_names]
    deform = bm.verts.layers.deform.verify()
    verts = {}
    for index in range(result_count):
        vertex = wedges[destination[index]][0]
        if vertex not in verts:
            new = verts[vertex] = bm.verts.new(mesh.vertices[vertex].co)
            for group, weight in groups[vertex]:
                new[deform][group] = weight
    skipped = 0
    for index in range(0, result_count, 3):
        corner_wedges = destination[index:index + 3]
        try:
            face = bm.faces.new([verts[wedges[wedge][0]] for wedge in corner_wedges])
        except ValueError:
            skipped += 1
            continue
        _, _, material, smooth = wedges[corner_wedges[0]]
        face.material_index, face.smooth = material, smooth
        for loop, wedge in zip(face.loops, corner_wedges):
            for layer, uv in zip(uv_layers, wedges[wedge][1]):
                loop[layer].uv = uv
    bm.verts.index_update()
    original_of = {new: vertex for vertex, new in verts.items()}
    active_layer = uv_layers[active_uv]
    for edge in bm.edges:
        sides = edge.link_loops
        key = tuple(sorted(original_of[vertex] for vertex in edge.verts))
        split = len(sides) != 2
        if not split:
            first = {loop.vert: loop[active_layer].uv for loop in (sides[0], sides[0].link_loop_next)}
            second = {loop.vert: loop[active_layer].uv for loop in (sides[1], sides[1].link_loop_next)}
            split = any((first[vertex] - second[vertex]).length > 1e-6 for vertex in edge.verts)
        edge.seam = split or key in seam_edges
    if join_triangles:
        # New faces have no normals yet; the face angle check needs them.
        bm.normal_update()
        bmesh.ops.join_triangles(
            bm, faces=bm.faces[:], cmp_seam=True, cmp_sharp=False, cmp_uvs=True,
            cmp_vcols=False, cmp_materials=True,
            angle_face_threshold=join_angle, angle_shape_threshold=join_angle)
    bm.to_mesh(mesh)
    bm.free()
    if mesh.uv_layers:
        mesh.uv_layers.active_index = active_uv
    mesh.update()
    return dict(source_triangles=source_triangles, triangles=triangle_count(mesh),
                polygons=len(mesh.polygons), error=error.value, locked=len(seam_vertices),
                skipped=skipped)
