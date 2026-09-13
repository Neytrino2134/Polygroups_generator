"""Topology-based morphological opening of a face graph (no Blender dependency)."""
from collections import deque
from heapq import heappop, heappush
from math import sqrt


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


def metric_distances(seeds, adjacency, centers, allowed):
    """Geodesic face-centre distance, with optional nonzero boundary seeds."""
    result = {node: float(distance) for node, distance in seeds.items() if node in allowed}
    queue = [(distance, node) for node, distance in result.items()]
    from heapq import heapify
    heapify(queue)
    while queue:
        distance, node = heappop(queue)
        if distance != result[node]:
            continue
        for other in adjacency[node]:
            if other not in allowed:
                continue
            step = sqrt(sum((a - b) ** 2 for a, b in zip(centers[node], centers[other])))
            candidate = distance + step
            if candidate < result.get(other, float('inf')):
                result[other] = candidate
                heappush(queue, (candidate, other))
    return result


def shape_aspect(nodes, centers):
    """Principal-axis elongation of a proposed part, independent of face count."""
    if len(nodes) < 3:
        return 0.0
    points = [centers[node] for node in nodes]
    dimensions = len(points[0])
    mean = [sum(point[i] for point in points) / len(points) for i in range(dimensions)]
    covariance = [[sum((point[i] - mean[i]) * (point[j] - mean[j]) for point in points)
                   for j in range(dimensions)] for i in range(dimensions)]
    direction = [1.0 / sqrt(dimensions)] * dimensions
    for _ in range(18):
        next_direction = [sum(covariance[i][j] * direction[j] for j in range(dimensions))
                          for i in range(dimensions)]
        magnitude = sqrt(sum(value * value for value in next_direction))
        if magnitude <= 1e-20:
            return 0.0
        direction = [value / magnitude for value in next_direction]
    major = sum(direction[i] * covariance[i][j] * direction[j]
                for i in range(dimensions) for j in range(dimensions))
    remaining = max(sum(covariance[i][i] for i in range(dimensions)) - major, 1e-20)
    return sqrt(major / remaining)


def filter_small_parts(adjacency, regions, face_areas, minimum_percent):
    """Reject cuts that would create pieces below a source-island area fraction.

    A quick branch-area check handles most false corner cuts. Then validate the
    combined cut plan, because two individually acceptable cuts can isolate a
    tiny piece between them. No graph or mesh mutation occurs here.
    """
    if minimum_percent <= 0:
        return regions
    by_face = {}
    islands = components(adjacency, adjacency)
    for index, island in enumerate(islands):
        by_face.update((face, index) for face in island)
    grouped = [[] for _ in islands]
    for region in regions:
        grouped[by_face[next(iter(region[0]))]].append(region)
    accepted = []
    for island, candidates in zip(islands, grouped):
        if not candidates:
            continue
        total = sum(face_areas[face] for face in island)
        if total <= 1e-20:
            accepted.extend(candidates)
            continue
        minimum = total * minimum_percent / 100.0
        keep = [region for region in candidates
                if sum(face_areas[face] for face in region[0]) >= minimum]
        while keep:
            blocked = {frozenset(pair) for _, attachments in keep for pair in attachments}
            remaining = set(island)
            small = []
            while remaining:
                seed = remaining.pop()
                part = {seed}
                stack = [seed]
                area = 0.0
                while stack:
                    face = stack.pop()
                    area += face_areas[face]
                    for neighbor in adjacency[face]:
                        if neighbor in remaining and frozenset((face, neighbor)) not in blocked:
                            remaining.remove(neighbor)
                            part.add(neighbor)
                            stack.append(neighbor)
                if area < minimum:
                    small.append(part)
            if not small:
                break
            offenders = [region for region in keep if any(
                region[0] & part or any(a in part or b in part for a, b in region[1])
                for part in small)]
            if not offenders:
                keep.clear()
                break
            keep.remove(min(offenders, key=lambda region: (
                sum(face_areas[face] for face in region[0]), min(region[0]))))
        accepted.extend(keep)
    return accepted


def find_narrow_regions(adjacency, boundary, width=3, min_faces=8,
                        min_length=3, min_core_faces=8, metric_depth=None,
                        centers=None, max_width_percent=0.0, min_shape_aspect=1.8):
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
        widest = max((metric_depth.get(node, 0.0) for node in island), default=0.0) if metric_depth else 0.0
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
            if widest > 1e-12 and max_width_percent > 0 and centers is not None:
                local = sorted(metric_depth[node] for node in branch)
                typical = local[int(0.75 * (len(local) - 1))]
                if typical > widest * max_width_percent / 100.0:
                    continue
                # Wide corner wedges can be near the boundary, yet are not
                # elongated appendages. Measure their actual geometry.
                if shape_aspect(branch, centers) < min_shape_aspect:
                    continue
            found.append((branch, attachments))
    return found
