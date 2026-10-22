"""Bake geometry helpers."""
from array import array
from mathutils import Vector
from .bake_constants import (
    BAKE_ARTIFACT_IMAGE_PROP,
)
from .bake_images import (
    _ensure_target_image,
    _write_pixels,
)


def _segment_triangle_hit(start, end, a, b, c):
    """Double-sided segment/triangle intersection, including both endpoints."""
    direction = end - start
    edge_a, edge_b = b - a, c - a
    cross = direction.cross(edge_b)
    determinant = edge_a.dot(cross)
    if abs(determinant) < 1e-12:
        return None
    inverse = 1.0 / determinant
    offset = start - a
    u = offset.dot(cross) * inverse
    if u < -1e-7 or u > 1.0000001:
        return None
    q = offset.cross(edge_a)
    v = direction.dot(q) * inverse
    if v < -1e-7 or u + v > 1.0000001:
        return None
    t = edge_b.dot(q) * inverse
    if t < -1e-7 or t > 1.0000001:
        return None
    return start + direction * t


def _triangle_intersection_points(first, second):
    hits = []
    for source, target in ((first, second), (second, first)):
        for index in range(3):
            point = _segment_triangle_hit(
                source[index], source[(index + 1) % 3], *target,
            )
            if point is not None and all((point - existing).length_squared > 1e-12 for existing in hits):
                hits.append(point)
    return hits


def _paint_intersection(mask, resolution, radius, target, cage_points, cage_triangle, index, hits):
    """Project a cage intersection segment through matching lowpoly UV loops."""
    if not hits:
        return
    a, b, c = (cage_points[vertex] for vertex in cage_triangle)
    edge_a, edge_b = b - a, c - a
    aa, ab, bb = edge_a.dot(edge_a), edge_a.dot(edge_b), edge_b.dot(edge_b)
    denominator = aa * bb - ab * ab
    if abs(denominator) < 1e-20:
        return
    uv_layer = target.data.uv_layers.active
    uv = [uv_layer.data[loop].uv for loop in target.data.loop_triangles[index].loops]
    mapped = []
    for hit in hits:
        offset = hit - a
        ac, bc = offset.dot(edge_a), offset.dot(edge_b)
        weight_b = (bb * ac - ab * bc) / denominator
        weight_c = (aa * bc - ab * ac) / denominator
        weight_a = 1.0 - weight_b - weight_c
        mapped.append((
            (uv[0].x * weight_a + uv[1].x * weight_b + uv[2].x * weight_c) * resolution,
            (uv[0].y * weight_a + uv[1].y * weight_b + uv[2].y * weight_c) * resolution,
        ))
    if len(mapped) > 2:
        first, second = max(
            ((one, two) for one in mapped for two in mapped),
            key=lambda pair: (pair[0][0] - pair[1][0]) ** 2 + (pair[0][1] - pair[1][1]) ** 2,
        )
    elif len(mapped) == 2:
        first, second = mapped
    else:
        first = second = mapped[0]
    steps = max(1, int(max(abs(second[0] - first[0]), abs(second[1] - first[1])) * 2))
    for step in range(steps + 1):
        factor = step / steps
        center_x = round(first[0] + (second[0] - first[0]) * factor - 0.5)
        center_y = round(first[1] + (second[1] - first[1]) * factor - 0.5)
        for y in range(max(0, center_y - radius), min(resolution, center_y + radius + 1)):
            for x in range(max(0, center_x - radius), min(resolution, center_x + radius + 1)):
                if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius * radius:
                    mask[y * resolution + x] = 255


def _inside_closed_mesh(point, bvh, direction, epsilon):
    """Odd ray-hit count means the cage point is inside the highpoly shell."""
    origin = point + direction * epsilon
    hits = 0
    for _ in range(128):
        location, _normal, _face, _distance = bvh.ray_cast(origin, direction)
        if location is None:
            break
        hits += 1
        origin = location + direction * epsilon
    return hits % 2 == 1


def _inside_open_mesh_estimate(point, bvh, epsilon):
    nearest = bvh.find_nearest(point)
    if nearest is None:
        return False
    location, normal, _face, _distance = nearest
    return (point - location).dot(normal) < -epsilon


def _fill_cage_area_inside_mesh(mask, resolution, target, cage_points, cage_triangle, index, other_tree, epsilon, offset_surface=False, closed_mesh=True):
    """Test UV texel centers on a cage face instead of painting its whole UV face."""
    uv_layer = target.data.uv_layers.active
    uv = [uv_layer.data[loop].uv for loop in target.data.loop_triangles[index].loops]
    ax, ay = uv[0].x * resolution, uv[0].y * resolution
    bx, by = uv[1].x * resolution, uv[1].y * resolution
    cx, cy = uv[2].x * resolution, uv[2].y * resolution
    determinant = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(determinant) < 1e-12:
        return
    a, b, c = (cage_points[vertex] for vertex in cage_triangle)
    direction = Vector((0.934, 0.293, 0.204)).normalized()
    normal = (b - a).cross(c - a).normalized() if offset_surface else None
    for y in range(max(0, int(min(ay, by, cy))), min(resolution, int(max(ay, by, cy)) + 1)):
        py = y + 0.5
        for x in range(max(0, int(min(ax, bx, cx))), min(resolution, int(max(ax, bx, cx)) + 1)):
            px = x + 0.5
            weight_a = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / determinant
            weight_b = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / determinant
            weight_c = 1.0 - weight_a - weight_b
            if min(weight_a, weight_b, weight_c) < -1e-6:
                continue
            point = a * weight_a + b * weight_b + c * weight_c
            if normal is not None:
                point += normal * (epsilon * 4)
            inside = (
                _inside_closed_mesh(point, other_tree, direction, epsilon)
                if closed_mesh else _inside_open_mesh_estimate(point, other_tree, epsilon)
            )
            if inside:
                mask[y * resolution + x] = 255


