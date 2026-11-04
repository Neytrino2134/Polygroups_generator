"""Foliage Card Generator core: highpoly silhouette -> low-poly alpha card mesh.

Pipeline (see docs/FOLIAGE_CARD_SPEC.md):
frame -> orthographic raycast mask/depth -> mask cleanup -> pixel contour trace ->
Douglas-Peucker simplify -> constrained Delaunay + depth-driven Steiner points -> 3D card.
Pure numpy/mathutils; the only bpy use is reading the evaluated source mesh.
"""
from collections import deque
from math import ceil

import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import delaunay_2d_cdt

AXIS_ITEMS = (
    ("AUTO", "Auto", "Thinnest principal direction of the mesh, snapped to a world axis when close"),
    ("X", "X", "Project along X (Right view)"),
    ("Y", "Y", "Project along Y (Front view)"),
    ("Z", "Z", "Project along Z (Top view)"),
    ("CAMERA", "Camera", "Project along the scene camera view direction"),
)
SIDE_ITEMS = (
    ("FRONT", "Front", "Card faces the standard view side (-Y for Front, +X for Right, +Z for Top)"),
    ("BACK", "Back", "Card faces the opposite side"),
)
DEPTH_MODE_ITEMS = (
    ("DEPTH_MAP", "Depth Map", "Place vertices on the highpoly surface along the projection axis"),
    ("SHRINKWRAP", "Shrinkwrap", "Depth map, then Shrinkwrap Nearest Surface with the offset"),
    ("FLAT", "Flat", "Keep the card planar in front of the highpoly"),
)
ISLAND_ITEMS = (
    ("JOIN", "One Object", "All leaves in one card object"),
    ("SEPARATE", "Object Per Leaf", "One card object per silhouette island"),
)

# Standard Blender view directions (camera looks along these): Right, Front, Top.
_VIEW_DIRECTION = {"X": Vector((-1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, -1))}
_VIEW_UP = {"X": Vector((0, 0, 1)), "Y": Vector((0, 0, 1)), "Z": Vector((0, 1, 0))}


class CardError(RuntimeError):
    pass


# --------------------------------------------------------------------------- frame

