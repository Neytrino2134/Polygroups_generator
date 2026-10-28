"""Topology of seam-bounded charts: Euler characteristic, boundary loops, genus.

A chart unwraps cleanly only when it is a topological disk (chi == 1, one boundary).
Everything here works on the chart *after* cutting along its seams: each vertex is
split into "corner nodes", one per fan of faces joined through uncut edges.
"""
from collections import namedtuple


ChartInfo = namedtuple("ChartInfo", "faces chi genus loops nodes")
BoundaryLoop = namedtuple("BoundaryLoop", "nodes edges length")


def is_cut(edge, faces):
    """Seam, open edge, non-manifold edge, or border of this chart."""
    if edge.seam or len(edge.link_faces) != 2:
        return True
    return not all(face in faces for face in edge.link_faces)


def charts(bm, faces=None):
    """Seam-bounded face components, optionally restricted to ``faces``."""
    pool = set(faces) if faces is not None else {f for f in bm.faces if not f.hide}
    result, seen = [], set()
    for start in sorted(pool, key=lambda f: f.index):
        if start in seen:
            continue
        component, stack = {start}, [start]
        seen.add(start)
        while stack:
            for edge in stack.pop().edges:
                if edge.seam:
                    continue
                for other in edge.link_faces:
                    if other in pool and other not in seen:
                        seen.add(other)
                        component.add(other)
                        stack.append(other)
        result.append(component)
    return result


class CornerNodes:
    """Union of face corners across uncut edges: vertex copies of the cut chart."""

    def __init__(self, faces):
        self.faces = faces
        self.parent = {}
        for face in faces:
            for loop in face.loops:
                self.parent[(face, loop.vert)] = (face, loop.vert)
        for face in faces:
            for edge in face.edges:
                if is_cut(edge, faces):
                    continue
                other = edge.link_faces[0] if edge.link_faces[1] is face else edge.link_faces[1]
                for vert in edge.verts:
                    self._union((face, vert), (other, vert))

    def _find(self, key):
        parent = self.parent
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def _union(self, a, b):
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self.parent[ra] = rb

    def node(self, face, vert):
        return self._find((face, vert))

    def all_nodes(self):
        return {self._find(key) for key in self.parent}


def _cut_sides(faces):
    """(edge, face) pairs: one per side of each cut edge that borders the chart."""
    sides = []
    for face in faces:
        for edge in face.edges:
            if is_cut(edge, faces):
                sides.append((edge, face))
    return sides


def boundary_loops(faces, nodes=None):
    nodes = nodes or CornerNodes(faces)
    sides = _cut_sides(faces)
    parent = {}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    ends = []
    for edge, face in sides:
        a, b = (nodes.node(face, v) for v in edge.verts)
        for key in (a, b):
            parent.setdefault(key, key)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
        ends.append((edge, a))
    groups = {}
    for edge, a in ends:
        groups.setdefault(find(a), []).append(edge)
    loops = []
    for root, edges in groups.items():
        members = {key for key in parent if find(key) == root}
        loops.append(BoundaryLoop(members, edges, sum(e.calc_length() for e in edges)))
    loops.sort(key=lambda loop: -loop.length)
    return loops


def classify(faces):
    faces = set(faces)
    nodes = CornerNodes(faces)
    interior = {e for f in faces for e in f.edges if not is_cut(e, faces)}
    sides = _cut_sides(faces)
    vertex_count = len(nodes.all_nodes())
    chi = vertex_count - (len(interior) + len(sides)) + len(faces)
    loops = boundary_loops(faces, nodes)
    genus = (2 - chi - len(loops)) / 2.0
    return ChartInfo(faces, chi, genus, loops, nodes)


def is_disk(info):
    return info.chi == 1 and len(info.loops) == 1


def chart_kind(info, hole_ratio=0.0):
    """DISK, CLOSED, ANNULUS, MULTI or HANDLE; tiny holes do not count as boundaries."""
    if info.genus >= 0.5:
        return "HANDLE"
    if not info.loops:
        return "CLOSED"
    major = significant_loops(info, hole_ratio)
    if len(major) <= 1:
        return "DISK"
    return "ANNULUS" if len(major) == 2 else "MULTI"


def significant_loops(info, hole_ratio):
    if not info.loops:
        return []
    longest = info.loops[0].length
    return [loop for loop in info.loops if loop.length >= longest * hole_ratio]
