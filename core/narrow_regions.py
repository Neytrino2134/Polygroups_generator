"""Topology-based morphological opening of a face graph (no Blender dependency)."""
from collections import deque


def components(nodes, adjacency):
    remaining = set(nodes)
    result = []
    for seed in sorted(remaining):
        if seed not in remaining:
            continue
        remaining.remove(seed)
        part = {seed}
        queue = [seed]
        while queue:
            for neighbor in adjacency[queue.pop()]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    part.add(neighbor)
                    queue.append(neighbor)
        result.append(part)
    return result


def distances(seeds, adjacency, allowed):
    result = {node: 0 for node in seeds}
    queue = deque(sorted(seeds))
    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            if neighbor in allowed and neighbor not in result:
                result[neighbor] = result[node] + 1
                queue.append(neighbor)
    return result


def find_narrow_regions(adjacency, boundary, width=3, min_faces=8,
                        min_length=3, min_core_faces=8):
    """Return narrow face sets with their attachment pairs.

    Width is an approximate number of face rows, not a metric distance.
    Opening preserves broad bodies and removes thin branches. Components with
    no broad core (e.g. an entire ribbon) are intentionally left untouched.
    Runtime is linear in graph size apart from deterministic seed sorting.
    """
    found = []
    radius = max(1, int(width) // 2 + 1)
    boundary = set(boundary)
    for island in components(adjacency, adjacency):
        depth = distances(island & boundary, adjacency, island)
        if not depth:
            continue
        cores = {node for node in island if depth.get(node, 0) >= radius}
        cores = set().union(*(part for part in components(cores, adjacency)
                             if len(part) >= min_core_faces)) if cores else set()
        if not cores:
            continue
        from_core = distances(cores, adjacency, island)
        body = {node for node, distance in from_core.items() if distance <= radius}
        for branch in components(island - body, adjacency):
            if len(branch) < min_faces:
                continue
            attachments = {(node, neighbor) for node in branch
                           for neighbor in adjacency[node] if neighbor in body}
            if not attachments:
                continue
            mouths = {node for node, _ in attachments}
            length = max(distances(mouths, adjacency, branch).values()) + 1
            if length < min_length:
                continue
            # Diagonal/staircase mouths may take up to twice the row width.
            if len(attachments) > 4 * width:
                continue
            found.append((branch, attachments))
    return found