def _world_vertices(obj_eval, limit=200000):
    mesh = obj_eval.data
    count = len(mesh.vertices)
    co = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if count > limit:
        co = co[:: max(1, count // limit)]
    mw = np.array(obj_eval.matrix_world, dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3]


def projection_basis(points, axis="AUTO", side="FRONT", camera=None):
    """Return (U, V, D): screen right, screen up, view direction (camera looks along D)."""
    if axis == "CAMERA":
        if camera is None:
            raise CardError("Projection axis is Camera but the scene has no camera")
        rot = camera.matrix_world.to_quaternion()
        d = (rot @ Vector((0, 0, -1))).normalized()
        up = (rot @ Vector((0, 1, 0))).normalized()
    else:
        if axis == "AUTO":
            centered = points - points.mean(axis=0)
            _values, vectors = np.linalg.eigh(centered.T @ centered)
            normal = Vector(vectors[:, 0]).normalized()
            key = "XYZ"[int(np.argmax(np.abs(vectors[:, 0])))]
            reference = _VIEW_DIRECTION[key]
            if abs(normal.dot(reference)) > 0.9:
                normal = reference.copy()
            elif normal.dot(reference) < 0:
                normal.negate()
            d, up = normal, _VIEW_UP[key].copy()
        else:
            d, up = _VIEW_DIRECTION[axis].copy(), _VIEW_UP[axis].copy()
        if side == "BACK":
            d.negate()
    up = up - d * up.dot(d)
    if up.length < 1e-6:
        up = Vector((0, 1, 0)) - d * d.y
    up.normalize()
    u = up.cross(-d).normalized()
    v = (-d).cross(u).normalized()
    return u, v, d


# --------------------------------------------------------------------------- raycast

def raycast_mask(obj_eval, depsgraph, basis, resolution, margin):
    """Orthographic rays along D over a square frame. Returns frame dict, hit mask, depth map."""
    u_axis, v_axis, d_axis = basis
    pts = _world_vertices(obj_eval)
    pu, pv, pd = pts @ np.array(u_axis), pts @ np.array(v_axis), pts @ np.array(d_axis)
    size = max(pu.max() - pu.min(), pv.max() - pv.min())
    if size <= 0:
        raise CardError("Source mesh has no extent in the projection plane")
    size *= 1.0 + 2.0 * margin
    u0 = 0.5 * (pu.max() + pu.min()) - 0.5 * size
    v0 = 0.5 * (pv.max() + pv.min()) - 0.5 * size
    depth_min, depth_max = float(pd.min()), float(pd.max())
    frame = dict(u0=float(u0), v0=float(v0), size=float(size), px=size / resolution, res=resolution,
                 depth_min=depth_min, depth_max=depth_max, basis=basis)
    mask, depth = raycast_frame(obj_eval, depsgraph, frame, resolution)
    return frame, mask, depth


def frame_to_dict(frame):
    data = {key: frame[key] for key in ("u0", "v0", "size", "depth_min", "depth_max")}
    data["basis"] = [list(axis) for axis in frame["basis"]]
    return data


def frame_from_dict(data):
    frame = dict(data)
    frame["basis"] = tuple(Vector(axis) for axis in data["basis"])
    return frame


def raycast_frame(obj_eval, depsgraph, frame, resolution):
    """Hit mask + depth (along D) for a resolution x resolution grid over a stored frame.

    The grid matches card UVs 1:1, so the mask doubles as the card's alpha map."""
    u_axis, v_axis, d_axis = frame["basis"]
    u0, v0, size = frame["u0"], frame["v0"], frame["size"]
    depth_min, depth_max = frame["depth_min"], frame["depth_max"]
    px = size / resolution
    tree = BVHTree.FromObject(obj_eval, depsgraph)
    mw = obj_eval.matrix_world
    inv = mw.inverted()
    local_dir = (inv.to_3x3() @ d_axis).normalized()
    start = depth_min - 0.05 * size - (depth_max - depth_min)
    distance = (depth_max - start) * 4.0 + size
    mask = np.zeros((resolution, resolution), dtype=bool)
    depth = np.zeros((resolution, resolution), dtype=np.float64)
    ray_cast = tree.ray_cast
    inv3 = inv.to_3x3()
    local_base = inv @ (u_axis * float(u0) + v_axis * float(v0) + d_axis * start)
    step_u, step_v = inv3 @ (u_axis * px), inv3 @ (v_axis * px)
    local_distance = distance * (inv3 @ d_axis).length
    for iy in range(resolution):
        row_origin = local_base + step_v * (iy + 0.5) + step_u * 0.5
        mask_row, depth_row = mask[iy], depth[iy]
        for ix in range(resolution):
            location = ray_cast(row_origin + step_u * ix, local_dir, local_distance)[0]
            if location is not None:
                mask_row[ix] = True
                depth_row[ix] = (mw @ location).dot(d_axis)
    return mask, depth


# --------------------------------------------------------------------------- morphology

def _shift_or(mask, offsets):
    r = max(max(abs(dx), abs(dy)) for dx, dy in offsets)
    h, w = mask.shape
    padded = np.zeros((h + 2 * r, w + 2 * r), dtype=bool)
    padded[r:r + h, r:r + w] = mask
    out = np.zeros_like(mask)
    for dx, dy in offsets:
        out |= padded[r + dy:r + dy + h, r + dx:r + dx + w]
    return out


def dilate(mask, radius):
    radius = int(radius)
    if radius <= 0:
        return mask.copy()
    if radius <= 12:
        offsets = [(dx, dy) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)
                   if dx * dx + dy * dy <= radius * radius + radius]
        return _shift_or(mask, offsets)
    out = mask
    cross = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
    box = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    for index in range(radius):
        out = _shift_or(out, box if index % 2 else cross)
    return out


def erode(mask, radius):
    return ~dilate(~mask, radius)


def label(mask):
    """4-connected component labels (0 = background) and per-label sizes."""
    h, w = mask.shape
    flat = mask.ravel()
    labels = np.zeros(h * w, dtype=np.int32)
    sizes = [0]
    current = 0
    for start in np.flatnonzero(flat):
        if labels[start]:
            continue
        current += 1
        labels[start] = current
        queue = deque((start,))
        count = 0
        while queue:
            index = queue.popleft()
            count += 1
            x = index % w
            for neighbor, ok in ((index - 1, x > 0), (index + 1, x < w - 1),
                                 (index - w, index >= w), (index + w, index < h * w - w)):
                if ok and flat[neighbor] and not labels[neighbor]:
                    labels[neighbor] = current
                    queue.append(neighbor)
        sizes.append(count)
    return labels.reshape(h, w), np.array(sizes)


def clean_mask(hit, gap_close_px, min_island_area, cut_holes, min_hole_area):
    """Close gaps, drop small islands, fill holes (all, or only those below min_hole_area)."""
    mask = hit.copy()
    if gap_close_px > 0:
        mask = erode(dilate(mask, gap_close_px), gap_close_px)
    total = max(1, int(mask.sum()))
    labels, sizes = label(mask)
    keep = sizes >= max(1.0, min_island_area * total)
    keep[0] = False
    mask = keep[labels]
    background, bg_sizes = label(~mask)
    border = set(np.unique(np.concatenate((background[0], background[-1], background[:, 0], background[:, -1]))))
    total = max(1, int(mask.sum()))
    fill = np.zeros(len(bg_sizes), dtype=bool)
    for index in range(1, len(bg_sizes)):
        if index not in border and (not cut_holes or bg_sizes[index] < min_hole_area * total):
            fill[index] = True
    return mask | fill[background]


# --------------------------------------------------------------------------- contour

def trace_contours(mask):
    """Pixel-boundary loops (lattice corners) with the filled region on the left.

    Outer boundaries are CCW, holes CW. Saddles prefer a left turn, keeping diagonal
    pixels in separate loops (4-connectivity)."""
    h, w = mask.shape
    m = np.zeros((h + 2, w + 2), dtype=bool)
    m[1:-1, 1:-1] = mask
    outgoing = {}

    def add(edges, sx, sy, ex, ey):
        for x, y in edges:
            outgoing.setdefault((x + sx, y + sy), []).append((x + ex, y + ey))

    core = m[1:-1, 1:-1]
    ys, xs = np.nonzero(core & ~m[:-2, 1:-1])     # below empty -> bottom edge, +x
    add(zip(xs.tolist(), ys.tolist()), 0, 0, 1, 0)
    ys, xs = np.nonzero(core & ~m[2:, 1:-1])      # above empty -> top edge, -x
    add(zip(xs.tolist(), ys.tolist()), 1, 1, 0, 1)
    ys, xs = np.nonzero(core & ~m[1:-1, :-2])     # left empty -> left edge, -y
    add(zip(xs.tolist(), ys.tolist()), 0, 1, 0, 0)
    ys, xs = np.nonzero(core & ~m[1:-1, 2:])      # right empty -> right edge, +y
    add(zip(xs.tolist(), ys.tolist()), 1, 0, 1, 1)

    loops = []
    while outgoing:
        start = next(iter(outgoing))
        loop = [start]
        current = start
        direction = None
        while True:
            targets = outgoing[current]
            if len(targets) == 1 or direction is None:
                target = targets.pop(0)
            else:
                dx, dy = direction
                priority = ((-dy, dx), (dx, dy), (dy, -dx))  # left, straight, right
                target = None
                for want in priority:
                    for candidate in targets:
                        if (candidate[0] - current[0], candidate[1] - current[1]) == want:
                            target = candidate
                            break
                    if target is not None:
                        break
                targets.remove(target)
            if not targets:
                del outgoing[current]
            direction = (target[0] - current[0], target[1] - current[1])
            current = target
            if current == start:
                break
            loop.append(current)
        if len(loop) >= 4:
            loops.append(np.array(loop, dtype=np.float64))
    return loops


def _signed_area(points):
    x, y = points[:, 0], points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _douglas_peucker_keep(points, tolerance):
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        a, b = points[first], points[last]
        segment = b - a
        length = np.hypot(*segment)
        chunk = points[first + 1:last] - a
        if length < 1e-12:
            dist = np.hypot(chunk[:, 0], chunk[:, 1])
        else:
            dist = np.abs(segment[0] * chunk[:, 1] - segment[1] * chunk[:, 0]) / length
        index = int(np.argmax(dist))
        if dist[index] > tolerance:
            split = first + 1 + index
            keep[split] = True
            stack.append((first, split))
            stack.append((split, last))
    return keep


def _line_intersection(p1, d1, p2, d2):
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cross) < 1e-9:
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / cross
    return p1 + d1 * t


