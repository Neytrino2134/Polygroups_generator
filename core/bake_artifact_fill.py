"""Boundary-to-interior artifact fill. Pure NumPy; original unmasked pixels survive."""
import numpy as np
from .bake_artifact_mask import NEIGHBORS, _slices


def _normal_axes(swizzle):
    axes = [axis[-1] for axis in swizzle]
    if len(axes) != 3 or set(axes) != set('XYZ'):
        raise ValueError('Autofill normals requires an XYZ normal swizzle without duplicate axes')
    return [(i, 'XYZ'.index(axis[-1]), -1 if axis.startswith('NEG_') else 1)
            for i, axis in enumerate(swizzle)]


def _unit(values, fallback):
    lengths = np.linalg.norm(values, axis=1)
    result = values / np.maximum(lengths[:, None], 1e-12)
    bad = lengths < 1e-8
    result[bad] = fallback[bad]
    return result


def _neighbors(indices, shape, dy, dx):
    height, width = shape
    yy, xx = indices // width + dy, indices % width + dx
    valid = (yy >= 0) & (yy < height) & (xx >= 0) & (xx < width)
    return indices[valid], (yy[valid] * width + xx[valid])


def _blur_filled(field, filled, known, owners, radius, normal):
    if radius <= 0 or not np.any(filled):
        return field
    indices = np.flatnonzero(filled)
    labels = owners.ravel()
    valid = known.ravel()
    original = field.reshape(-1, 3)[indices].copy()
    for axis in (0, 1):
        sums = np.zeros((len(indices), 3), dtype=np.float32)
        weights = np.zeros(len(indices), dtype=np.float32)
        values = field.reshape(-1, 3)
        sigma = max(.5, radius / 2)
        for offset in range(-radius, radius + 1):
            # Sources on each side of a filled destination, with clipped image edges.
            yy, xx = indices // filled.shape[1], indices % filled.shape[1]
            if axis == 0:
                xx = xx + offset
            else:
                yy = yy + offset
            good = (yy >= 0) & (yy < filled.shape[0]) & (xx >= 0) & (xx < filled.shape[1])
            destinations = np.flatnonzero(good)
            neighbors = yy[good] * filled.shape[1] + xx[good]
            same = valid[neighbors] & (labels[neighbors] == labels[indices[good]])
            destinations, neighbors = destinations[same], neighbors[same]
            weight = np.float32(np.exp(-offset*offset / (2*sigma*sigma)))
            sums[destinations] += weight * values[neighbors]
            weights[destinations] += weight
        updated = sums / np.maximum(weights[:, None], 1e-12)
        next_field = field.copy()
        next_field.reshape(-1, 3)[indices] = updated
        field = next_field
    if normal:
        field.reshape(-1, 3)[indices] = _unit(field.reshape(-1, 3)[indices], original)
    return field


def fill_region(rgba, mask, ownership, donors, blur_radius=2, normal_swizzle=None):
    """Average an advancing 8-neighbor front, then blur only newly filled RGB.

    Donors are healthy outside-mask texels. Owners keep colors/vectors within the
    same UV island, including its assigned gutter. Disconnected/no-donor regions
    remain unchanged. All reads in one wave precede writes (no scan-order bias).
    """
    if rgba.shape != (*mask.shape, 4) or ownership.shape != mask.shape or donors.shape != mask.shape:
        raise ValueError('Autofill dimensions differ')
    normal = normal_swizzle is not None
    axes = _normal_axes(normal_swizzle) if normal else None
    field = rgba[..., :3].copy()
    if normal:
        field = np.empty_like(field)
        for encoded, canonical, sign in axes:
            field[..., canonical] = (rgba[..., encoded] - .50001) * (2*sign)
    healthy = donors & ~mask & (ownership > 0) & np.isfinite(field).all(axis=2)
    if normal:
        lengths = np.linalg.norm(field, axis=2)
        healthy &= lengths > 1e-8
        field[healthy] /= lengths[healthy, None]
    near_mask = np.zeros(mask.shape, dtype=bool)
    for dy, dx in NEIGHBORS:
        source, target = _slices(mask.shape, dy, dx)
        near_mask[source] |= mask[target] & (ownership[source] == ownership[target])
    frontier = np.flatnonzero(healthy & near_mask)
    filled = np.zeros(mask.shape, dtype=bool)
    labels, wanted, done = ownership.ravel(), mask.ravel(), filled.ravel()
    values = field.reshape(-1, 3)
    waves = 0
    while len(frontier):
        targets, sources = [], []
        for dy, dx in NEIGHBORS:
            origin, destination = _neighbors(frontier, mask.shape, dy, dx)
            eligible = wanted[destination] & ~done[destination] & (labels[destination] == labels[origin])
            targets.append(destination[eligible])
            sources.append(origin[eligible])
        targets, sources = np.concatenate(targets), np.concatenate(sources)
        if not len(targets):
            break
        unique, first, inverse = np.unique(targets, return_index=True, return_inverse=True)
        counts = np.bincount(inverse)
        averaged = np.column_stack([np.bincount(inverse, weights=values[sources, channel]) / counts
                                    for channel in range(3)]).astype(np.float32)
        if normal:
            averaged = _unit(averaged, values[sources[first]])
        values[unique] = averaged
        done[unique] = True
        frontier = unique
        waves += 1
    field = _blur_filled(field, filled, healthy | filled, ownership, blur_radius, normal)
    output = rgba.copy()
    if normal:
        for encoded, canonical, sign in axes:
            output[..., encoded][filled] = np.clip(field[..., canonical][filled] * (.5*sign) + .50001, 0, 1)
    else:
        output[..., :3][filled] = field[filled]
    output[..., 3][filled] = 1
    return output, filled, dict(filled=int(np.count_nonzero(filled)),
        unfilled=int(np.count_nonzero(mask & ~filled)), waves=waves)
