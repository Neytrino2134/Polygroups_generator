"""Binary projection diagnostics. No Blender dependency; arrays are UV pixel order."""
import numpy as np

REVERSED = 1
MISS = 2
EDGE = 4
PADDING = 8
GEOMETRY = 16


def canonical_z(rgba, swizzle):
    channels = [i for i, axis in enumerate(swizzle) if axis.endswith('_Z')]
    if len(channels) != 1:
        raise ValueError('Normal swizzle must contain exactly one Z channel')
    index = channels[0]
    sign = -1 if swizzle[index].startswith('NEG_') else 1
    return ((rgba[..., index] - 0.50001) * (2 * sign)).astype(np.float32)


def _grow_connected(seed, candidate, ownership):
    """Scanline union-find: work scales with row runs, not individual white pixels."""
    height, width = seed.shape
    parents, seeded, runs = [], [], []
    previous = []
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for y in range(height):
        row = candidate[y]
        ids = ownership[y]
        boundaries = np.flatnonzero(np.r_[True, (row[1:] != row[:-1]) | (ids[1:] != ids[:-1]), True])
        current = []
        p = 0
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            if not row[start]:
                continue
            label = len(parents)
            parents.append(label)
            seeded.append(bool(seed[y, start:end].any()))
            entry = (int(start), int(end), int(ids[start]), label)
            current.append(entry)
            runs.append((y, *entry))
            while p < len(previous) and previous[p][1] <= start:
                p += 1
            q = p
            while q < len(previous) and previous[q][0] < end:
                if entry[2] > 0 and previous[q][2] == entry[2]:
                    a, b = root(label), root(previous[q][3])
                    if a != b:
                        parents[b] = a
                        seeded[a] |= seeded[b]
                q += 1
        previous = current
    result = seed.copy()
    for y, start, end, owner, label in runs:
        if owner > 0 and seeded[root(label)]:
            result[y, start:end] = True
    return result


def classify(z, hit, domain, ownership, radius=2, epsilon=0.001, edge_z=0.08):
    if not (z.shape == hit.shape == domain.shape == ownership.shape):
        raise ValueError('Diagnostic dimensions differ')
    if not np.isfinite(z[domain & hit]).all():
        raise ValueError('Non-finite normal pixels')
    reversed_seed = domain & hit & (z < -epsilon)
    miss = domain & ~hit
    grown = _grow_connected(reversed_seed, domain & hit & (z <= edge_z), ownership)
    reasons = np.zeros(z.shape, dtype=np.uint8)
    reasons[reversed_seed] |= REVERSED
    reasons[miss] |= MISS
    reasons[grown & ~reversed_seed] |= EDGE
    core = reasons != 0
    padded = core.copy()
    # Ownership constraints prevent dilation into adjacent UV islands or overlaps.
    for _ in range(radius):
        previous = padded.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ys = slice(max(0, dy), z.shape[0] + min(0, dy))
            xs = slice(max(0, dx), z.shape[1] + min(0, dx))
            yt = slice(max(0, -dy), z.shape[0] + min(0, -dy))
            xt = slice(max(0, -dx), z.shape[1] + min(0, -dx))
            padded[yt, xt] |= previous[ys, xs] & domain[yt, xt] & (ownership[yt, xt] > 0) & (ownership[ys, xs] == ownership[yt, xt])
    reasons[padded & ~core] |= PADDING
    return reasons


def conservative_resize(mask, size):
    """Any-hit area resampling; even a single texel survives manual downsampling."""
    if mask.shape == (size, size):
        return mask
    height, width = mask.shape
    result = np.zeros((size, size), dtype=bool)
    # Accumulate source white texels into all destination cells they overlap.
    ys, xs = np.nonzero(mask)
    for y_offset in (0, 1):
        for x_offset in (0, 1):
            yy = (ys * size // height) if not y_offset else ((ys + 1) * size - 1) // height
            xx = (xs * size // width) if not x_offset else ((xs + 1) * size - 1) // width
            result[yy, xx] = True
    if size > min(height, width):
        # Manual mode is limited to downsampling by the host API.
        raise ValueError('Manual mask resolution cannot exceed the normal resolution')
    return result