def simplify_loop(loop, tolerance, padding):
    """Closed Douglas-Peucker on pixel-edge midpoints, made conservative.

    Every simplified edge is pushed outward (to the right: traced loops keep the filled
    region on the left) just far enough to cover the points it skipped, plus padding.
    No mask dilation is needed, so narrow gaps between lobes survive as wedges."""
    mid = 0.5 * (loop + np.roll(loop, -1, axis=0))
    n = len(mid)
    far = int(np.argmax(np.hypot(*(mid - mid[0]).T)))
    keep = np.zeros(n, dtype=bool)
    keep[:far + 1] |= _douglas_peucker_keep(mid[:far + 1], tolerance)
    second = _douglas_peucker_keep(np.vstack((mid[far:], mid[:1])), tolerance)
    keep[far:] |= second[:-1]
    kept = np.flatnonzero(keep)
    if len(kept) < 3:
        return None
    m = len(kept)
    origins, directions, normals, shifts = [], [], [], []
    for i in range(m):
        a_index, b_index = kept[i], kept[(i + 1) % m]
        a, b = mid[a_index], mid[b_index]
        d = b - a
        length = float(np.hypot(*d))
        if length < 1e-9:
            d, length = np.array([1.0, 0.0]), 1.0
        d = d / length
        right = np.array([d[1], -d[0]])
        if b_index > a_index:
            skipped = mid[a_index + 1:b_index]
        else:
            skipped = np.vstack((mid[a_index + 1:], mid[:b_index]))
        outside = 0.0
        if len(skipped):
            signed_left = (skipped - a) @ np.array([-d[1], d[0]])
            outside = max(0.0, -float(signed_left.min()))
        shift = outside + padding
        origins.append(a + right * shift)
        directions.append(d)
        normals.append(right)
        shifts.append(shift)
    result = np.empty((m, 2))
    for i in range(m):
        prev = i - 1
        point = _line_intersection(origins[prev], directions[prev], origins[i], directions[i])
        corner = mid[kept[i]]
        limit = 3.0 * max(shifts[prev], shifts[i]) + 1.0
        if point is None or np.hypot(*(point - corner)) > limit:
            bisector = normals[prev] + normals[i]
            norm = np.hypot(*bisector)
            bisector = bisector / norm if norm > 1e-9 else normals[i]
            point = corner + bisector * max(shifts[prev], shifts[i])
        result[i] = point
    return result


