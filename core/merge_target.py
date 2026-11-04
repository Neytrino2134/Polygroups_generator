"""Where a collapsed group of vertices should land.

Moving a group to its average position pulls the surrounding surface inward: volume shrinks and the
silhouette changes. Welding the group into one of its own vertices keeps every other vertex where it is, so
the surface only changes by the size of the removed patch. The vertex is chosen by the quadric error of the
faces that stay: the sum of area-weighted squared distances from the candidate to the planes of those faces.
"""


def plane_error(position, faces):
    total = 0.0
    for face in faces:
        distance = face.normal.dot(position - face.verts[0].co)
        total += face.calc_area() * distance * distance
    return total


def surviving_faces(vertices, removed=()):
    """Faces around ``vertices`` that are not collapsed with them: ``removed`` or lying fully inside the group."""
    group = set(vertices)
    removed = set(removed)
    return {face for vert in group if vert.is_valid for face in vert.link_faces
            if face.is_valid and face not in removed and not all(v in group for v in face.verts)}


def best_vertex(vertices, removed=(), allowed=None):
    """The vertex of ``vertices`` whose position changes the staying surface least (lowest vertex index on ties).

    ``allowed`` optionally limits the candidates (for example to vertices that are not pinned)."""
    candidates = [v for v in vertices if v.is_valid and (allowed is None or v in allowed)]
    if not candidates:
        return None
    faces = surviving_faces(candidates if allowed is None else vertices, removed)
    return min(candidates, key=lambda v: (plane_error(v.co, faces), v.index))
