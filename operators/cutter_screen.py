"""Screen-space picking, axis locks and cutter section geometry."""
import bpy
from math import atan2, cos, sin, tau
from mathutils import Vector


def _view3d_under_mouse(context, event):
    screen = context.window.screen
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue

        region = next((item for item in area.regions if item.type == "WINDOW"), None)
        space = next((item for item in area.spaces if item.type == "VIEW_3D"), None)
        if region is None or space is None or space.region_3d is None:
            continue

        inside_x = region.x <= event.mouse_x < region.x + region.width
        inside_y = region.y <= event.mouse_y < region.y + region.height
        if inside_x and inside_y:
            region_pos = (event.mouse_x - region.x, event.mouse_y - region.y)
            return area, region, space.region_3d, region_pos

    return None, None, None, None


def _target_bounds(target):
    corners = [target.matrix_world @ Vector(corner) for corner in target.bound_box]
    center = sum(corners, Vector()) / len(corners)
    diagonal = max((corner - center).length for corner in corners) * 2.0
    return center, max(diagonal, 1.0)


def _axis_lock_mode(start_pos, end_pos):
    start = Vector(start_pos)
    end = Vector(end_pos)
    delta = end - start
    if abs(delta.x) >= abs(delta.y):
        return "HORIZONTAL"
    return "VERTICAL"


def _axis_locked_region_pos(start_pos, end_pos, enabled):
    if not enabled:
        return end_pos

    start = Vector(start_pos)
    end = Vector(end_pos)
    if _axis_lock_mode(start, end) == "HORIZONTAL":
        return (end.x, start.y)
    return (start.x, end.y)


def _surface_hit_from_region_pos(region, rv3d, region_pos, target):
    from bpy_extras import view3d_utils

    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, region_pos)
    ray_direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, region_pos)
    if ray_direction.length < 0.000001:
        return None
    ray_direction.normalize()

    matrix_inv = target.matrix_world.inverted()
    local_origin = matrix_inv @ ray_origin
    local_direction = matrix_inv.to_3x3() @ ray_direction
    if local_direction.length < 0.000001:
        return None
    local_direction.normalize()

    hit, location, normal, face_index = target.ray_cast(local_origin, local_direction)
    if not hit:
        return None

    world_location = target.matrix_world @ location
    world_normal = target.matrix_world.to_3x3().inverted().transposed() @ normal
    if world_normal.length < 0.000001:
        return None
    world_normal.normalize()
    return world_location, world_normal, face_index


def _target_ray_cast_world(target, origin, direction):
    if direction.length < 0.000001:
        return None
    direction = direction.normalized()

    matrix_inv = target.matrix_world.inverted()
    local_origin = matrix_inv @ origin
    local_direction = matrix_inv.to_3x3() @ direction
    if local_direction.length < 0.000001:
        return None
    local_direction.normalize()

    hit, location, normal, face_index = target.ray_cast(local_origin, local_direction)
    if not hit:
        return None

    world_location = target.matrix_world @ location
    world_normal = target.matrix_world.to_3x3().inverted().transposed() @ normal
    if world_normal.length > 0.000001:
        world_normal.normalize()
    return world_location, world_normal, face_index


def _screen_cut_plane(area, region, rv3d, start_pos, end_pos, target, size_multiplier):
    del area
    from bpy_extras import view3d_utils

    start = Vector(start_pos)
    end = Vector(end_pos)
    if (end - start).length < 2.0:
        return None

    target_center, target_diagonal = _target_bounds(target)
    start_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, start)
    end_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, end)
    start_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, start)
    end_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, end)

    if rv3d.is_perspective:
        plane_co = start_origin
        plane_no = start_vector.cross(end_vector)
    else:
        plane_co = start_origin
        plane_no = (end_origin - start_origin).cross(start_vector)

    if plane_no.length < 0.000001:
        return None

    plane_no.normalize()
    center = target_center - plane_no * (target_center - plane_co).dot(plane_no)

    start_depth = view3d_utils.region_2d_to_location_3d(region, rv3d, start, target_center)
    end_depth = view3d_utils.region_2d_to_location_3d(region, rv3d, end, target_center)
    axis_a = end_depth - start_depth
    if axis_a.length < 0.000001:
        axis_a = plane_no.cross(start_vector)
    if axis_a.length < 0.000001:
        return None
    axis_a.normalize()

    axis_b = plane_no.cross(axis_a)
    if axis_b.length < 0.000001:
        return None
    axis_b.normalize()

    size = target_diagonal * size_multiplier
    return center, axis_a, axis_b, size


def _arc_center_2d(a, b, c):
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    cx, cy = c.x, c.y
    determinant = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(determinant) < 0.000001:
        return None

    a_sq = ax * ax + ay * ay
    b_sq = bx * bx + by * by
    c_sq = cx * cx + cy * cy
    ux = (a_sq * (by - cy) + b_sq * (cy - ay) + c_sq * (ay - by)) / determinant
    uy = (a_sq * (cx - bx) + b_sq * (ax - cx) + c_sq * (bx - ax)) / determinant
    return Vector((ux, uy))


