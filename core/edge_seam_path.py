"""Route over existing edges, preferring edge-flow runs to zigzag shortcuts."""
from heapq import heappop, heappush
from itertools import count
from statistics import median


def find_edge_path(bm, start, end, matrix):
    """A* with incoming-edge states: length plus a penalty for each turn.

    Opposite edges in regular quad fans continue the same row even on a curved
    surface. At poles, triangles and wire vertices, use the geometric direction.
    Hidden geometry is excluded. No BMesh geometry or selection is modified.
    """
    if start == end or start.hide or end.hide:
        return []
    bm.verts.index_update()
    positions, neighbors, lengths, fans = {}, {}, {}, {}

    def position(vert):
        if vert not in positions:
            positions[vert] = matrix @ vert.co
        return positions[vert]

    def adjacent(vert):
        if vert not in neighbors:
            neighbors[vert] = sorted(
                [(edge.other_vert(vert), edge) for edge in vert.link_edges
                 if not edge.hide and not edge.other_vert(vert).hide],
                key=lambda item: item[0].index,
            )
        return neighbors[vert]

    def length(edge):
        if edge not in lengths:
            lengths[edge] = (position(edge.verts[0]) - position(edge.verts[1])).length
        return lengths[edge]

    def turn_cost(vert, incoming, outgoing):
        if incoming is None:
            return 0.0
        if vert not in fans:
            edges, faces = vert.link_edges, vert.link_faces
            fans[vert] = (
                (len(edges), len(faces)) in {(4, 4), (3, 2), (2, 1)}
                and all(len(face.verts) == 4 for face in faces)
                and all(edge.is_manifold or edge.is_boundary for edge in edges)
            )
        if fans[vert]:
            # Edges sharing a quad face turn across its corner; the opposite
            # pair continues a row, independently of curvature or uneven spacing.
            return float(any(face in outgoing.link_faces for face in incoming.link_faces))
        a = position(vert) - position(incoming.other_vert(vert))
        b = position(outgoing.other_vert(vert)) - position(vert)
        if a.length_squared < 1e-24 or b.length_squared < 1e-24:
            return 1.0
        cosine = max(-1.0, min(1.0, a.normalized().dot(b.normalized())))
        return 0.0 if cosine >= 0.95 else 1.0 - 0.5 * cosine

    local_lengths = [length(edge) for vert in (start, end) for _, edge in adjacent(vert)
                     if length(edge) > 1e-12]
    if not local_lengths:
        return []
    corner_weight = 8.0 * median(local_lengths)
    serial = count()
    initial = (start, None)
    costs = {initial: 0.0}
    parents = {}
    queue = [((position(start) - position(end)).length, next(serial), 0.0, initial)]
    while queue:
        _, _, cost, state = heappop(queue)
        if cost != costs.get(state):
            continue
        vert, incoming = state
        if vert == end:
            route = []
            while state != initial:
                route.append(state[1])
                state = parents[state]
            route.reverse()
            # An incoming-edge search can revisit a vertex to avoid an expensive
            # turn. Remove such loops so the resulting seam never has branches.
            vertices, simple, indices = [start], [], {start: 0}
            for edge in route:
                target = edge.other_vert(vertices[-1])
                if target in indices:
                    cut = indices[target]
                    for removed in vertices[cut + 1:]:
                        del indices[removed]
                    del vertices[cut + 1:]
                    del simple[cut:]
                else:
                    simple.append(edge)
                    indices[target] = len(vertices)
                    vertices.append(target)
            return simple
        for target, edge in adjacent(vert):
            if edge == incoming:
                continue
            new_cost = cost + length(edge) + corner_weight * turn_cost(vert, incoming, edge)
            following = (target, edge)
            if new_cost < costs.get(following, float("inf")):
                costs[following] = new_cost
                parents[following] = state
                estimate = new_cost + (position(target) - position(end)).length
                heappush(queue, (estimate, next(serial), new_cost, following))
    return []
