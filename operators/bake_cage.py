"""Bake cage helpers."""
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .bake_constants import (
    AUTO_CAGE_INTERSECTION_EPSILON,
)


def _evaluated_mesh(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    return evaluated, evaluated.to_mesh()


def _world_vertices(evaluated, mesh):
    matrix = evaluated.matrix_world
    return [matrix @ vertex.co for vertex in mesh.vertices]


def _mesh_world_diagonal(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    if not corners:
        return 0.0

    min_corner = Vector((
        min(corner.x for corner in corners),
        min(corner.y for corner in corners),
        min(corner.z for corner in corners),
    ))
    max_corner = Vector((
        max(corner.x for corner in corners),
        max(corner.y for corner in corners),
        max(corner.z for corner in corners),
    ))
    return (max_corner - min_corner).length


def _lowpoly_bvh(context, target):
    depsgraph = context.evaluated_depsgraph_get()
    evaluated, mesh = _evaluated_mesh(target, depsgraph)
    try:
        mesh.calc_loop_triangles()
        vertices = _world_vertices(evaluated, mesh)
        faces = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
        if not vertices or not faces:
            return None

        return BVHTree.FromPolygons(vertices, faces)
    finally:
        evaluated.to_mesh_clear()


def _highpoly_sample_points(context, sources, sample_limit):
    depsgraph = context.evaluated_depsgraph_get()
    points = []
    sample_limit = max(100, int(sample_limit))

    for source in sources:
        evaluated, mesh = _evaluated_mesh(source, depsgraph)
        try:
            mesh.calc_loop_triangles()
            vertices = _world_vertices(evaluated, mesh)
            points.extend(vertices)
            for triangle in mesh.loop_triangles:
                tri_vertices = [vertices[index] for index in triangle.vertices]
                center = (tri_vertices[0] + tri_vertices[1] + tri_vertices[2]) / 3.0
                points.append(center)
        finally:
            evaluated.to_mesh_clear()

    if len(points) <= sample_limit:
        return points

    stride = len(points) / sample_limit
    return [points[min(int(index * stride), len(points) - 1)] for index in range(sample_limit)]


def _percentile(sorted_values, percentile):
    if not sorted_values:
        return 0.0

    percentile = min(100.0, max(0.0, float(percentile)))
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (percentile / 100.0) * (len(sorted_values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    blend = position - lower_index
    return sorted_values[lower_index] * (1.0 - blend) + sorted_values[upper_index] * blend


def calculate_auto_cage(context, target, sources, settings):
    low_bvh = _lowpoly_bvh(context, target)
    if low_bvh is None:
        raise ValueError("Could not build lowpoly BVH")

    sample_points = _highpoly_sample_points(context, sources, settings.auto_cage_sample_limit)
    if not sample_points:
        raise ValueError("No highpoly sample points found")

    outward_distances = []
    inward_count = 0
    missed_count = 0
    for point in sample_points:
        nearest = low_bvh.find_nearest(point)
        if nearest is None:
            missed_count += 1
            continue

        low_point, low_normal, _face_index, _distance = nearest
        offset = point - low_point
        signed_distance = offset.dot(low_normal.normalized()) if low_normal.length else offset.length
        if signed_distance < -AUTO_CAGE_INTERSECTION_EPSILON:
            inward_count += 1
        outward_distances.append(max(0.0, signed_distance))

    if not outward_distances:
        raise ValueError("Could not compare lowpoly and highpoly surfaces")

    outward_distances.sort()
    base_value = _percentile(outward_distances, settings.auto_cage_coverage)
    target_diagonal = max(_mesh_world_diagonal(target), 0.000001)
    margin = max(settings.auto_cage_margin, target_diagonal * settings.auto_cage_margin_percent)
    safe_zone_multiplier = 1.0 + (settings.auto_cage_safe_zone / 100.0)
    max_limit = max(0.0, settings.auto_cage_max)
    cage_value = (base_value + margin) * safe_zone_multiplier
    if max_limit > 0.0:
        cage_value = min(cage_value, max_limit)

    coverage_distance = max(0.0, cage_value - margin)
    covered_count = sum(1 for distance in outward_distances if distance <= coverage_distance)
    coverage = (covered_count / len(outward_distances)) * 100.0
    outlier_count = max(0, len(outward_distances) - covered_count)

    return {
        "cage": cage_value,
        "coverage": coverage,
        "outliers": outlier_count,
        "intersections": inward_count,
        "missed": missed_count,
        "samples": len(sample_points),
        "safe_zone": settings.auto_cage_safe_zone,
        "max_distance": outward_distances[-1],
    }


def _apply_auto_cage_if_enabled(context, target, sources, settings, report):
    if getattr(settings, "autogenerate_smart_cage", False):
        from .smart_cage import prepare_bake
        return prepare_bake(context, target, sources, settings, report)
    if not settings.use_auto_cage:
        return True

    try:
        result = calculate_auto_cage(context, target, sources, settings)
    except ValueError as error:
        settings.auto_cage_status = f"AutoCage failed: {error}"
        report({"WARNING"}, settings.auto_cage_status)
        return False

    settings.cage_extrusion = result["cage"]
    settings.auto_cage_status = (
        f"Cage {result['cage']:.5f} m | Coverage {result['coverage']:.1f}% | "
        f"Safe {result['safe_zone']:.1f}% | Outliers {result['outliers']} | "
        f"Intersections {result['intersections']}"
    )
    report({"INFO"}, settings.auto_cage_status)
    return True