def build_outline(mask, padding_px, tolerance):
    """Conservative simplified outline loops (lattice coordinates)."""
    loops = []
    for loop in trace_contours(mask):
        simple = simplify_loop(loop, tolerance, padding_px)
        if simple is not None and abs(_signed_area(simple)) > 4.0:
            loops.append(simple)
    return mask, loops


def group_components(loops):
    """Assign hole loops (CW) to the outer loop (CCW) that contains them."""
    outers = [loop for loop in loops if _signed_area(loop) > 0]
    holes = [loop for loop in loops if _signed_area(loop) <= 0]
    components = [[outer] for outer in outers]
    for hole in holes:
        point = hole[0]
        for component in sorted(components, key=lambda item: abs(_signed_area(item[0]))):
            if _points_in_loops(point[None, :], [component[0]])[0]:
                component.append(hole)
                break
    return components


def outline_triangle_count(components):
    return sum(sum(len(loop) for loop in comp) + 2 * (len(comp) - 1) - 2 for comp in components)


# --------------------------------------------------------------------------- triangulation

def _points_in_loops(points, loops):
    """Non-zero winding point-in-polygon over several loops (outer CCW, holes CW).

    Non-zero (not even-odd) keeps areas where outward-shifted edges overlap inside the card."""
    winding = np.zeros(len(points), dtype=np.int64)
    px, py = points[:, 0][:, None], points[:, 1][:, None]
    for loop in loops:
        a = loop
        b = np.roll(loop, -1, axis=0)
        ax, ay, bx, by = a[:, 0][None, :], a[:, 1][None, :], b[:, 0][None, :], b[:, 1][None, :]
        side = (bx - ax) * (py - ay) - (px - ax) * (by - ay)
        up = (ay <= py) & (by > py) & (side > 0)
        down = (ay > py) & (by <= py) & (side < 0)
        winding += up.sum(axis=1) - down.sum(axis=1)
    return winding != 0