def _generate_legacy_geometric_artifact_mask(context, target, sources, settings, resolution_override=None, include_source=True, radius_override=None):
    """Project cage/highpoly and cage/self intersection curves into lowpoly UV."""
    from .smart_cage import closed, geometry, sources_geometry, tree

    if not settings.bake_artifact_mask:
        return None
    cage = settings.smart_cage_object if settings.autogenerate_smart_cage else None
    diagnostic_mesh = cage if cage is not None else target
    points, triangles, _faces = geometry(context, diagnostic_mesh)
    if cage is None and settings.use_selected_to_active and settings.cage_extrusion > 0:
        # Blender's automatic cage is not exposed as a mesh. Approximate its
        # vertex-normal extrusion for this geometric diagnostic.
        normals = [Vector((0.0, 0.0, 0.0)) for _ in points]
        for a, b, c in triangles:
            normal = (points[b] - points[a]).cross(points[c] - points[a])
            for vertex in (a, b, c):
                normals[vertex] += normal
        points = [
            point + normal.normalized() * settings.cage_extrusion if normal.length else point
            for point, normal in zip(points, normals)
        ]
    target.data.calc_loop_triangles()
    target_triangles = target.data.loop_triangles
    if len(triangles) != len(target_triangles) or any(
        triangle != tuple(target_triangles[index].vertices)
        for index, triangle in enumerate(triangles)
    ):
        raise ValueError("Cage/target evaluated topology differs from target UV topology")
    if not triangles:
        raise ValueError("Target has no triangles")
    if target.data.uv_layers.active is None:
        raise ValueError("Target has no active UV map")
    high_points, high_triangles = sources_geometry(context, sources)
    cage_tree = tree(points, triangles)
    high_tree = tree(high_points, high_triangles)
    resolution = settings.bake_artifact_resolution if resolution_override is None else resolution_override
    radius = settings.bake_artifact_radius if radius_override is None else radius_override
    mask = bytearray(resolution * resolution)
    intersection_count = 0
    high_faces_to_fill = set()
    self_faces_to_fill = set()
    for cage_index, high_index in (cage_tree.overlap(high_tree) if include_source else []):
        hits = _triangle_intersection_points(
            [points[vertex] for vertex in triangles[cage_index]],
            [high_points[vertex] for vertex in high_triangles[high_index]],
        )
        if hits:
            _paint_intersection(mask, resolution, radius, target, points, triangles[cage_index], cage_index, hits)
            high_faces_to_fill.add(cage_index)
            intersection_count += 1
    if settings.bake_artifact_self_intersections:
        for first, second in cage_tree.overlap(cage_tree):
            if first < second and not set(triangles[first]).intersection(triangles[second]):
                hits = _triangle_intersection_points(
                    [points[vertex] for vertex in triangles[first]],
                    [points[vertex] for vertex in triangles[second]],
                )
                if hits:
                    for index in (first, second):
                        _paint_intersection(mask, resolution, radius, target, points, triangles[index], index, hits)
                        self_faces_to_fill.add(index)
                    intersection_count += 1
    epsilon = max(1e-7, max((point - high_points[0]).length for point in high_points) * 1e-7)
    high_is_closed = closed(high_triangles)
    cage_is_closed = closed(triangles) if self_faces_to_fill else False
    for index in high_faces_to_fill:
        _fill_cage_area_inside_mesh(
            mask, resolution, target, points, triangles[index], index, high_tree, epsilon,
            closed_mesh=high_is_closed,
        )
    for index in self_faces_to_fill:
        _fill_cage_area_inside_mesh(
            mask, resolution, target, points, triangles[index], index, cage_tree, epsilon,
            offset_surface=True, closed_mesh=cage_is_closed,
        )
    pixels = array("f", [0.0]) * (resolution * resolution * 4)
    for index, value in enumerate(mask):
        color = value / 255.0
        offset = index * 4
        pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = color
        pixels[offset + 3] = 1.0
    image = _ensure_target_image(
        target, settings, BAKE_ARTIFACT_IMAGE_PROP, "ArtifactMask", "Non-Color",
        generated_color=(0.0, 0.0, 0.0, 1.0),
        resolution=resolution,
    )
    _write_pixels(image, pixels)
    return image, intersection_count
