"""UV distortion detection and conservative face-graph region growing."""
import math

from .narrow_regions import components


def distortion_scores(areas, uv_areas, shapes, islands):
    """Compare density within each island; independent of packing scale."""
    scores = {}
    for island in islands:
        samples = sorted((uv_areas[i] / areas[i], areas[i])
                         for i in island if areas[i] > 1e-20)
        total = sum(weight for _, weight in samples)
        accumulated = 0.0
        reference = 0.0
        for density, weight in samples:
            accumulated += weight
            reference = density
            if accumulated >= total * 0.5:
                break
        for i in island:
            if areas[i] <= 1e-20:
                scores[i] = 1.0
                continue
            density = uv_areas[i] / areas[i]
            area_stretch = (max(density / reference, reference / density)
                            if min(reference, density) > 1e-20 else math.inf)
            scores[i] = max(area_stretch, shapes[i])
    return scores


def find_regions(scores, adjacency, threshold=4.0, grow_threshold=1.8,
                 min_faces=6, smooth_steps=2):
    seeds = {i for i, score in scores.items() if score >= threshold}
    allowed = {i for i, score in scores.items() if score >= grow_threshold}
    regions = []
    for part in components(allowed, adjacency):
        if not part & seeds:
            continue
        regions.append(part)
    selected = set().union(*regions) if regions else set()
    # Fill concave notches by majority voting; never delete critical seeds.
    for _ in range(smooth_steps):
        add = {i for i, neighbors in adjacency.items() if i not in selected
               and len(neighbors) >= 2 and len(neighbors & selected) > len(neighbors) / 2}
        selected.update(add)
    return [part for part in components(selected, adjacency) if len(part) >= min_faces]
