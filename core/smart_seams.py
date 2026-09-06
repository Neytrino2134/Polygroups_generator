"""Geometry-only, area-weighted surface segmentation for smart seams."""
import heapq
import math
from collections import Counter


def segment_surfaces(bm, faces, angle, iterations=4, min_fraction=0.01, smoothness=0.35):
    faces = sorted(faces, key=lambda f: f.index)
    count = len(faces)
    if not count:
        return {}
    indices = {f: i for i, f in enumerate(faces)}
    areas = [max(f.calc_area(), 1e-20) for f in faces]
    normals = [f.normal.copy() for f in faces]
    adjacency = [dict() for _ in faces]
    for i, face in enumerate(faces):
        for edge in face.edges:
            if len(edge.link_faces) != 2:
                continue
            other = edge.link_faces[0] if edge.link_faces[1] == face else edge.link_faces[1]
            j = indices.get(other)
            if j is not None:
                adjacency[i][j] = edge.calc_length()
    # Bilateral diffusion: average small bumps but suppress diffusion across creases.
    for _ in range(iterations):
        filtered = []
        for i in range(count):
            normal = normals[i] * areas[i]
            for j in adjacency[i]:
                dot = max(-1.0, min(1.0, normals[i].dot(normals[j])))
                weight = math.exp(-((1.0 - dot) / 0.18) ** 2)
                normal += normals[j] * (areas[j] * weight)
            filtered.append(normal.normalized())
        normals = filtered
    parent = list(range(count))
    sums = [normals[i] * areas[i] for i in range(count)]
    weights = areas[:]
    neighbors = [dict(a) for a in adjacency]
    versions = [0] * count
    queue = []

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def offer(a, b):
        if a > b:
            a, b = b, a
        dot = sums[a].normalized().dot(sums[b].normalized())
        heapq.heappush(queue, (1.0 - dot, a, b, versions[a], versions[b]))

    def merge(a, b):
        parent[b] = a
        sums[a] += sums[b]
        weights[a] += weights[b]
        versions[a] += 1
        neighbors[a].pop(b, None)
        for n, length in list(neighbors[b].items()):
            neighbors[n].pop(b, None)
            if n != a:
                neighbors[a][n] = neighbors[a].get(n, 0.0) + length
                neighbors[n][a] = neighbors[a][n]
        neighbors[b].clear()
        for n in neighbors[a]:
            offer(a, n)

    for i in range(count):
        for j in neighbors[i]:
            if i < j:
                offer(i, j)
    threshold = 1.0 - math.cos(angle)
    while queue:
        cost, a, b, va, vb = heapq.heappop(queue)
        if parent[a] != a or parent[b] != b or va != versions[a] or vb != versions[b]:
            continue
        if cost > threshold:
            break
        merge(a, b)
    # Area threshold is relative to each connected component, not the whole selection.
    components = []
    unseen = set(range(count))
    while unseen:
        seed = min(unseen)
        unseen.remove(seed)
        component, stack = [], [seed]
        while stack:
            i = stack.pop()
            component.append(i)
            for j in adjacency[i]:
                if j in unseen:
                    unseen.remove(j)
                    stack.append(j)
        components.append(component)
    for component in components:
        minimum = sum(areas[i] for i in component) * min_fraction
        for r in sorted({root(i) for i in component}, key=lambda r: (weights[r], r)):
            r = root(r)
            if weights[r] < minimum and neighbors[r]:
                target = min(neighbors[r], key=lambda n: (
                    1.0 - sums[r].normalized().dot(sums[n].normalized()),
                    -neighbors[r][n], n))
                merge(target, r)
    labels = [root(i) for i in range(count)]
    # Shorten boundaries with a length penalty, preserving source-region connectivity.
    means = {r: sums[r].normalized() for r in set(labels)}
    sizes = Counter(labels)
    for _ in range(3 if smoothness else 0):
        changed = False
        for i in range(count):
            old = labels[i]
            candidates = {labels[j] for j in adjacency[i]}
            if len(candidates | {old}) < 2 or sizes[old] <= 1:
                continue
            perimeter = sum(adjacency[i].values()) or 1.0
            def energy(label):
                return (1.0 - normals[i].dot(means[label]) + smoothness *
                        sum(length for j, length in adjacency[i].items() if labels[j] != label) / perimeter)
            best = min(candidates | {old}, key=lambda r: (energy(r), r))
            if best == old or energy(best) >= energy(old) - 1e-9:
                continue
            # A connected local fan is a sufficient condition for no fragmentation.
            fan = {j for j in adjacency[i] if labels[j] == old}
            if fan:
                reached = {min(fan)}
                stack = list(reached)
                while stack:
                    for j in adjacency[stack.pop()]:
                        if j in fan and j not in reached:
                            reached.add(j)
                            stack.append(j)
                if reached != fan:
                    continue
            labels[i] = best
            sizes[old] -= 1
            sizes[best] += 1
            changed = True
        if not changed:
            break
    return {face: labels[i] for i, face in enumerate(faces)}