def _angle_delta_ccw(start_angle, end_angle):
    return (end_angle - start_angle) % tau


def _screen_arc_points(start_pos, middle_pos, end_pos, segments):
    start = Vector(start_pos)
    middle = Vector(middle_pos)
    end = Vector(end_pos)
    center = _arc_center_2d(start, middle, end)
    if center is None:
        return None

    radius = (start - center).length
    if radius < 2.0:
        return None

    start_angle = atan2(start.y - center.y, start.x - center.x)
    middle_angle = atan2(middle.y - center.y, middle.x - center.x)
    end_angle = atan2(end.y - center.y, end.x - center.x)

    ccw_total = _angle_delta_ccw(start_angle, end_angle)
    ccw_to_middle = _angle_delta_ccw(start_angle, middle_angle)
    if ccw_to_middle <= ccw_total:
        total = ccw_total
    else:
        total = ccw_total - tau

    if abs(total) < 0.000001 or abs(abs(total) - tau) < 0.000001:
        return None

    points = []
    for index in range(segments + 1):
        angle = start_angle + total * (index / segments)
        points.append(
            (
                center.x + radius * cos(angle),
                center.y + radius * sin(angle),
            )
        )
    return points


def _screen_arc_surface(area, region, rv3d, start_pos, middle_pos, end_pos, target, size_multiplier, segments):
    del area
    from bpy_extras import view3d_utils

    arc_points = _screen_arc_points(start_pos, middle_pos, end_pos, segments)
    if arc_points is None:
        return None

    target_center, target_diagonal = _target_bounds(target)
    center_points = [
        view3d_utils.region_2d_to_location_3d(region, rv3d, Vector(point), target_center)
        for point in arc_points
    ]
    if len(center_points) < 2:
        return None

    region_center = Vector((region.width * 0.5, region.height * 0.5))
    depth_axis = view3d_utils.region_2d_to_vector_3d(region, rv3d, region_center)
    if depth_axis.length < 0.000001:
        return None
    depth_axis.normalize()

    return center_points, depth_axis, target_diagonal * size_multiplier


def _screen_section_plane(context, region, rv3d, start_pos, end_pos, target):
    from bpy_extras import view3d_utils

    start, end = Vector(start_pos), Vector(end_pos)
    if (end - start).length < 2.0:
        raise ValueError("Place the two points farther apart, across the local section")
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = target.evaluated_get(depsgraph)
    # Search from the middle of the drawn line outwards; endpoints may be
    # outside the silhouette, just as with Local Ring.
    seed = None
    for step in sorted(range(65), key=lambda i: abs(i - 32)):
        hit = _surface_hit_from_region_pos(region, rv3d, start.lerp(end, step / 64), evaluated)
        if hit is not None:
            seed = hit[0]
            break
    if seed is None:
        raise ValueError("The line must cross the visible surface of the target mesh")
    ray_a = view3d_utils.region_2d_to_vector_3d(region, rv3d, start)
    ray_b = view3d_utils.region_2d_to_vector_3d(region, rv3d, end)
    if rv3d.is_perspective:
        normal = ray_a.cross(ray_b)
    else:
        a = view3d_utils.region_2d_to_location_3d(region, rv3d, start, seed)
        b = view3d_utils.region_2d_to_location_3d(region, rv3d, end, seed)
        normal = (b - a).cross(ray_a)
    if normal.length < 1e-10:
        raise ValueError("Cannot determine the section plane from these points")
    return seed, normal.normalized(), depsgraph


def _screen_local_ring_surface(area, region, rv3d, start_pos, end_pos, target, radius_offset, fit_mode):
    del area
    from bpy_extras import view3d_utils
    from ..core.local_contour import fitted_ring_section

    seed, normal, depsgraph = _screen_section_plane(
        bpy.context, region, rv3d, start_pos, end_pos, target,
    )
    settings = bpy.context.scene.polygroups_object_seam_cutter_settings
    def radius_from_center(center):
        # Measure the drawn diameter at the actual section depth, never at the
        # whole object's bounding-box center or the front surface of a limb.
        a = view3d_utils.region_2d_to_location_3d(region, rv3d, Vector(start_pos), center)
        b = view3d_utils.region_2d_to_location_3d(region, rv3d, Vector(end_pos), center)
        return (b - a).length * 0.5 + radius_offset

    return fitted_ring_section(
        target, depsgraph, seed, normal, seed,
        settings.cutter_local_ring_segments, radius_offset,
        radius_from_center=radius_from_center if fit_mode == "SURFACE" else None,
        radius_hint=max(0.0, radius_from_center(seed) - radius_offset),
    )
