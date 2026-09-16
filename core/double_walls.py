"""Detect coincident faces with opposite winding, even with split vertices."""
from collections import defaultdict


def double_wall_groups(bm, tolerance=1e-6):
    bm.normal_update()
    buckets = defaultdict(list)
    for face in bm.faces:
        if face.calc_area() <= 1e-20:
            continue
        key = tuple(sorted(tuple(round(float(value) / tolerance) for value in vert.co)
                           for vert in face.verts))
        buckets[key].append(face)
    groups = []
    for faces in buckets.values():
        if len(faces) < 2:
            continue
        paired = set()
        for index, face in enumerate(faces):
            for other in faces[index + 1:]:
                if face.normal.dot(other.normal) > -0.9999:
                    continue
                if all(any((vert.co - candidate.co).length <= tolerance
                           for candidate in other.verts) for vert in face.verts):
                    paired.update((face, other))
        if paired:
            groups.append(paired)
    return groups