def triangulate(component, steiner):
    """CDT over the component loops + interior points; keep triangles inside (even-odd)."""
    coords, edges = [], []
    for loop in component:
        offset = len(coords)
        coords.extend(Vector((float(x), float(y))) for x, y in loop)
        n = len(loop)
        edges.extend((offset + i, offset + (i + 1) % n) for i in range(n))
    coords.extend(Vector((float(x), float(y))) for x, y in steiner)
    verts, _edges, faces, _ov, _oe, _of = delaunay_2d_cdt(coords, edges, [], 0, 1e-5, False)
    verts = np.array([(v.x, v.y) for v in verts], dtype=np.float64)
    tris = np.array([face for face in faces if len(face) == 3], dtype=np.int64).reshape(-1, 3)
    if not len(tris):
        return verts, tris
    centroids = verts[tris].mean(axis=1)
    tris = tris[_points_in_loops(centroids, component)]
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    tris[cross < 0] = tris[cross < 0][:, ::-1]
    tris = tris[np.abs(cross) > 1e-9]
    used = np.unique(tris)
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[tris]


def refine_by_depth(component, depth, valid, tolerance, max_points, stride):
    """Insert interior vertices where the planar card deviates from the depth map."""
    steiner = []
    verts, tris = triangulate(component, steiner)
    if max_points <= 0 or tolerance <= 0:
        return verts, tris
    gy, gx = np.mgrid[0:depth.shape[0]:stride, 0:depth.shape[1]:stride]
    sample_depth = depth[gy, gx]
    sample_valid = valid[gy, gx]
    cx, cy = gx + 0.5, gy + 0.5   # pixel centers in lattice coordinates
    while len(steiner) < max_points:
        vdepth = sample_bilinear(depth, verts)
        best = []
        for tri in tris:
            a, b, c = verts[tri]
            lo = np.maximum(np.floor(np.minimum(np.minimum(a, b), c) / stride).astype(int), 0)
            hi = np.ceil(np.maximum(np.maximum(a, b), c) / stride).astype(int) + 1
            sx, sy = cx[lo[1]:hi[1], lo[0]:hi[0]], cy[lo[1]:hi[1], lo[0]:hi[0]]
            if not sx.size:
                continue
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-9:
                continue
            w0 = ((b[1] - c[1]) * (sx - c[0]) + (c[0] - b[0]) * (sy - c[1])) / det
            w1 = ((c[1] - a[1]) * (sx - c[0]) + (a[0] - c[0]) * (sy - c[1])) / det
            w2 = 1.0 - w0 - w1
            # stay away from edges to avoid slivers
            inside = (w0 > 0.12) & (w1 > 0.12) & (w2 > 0.12) & sample_valid[lo[1]:hi[1], lo[0]:hi[0]]
            if not inside.any():
                continue
            plane = w0 * vdepth[tri[0]] + w1 * vdepth[tri[1]] + w2 * vdepth[tri[2]]
            error = np.where(inside, np.abs(plane - sample_depth[lo[1]:hi[1], lo[0]:hi[0]]), -1.0)
            index = np.unravel_index(int(np.argmax(error)), error.shape)
            if error[index] > tolerance:
                best.append((float(error[index]), float(sx[index]), float(sy[index])))
        if not best:
            break
        best.sort(reverse=True)
        room = max_points - len(steiner)
        steiner.extend((x, y) for _e, x, y in best[:max(1, min(room, (len(best) + 1) // 2))])
        verts, tris = triangulate(component, steiner)
    return verts, tris


# --------------------------------------------------------------------------- depth

def fill_depth(depth, hit, iterations):
    """Extend hit depths outward (nearest-ish) so padded outline vertices get a sane depth."""
    value = np.where(hit, depth, 0.0)
    known = hit.copy()
    h, w = depth.shape
    for _ in range(iterations):
        if known.all():
            break
        pv = np.pad(value, 1)
        pk = np.pad(known, 1).astype(np.float64)
        total = pv[:-2, 1:-1] * pk[:-2, 1:-1] + pv[2:, 1:-1] * pk[2:, 1:-1] \
            + pv[1:-1, :-2] * pk[1:-1, :-2] + pv[1:-1, 2:] * pk[1:-1, 2:]
        count = pk[:-2, 1:-1] + pk[2:, 1:-1] + pk[1:-1, :-2] + pk[1:-1, 2:]
        grow = (~known) & (count > 0)
        value[grow] = total[grow] / count[grow]
        known |= grow
    if not known.all():
        value[~known] = np.median(depth[hit]) if hit.any() else 0.0
    return value


def smooth_depth(depth, iterations):
    for _ in range(int(iterations)):
        p = np.pad(depth, 1, mode="edge")
        depth = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + 4.0 * p[1:-1, 1:-1]) / 8.0
    return depth


def sample_bilinear(image, points):
    """Sample at lattice coordinates (pixel corner origin)."""
    h, w = image.shape
    fx = np.clip(points[:, 0] - 0.5, 0, w - 1.001)
    fy = np.clip(points[:, 1] - 0.5, 0, h - 1.001)
    x0, y0 = fx.astype(int), fy.astype(int)
    tx, ty = fx - x0, fy - y0
    return (image[y0, x0] * (1 - tx) * (1 - ty) + image[y0, x0 + 1] * tx * (1 - ty)
            + image[y0 + 1, x0] * (1 - tx) * ty + image[y0 + 1, x0 + 1] * tx * ty)


# --------------------------------------------------------------------------- driver

def build_card(obj_eval, depsgraph, *, axis="AUTO", side="FRONT", camera=None, margin=0.02,
               resolution=512, gap_close_px=0, min_island_area=0.005, cut_holes=False,
               min_hole_area=0.02, padding_px=2, triangle_limit=200, outline_tolerance=1.5,
               depth_tolerance=0.003, depth_smoothing=1, surface_offset=0.011, depth_mode="DEPTH_MAP",
               steiner_share=0.2):
    """Return dict(frame, mask, components=[(world_verts Nx3, tris Mx3, uvs Nx2), ...], stats)."""
    points = _world_vertices(obj_eval, 50000)
    basis = projection_basis(points, axis, side, camera)
    frame, hit, depth = raycast_mask(obj_eval, depsgraph, basis, resolution, margin)
    if not hit.any():
        raise CardError("No ray hit the source mesh; check the projection axis")
    mask = clean_mask(hit, gap_close_px, min_island_area, cut_holes, min_hole_area)

    def outline(tol):
        grown, loops = build_outline(mask, padding_px, tol)
        return grown, group_components(loops)

    tolerance = max(0.25, outline_tolerance)
    grown, components = outline(tolerance)
    if not components:
        raise CardError("Silhouette produced no outline")
    steiner_budget = 0
    if triangle_limit > 0:
        outline_budget = max(len(components), int(triangle_limit * (1.0 - steiner_share)))
        if outline_triangle_count(components) > outline_budget:
            low, high = tolerance, tolerance
            while outline_triangle_count(components) > outline_budget and high < resolution / 4:
                low, high = high, high * 2.0
                grown, components = outline(high)
            for _ in range(8):
                middle = 0.5 * (low + high)
                g, c = outline(middle)
                if outline_triangle_count(c) > outline_budget:
                    low = middle
                else:
                    high, grown, components = middle, g, c
            tolerance = high
        steiner_budget = max(0, (triangle_limit - outline_triangle_count(components)) // 2)
    else:
        steiner_budget = 10 ** 6

    filled = fill_depth(depth, hit, padding_px + 24 + resolution // 32)
    filled = smooth_depth(filled, depth_smoothing)
    stride = max(1, resolution // 160)
    u_axis, v_axis, d_axis = (np.array(axis_vec) for axis_vec in basis)
    px, u0, v0 = frame["px"], frame["u0"], frame["v0"]
    flat_depth = float(depth[hit].min())
    mode_tol = depth_tolerance if depth_mode != "FLAT" else 0.0

    def triangulate_all(comps, budget):
        total_area = sum(abs(_signed_area(comp[0])) for comp in comps) or 1.0
        built = []
        for comp in comps:
            share = abs(_signed_area(comp[0])) / total_area
            points_budget = int(round(budget * share)) if triangle_limit > 0 else 10 ** 6
            verts2d, tris = refine_by_depth(comp, filled, hit, mode_tol, points_budget, stride)
            if len(tris):
                built.append((verts2d, tris))
        return built

    built = triangulate_all(components, steiner_budget)
    # Edge crossings and merged CDT vertices make the estimate inexact: trim to the budget.
    for _ in range(12):
        excess = sum(len(t) for _v, t in built) - triangle_limit
        if triangle_limit <= 0 or excess <= 0:
            break
        if steiner_budget > 0:
            steiner_budget = max(0, steiner_budget - (excess + 1) // 2)
        else:
            tolerance *= 1.15
            grown, components = outline(tolerance)
        built = triangulate_all(components, steiner_budget)

    results = []
    for verts2d, tris in built:
        if depth_mode == "FLAT":
            vdepth = np.full(len(verts2d), flat_depth)
        else:
            vdepth = sample_bilinear(filled, verts2d)
        vdepth = vdepth - surface_offset
        wu = u0 + verts2d[:, 0] * px
        wv = v0 + verts2d[:, 1] * px
        world = wu[:, None] * u_axis + wv[:, None] * v_axis + vdepth[:, None] * d_axis
        uvs = np.column_stack((verts2d[:, 0] / resolution, verts2d[:, 1] / resolution))
        results.append((world, tris, uvs))

    # Fraction of silhouette pixels (sampled) not covered by any card polygon.
    hy, hx = np.nonzero(hit[::stride, ::stride])
    centers = np.column_stack((hx * stride + 0.5, hy * stride + 0.5)).astype(np.float64)
    covered = np.zeros(len(centers), dtype=bool)
    for comp in components:
        covered |= _points_in_loops(centers, comp)
    coverage = float((~covered).sum()) / max(1, len(centers))
    stats = dict(
        triangles=sum(len(t) for _w, t, _u in results),
        islands=len(results),
        tolerance_px=tolerance,
        hit_pixels=int(hit.sum()),
        uncovered_fraction=coverage,
    )
    return dict(frame=frame, mask=mask, hit=hit, grown=grown, components=results, stats=stats)


def to_local(world, matrix_world):
    inv = np.array(Matrix(matrix_world).inverted(), dtype=np.float64)
    return world @ inv[:3, :3].T + inv[:3, 3]
