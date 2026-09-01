import json
import bpy
from math import atan2
from math import cos
from math import radians
from math import sin
from math import tau
from mathutils import kdtree
from mathutils import Matrix
from mathutils import Vector

from ..sound import play_operation_done_sound
from .mesh_checks import _delete_faces_by_indices
from .mesh_checks import _edge_face_data
from .mesh_checks import _fixable_issue_total
from .mesh_checks import _refresh_mesh_check
from .mesh_checks import _select_edges
from .mesh_checks import _thin_protrusion_faces
from .mesh_checks import analyze_mesh


CUTTER_COLLECTION_NAME = "Seam Cutters"
CUTTER_COLLECTION_BY_TOOL = {
    "PLANE": "Seam Cutters Plane",
    "ARC": "Seam Cutters Arc",
    "LOCAL_RING": "Seam Cutters Local Ring",
    "PATH": "Seam Cutters Path",
    "DRAW": "Seam Cutters Draw",
}
CUTTER_PROP = "polygroups_object_seam_cutter"
CUTTER_TYPE_PROP = "polygroups_object_seam_cutter_type"
CUTTER_PATH_DATA_PROP = "polygroups_object_seam_cutter_path_data"
CUTTER_DRAW_DATA_PROP = "polygroups_object_seam_cutter_draw_data"
CUTTER_SOLIDIFY_MODIFIER_NAME = "Cutter Plane Thickness"
BOOLEAN_PATH_TEMP_MATERIAL_NAME = "__AI_RETOPO_PATH_CUTTER_TEMP__"
BOOLEAN_PATH_PLACEHOLDER_MATERIAL_NAME = "__AI_RETOPO_PATH_ORIGINAL_TEMP__"
DEFAULT_CUTTER_PATH_TILT = radians(90.0)
CUTTER_PATH_TILT_STEP = radians(15.0)
BOOLEAN_CUTTER_SOLIDIFY_THICKNESS = 0.00001
BOOLEAN_SEAM_MERGE_DISTANCE = 0.00002
AUTOFIX_MAX_PROTRUSION_FACES = 2000
AUTOFIX_MAX_LOOSE_GEOMETRY = 10000
AUTOFIX_MAX_HOLE_EDGE_COUNT = 128
AUTOFIX_MAX_HOLE_LOOPS = 16


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


def _collection():
    collection = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(CUTTER_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _tool_collection(cutter_type):
    parent = _collection()
    collection_name = CUTTER_COLLECTION_BY_TOOL.get(cutter_type, CUTTER_COLLECTION_NAME)
    if collection_name == CUTTER_COLLECTION_NAME:
        return parent

    collection = parent.children.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            collection = bpy.data.collections.new(collection_name)
        if parent.children.get(collection.name) is None:
            parent.children.link(collection)
    return collection


def _tool_collection_type_for_cutter(cutter):
    cutter_type = cutter.get(CUTTER_TYPE_PROP)
    if cutter_type == "DRAW_STROKE":
        return "DRAW"
    return cutter_type or ""


def _collection_objects_recursive(collection, seen=None):
    seen = seen or set()
    objects = []
    for obj in collection.objects:
        if obj.name in seen:
            continue
        seen.add(obj.name)
        objects.append(obj)
    for child in collection.children:
        objects.extend(_collection_objects_recursive(child, seen))
    return objects


def _cutter_collection_objects():
    collection = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
    if collection is None:
        return []
    return _collection_objects_recursive(collection)


def _material(alpha):
    material = bpy.data.materials.get("PolyGroups Cutter Plane")
    if material is None:
        material = bpy.data.materials.new("PolyGroups Cutter Plane")
    material.diffuse_color = (0.1, 0.55, 1.0, alpha)
    material.use_nodes = False
    try:
        material.blend_method = "BLEND"
    except Exception:
        pass
    return material


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


def _surface_local_ring_surface(region, rv3d, start, end, target, radius_offset):
    from bpy_extras import view3d_utils

    target_center, _target_diagonal = _target_bounds(target)
    start_hit = _surface_hit_from_region_pos(region, rv3d, start, target)
    end_hit = _surface_hit_from_region_pos(region, rv3d, end, target)
    if start_hit is not None and end_hit is not None:
        start_world = start_hit[0]
        end_world = end_hit[0]
    else:
        start_world = view3d_utils.region_2d_to_location_3d(region, rv3d, start, target_center)
        end_world = view3d_utils.region_2d_to_location_3d(region, rv3d, end, target_center)

    axis_a = end_world - start_world
    radius = axis_a.length * 0.5 + radius_offset
    if radius <= 0.000001:
        return None
    axis_a.normalize()

    region_center = Vector((region.width * 0.5, region.height * 0.5))
    view_axis = view3d_utils.region_2d_to_vector_3d(region, rv3d, region_center)
    axis_b = view_axis - axis_a * view_axis.dot(axis_a)
    if axis_b.length < 0.000001:
        average_normal = Vector((0.0, 0.0, 0.0))
        if start_hit is not None:
            average_normal += start_hit[1]
        if end_hit is not None:
            average_normal += end_hit[1]
        axis_b = average_normal - axis_a * average_normal.dot(axis_a)
    if axis_b.length < 0.000001:
        axis_b = axis_a.cross(Vector((0.0, 0.0, 1.0)))
    if axis_b.length < 0.000001:
        axis_b = axis_a.cross(Vector((0.0, 1.0, 0.0)))
    if axis_b.length < 0.000001:
        return None
    axis_b.normalize()

    center = (start_world + end_world) * 0.5
    return center, axis_a, axis_b, radius


def _volume_center_from_surface_hit(target, location, normal, epsilon):
    if normal.length < 0.000001:
        return None

    for direction in (-normal, normal):
        if direction.length < 0.000001:
            continue
        direction.normalize()
        exit_hit = _target_ray_cast_world(target, location + direction * epsilon, direction)
        if exit_hit is None:
            continue
        exit_location = exit_hit[0]
        distance = (exit_location - location).length
        if distance > epsilon * 2.0:
            return (location + exit_location) * 0.5, distance * 0.5

    return None


def _volume_local_ring_surface(region, rv3d, start, end, target, radius_offset):
    start_hit = _surface_hit_from_region_pos(region, rv3d, start, target)
    end_hit = _surface_hit_from_region_pos(region, rv3d, end, target)
    if start_hit is None or end_hit is None:
        return None

    start_world, start_normal, _start_face = start_hit
    end_world, end_normal, _end_face = end_hit
    axis_a = end_world - start_world
    radius = axis_a.length * 0.5 + radius_offset
    if radius <= 0.000001:
        return None
    axis_a.normalize()

    _target_center, target_diagonal = _target_bounds(target)
    epsilon = max(target_diagonal * 0.0001, 0.00001)
    volume_samples = []
    for location, normal in ((start_world, start_normal), (end_world, end_normal)):
        sample = _volume_center_from_surface_hit(target, location, normal, epsilon)
        if sample is not None:
            volume_samples.append(sample)

    center = (start_world + end_world) * 0.5
    if volume_samples:
        volume_center = sum((item[0] for item in volume_samples), Vector()) / len(volume_samples)
        depth_hint = volume_center - center
    else:
        depth_hint = Vector((0.0, 0.0, 0.0))
    if depth_hint.length < 0.000001:
        average_normal = start_normal + end_normal
        depth_hint = -average_normal if average_normal.length > 0.000001 else Vector((0.0, 0.0, 1.0))
    axis_b = depth_hint - axis_a * depth_hint.dot(axis_a)
    if axis_b.length < 0.000001:
        axis_b = axis_a.cross(Vector((0.0, 0.0, 1.0)))
    if axis_b.length < 0.000001:
        axis_b = axis_a.cross(Vector((0.0, 1.0, 0.0)))
    if axis_b.length < 0.000001:
        return None
    axis_b.normalize()

    radius = max(radius, epsilon)
    return center, axis_a, axis_b, radius


def _screen_local_ring_surface(area, region, rv3d, start_pos, end_pos, target, radius_offset, fit_mode):
    del area

    start = Vector(start_pos)
    end = Vector(end_pos)
    if (end - start).length < 2.0:
        return None

    if fit_mode == "VOLUME":
        surface = _volume_local_ring_surface(region, rv3d, start, end, target, radius_offset)
        if surface is not None:
            return surface

    return _surface_local_ring_surface(region, rv3d, start, end, target, radius_offset)


def _add_solidify_modifier(obj, thickness):
    modifier = obj.modifiers.get(CUTTER_SOLIDIFY_MODIFIER_NAME)
    if modifier is None:
        modifier = obj.modifiers.new(CUTTER_SOLIDIFY_MODIFIER_NAME, "SOLIDIFY")
    modifier.thickness = thickness
    modifier.offset = 0.0
    return modifier


def _create_cutter_plane(name, center, axis_a, axis_b, size, alpha, thickness):
    half = size * 0.5
    vertices = [
        (-axis_a - axis_b) * half,
        (axis_a - axis_b) * half,
        (axis_a + axis_b) * half,
        (-axis_a + axis_b) * half,
    ]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(vertex) for vertex in vertices], [], [(0, 1, 2, 3)])
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = center
    obj.show_in_front = False
    obj.display_type = "TEXTURED"
    obj[CUTTER_PROP] = True
    obj[CUTTER_TYPE_PROP] = "PLANE"
    obj.data.materials.append(_material(alpha))
    _add_solidify_modifier(obj, thickness)
    _tool_collection("PLANE").objects.link(obj)
    return obj


def _create_cutter_arc(name, center_points, depth_axis, size, alpha, thickness):
    vertices = []
    faces = []
    half = size * 0.5

    for center in center_points:
        vertices.append(center - depth_axis * half)
        vertices.append(center + depth_axis * half)

    for index in range(len(center_points) - 1):
        start = index * 2
        faces.append((start, start + 1, start + 3, start + 2))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(vertex) for vertex in vertices], [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    obj = bpy.data.objects.new(name, mesh)
    obj.show_in_front = False
    obj.display_type = "TEXTURED"
    obj[CUTTER_PROP] = True
    obj[CUTTER_TYPE_PROP] = "ARC"
    obj.data.materials.append(_material(alpha))
    modifier = _add_solidify_modifier(obj, thickness)
    if hasattr(modifier, "use_rim"):
        modifier.use_rim = True
    _tool_collection("ARC").objects.link(obj)
    return obj


def _create_cutter_local_ring(name, center, axis_a, axis_b, radius, segments, alpha):
    vertices = [(0.0, 0.0, 0.0)]
    for index in range(segments):
        angle = tau * (index / segments)
        vertex = axis_a * (cos(angle) * radius) + axis_b * (sin(angle) * radius)
        vertices.append(tuple(vertex))

    faces = []
    for index in range(segments):
        start = index + 1
        end = 1 if index == segments - 1 else index + 2
        faces.append((0, start, end))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = center
    obj.show_in_front = False
    obj.display_type = "TEXTURED"
    obj[CUTTER_PROP] = True
    obj[CUTTER_TYPE_PROP] = "LOCAL_RING"
    obj.data.materials.append(_material(alpha))
    _tool_collection("LOCAL_RING").objects.link(obj)
    return obj


def _create_cutter_path(name, path_points, render_u, extrude, alpha, collection_type="PATH"):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = render_u
    curve.render_resolution_u = render_u
    curve.extrude = extrude

    spline = curve.splines.new("POLY")
    spline.points.add(len(path_points) - 1)
    for point, item in zip(spline.points, path_points):
        location = item["location"]
        point.co = (location.x, location.y, location.z, 1.0)
        if hasattr(point, "tilt"):
            point.tilt = DEFAULT_CUTTER_PATH_TILT

    obj = bpy.data.objects.new(name, curve)
    obj.show_in_front = False
    obj.display_type = "TEXTURED"
    obj[CUTTER_PROP] = True
    obj[CUTTER_TYPE_PROP] = "PATH"
    obj[CUTTER_PATH_DATA_PROP] = json.dumps(
        [
            {
                "co": list(item["location"]),
                "normal": list(item["normal"]),
            }
            for item in path_points
        ],
    )
    obj.data.materials.append(_material(alpha))
    _tool_collection(collection_type).objects.link(obj)
    return obj


def _write_cutter_path_points(cutter, path_points):
    if cutter.type != "CURVE":
        return

    cutter.data.splines.clear()
    spline = cutter.data.splines.new("POLY")
    spline.points.add(len(path_points) - 1)
    for point, item in zip(spline.points, path_points):
        location = item["location"]
        point.co = (location.x, location.y, location.z, 1.0)
        if hasattr(point, "tilt"):
            point.tilt = DEFAULT_CUTTER_PATH_TILT

    cutter[CUTTER_PATH_DATA_PROP] = json.dumps(
        [
            {
                "co": list(item["location"]),
                "normal": list(item["normal"]),
            }
            for item in path_points
        ],
    )


def _create_cutter_draw_stroke(name, path_points, render_u, alpha):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = render_u
    curve.render_resolution_u = render_u
    curve.bevel_depth = 0.002
    curve.bevel_resolution = 1

    spline = curve.splines.new("POLY")
    spline.points.add(len(path_points) - 1)
    for point, item in zip(spline.points, path_points):
        location = item["location"]
        point.co = (location.x, location.y, location.z, 1.0)
        if hasattr(point, "tilt"):
            point.tilt = DEFAULT_CUTTER_PATH_TILT

    obj = bpy.data.objects.new(name, curve)
    obj.show_in_front = False
    obj.display_type = "TEXTURED"
    obj[CUTTER_PROP] = True
    obj[CUTTER_TYPE_PROP] = "DRAW_STROKE"
    obj[CUTTER_DRAW_DATA_PROP] = json.dumps(
        [
            {
                "co": list(item["location"]),
                "normal": list(item["normal"]),
            }
            for item in path_points
        ],
    )
    obj.data.materials.append(_material(alpha))
    _tool_collection("DRAW").objects.link(obj)
    return obj


def _write_draw_stroke_points(stroke, path_points):
    if stroke.type != "CURVE":
        return

    stroke.data.splines.clear()
    spline = stroke.data.splines.new("POLY")
    spline.points.add(len(path_points) - 1)
    for point, item in zip(spline.points, path_points):
        location = item["location"]
        point.co = (location.x, location.y, location.z, 1.0)
        if hasattr(point, "tilt"):
            point.tilt = DEFAULT_CUTTER_PATH_TILT

    stroke[CUTTER_DRAW_DATA_PROP] = json.dumps(
        [
            {
                "co": list(item["location"]),
                "normal": list(item["normal"]),
            }
            for item in path_points
        ],
    )


def _draw_stroke_data(cutter):
    try:
        data = json.loads(cutter.get(CUTTER_DRAW_DATA_PROP, "[]"))
    except Exception:
        data = []
    return data if isinstance(data, list) else []


def _draw_stroke_path_points(cutter):
    data = _draw_stroke_data(cutter)
    if data:
        return [
            {
                "location": Vector(item.get("co", (0.0, 0.0, 0.0))),
                "normal": Vector(item.get("normal", (0.0, 0.0, 1.0))),
            }
            for item in data
        ]

    if cutter.type != "CURVE" or not cutter.data.splines:
        return []

    return [
        {
            "location": cutter.matrix_world @ _curve_point_local_co(point),
            "normal": Vector((0.0, 0.0, 1.0)),
        }
        for point in _curve_spline_points(cutter.data.splines[0])
    ]


def _simplify_path_points(path_points, distance):
    if len(path_points) < 3 or distance <= 0.0:
        return path_points

    simplified = [path_points[0]]
    for item in path_points[1:-1]:
        if (item["location"] - simplified[-1]["location"]).length >= distance:
            simplified.append(item)

    if simplified[-1] is not path_points[-1]:
        simplified.append(path_points[-1])
    return simplified


def _convert_draw_stroke_to_cutter_path(context, stroke):
    settings = context.scene.polygroups_object_seam_cutter_settings
    path_points = _simplify_path_points(
        _draw_stroke_path_points(stroke),
        settings.cutter_draw_simplify_distance,
    )
    if len(path_points) < 2:
        return None

    cutter = _create_cutter_path(
        "Seam_Cutter_Path",
        path_points,
        settings.cutter_path_render_u,
        settings.cutter_path_extrude,
        settings.cutter_alpha,
    )
    if settings.delete_draw_strokes_after_convert and stroke.name in bpy.data.objects:
        bpy.data.objects.remove(stroke, do_unlink=True)
    return cutter


def _draw_strokes_from_cutters(cutters):
    return [
        cutter
        for cutter in cutters
        if cutter.type == "CURVE" and cutter.get(CUTTER_TYPE_PROP) == "DRAW_STROKE"
    ]


def _draw_strokes_in_collection(exclude=None):
    exclude = set(exclude or [])
    return [
        obj
        for obj in _cutter_collection_objects()
        if obj not in exclude
        and obj.type == "CURVE"
        and obj.get(CUTTER_PROP)
        and obj.get(CUTTER_TYPE_PROP) == "DRAW_STROKE"
    ]


def _join_draw_stroke_points(base_points, next_points):
    candidates = (
        ((base_points[-1]["location"] - next_points[0]["location"]).length, base_points, next_points),
        ((base_points[0]["location"] - next_points[-1]["location"]).length, next_points, base_points),
        ((base_points[0]["location"] - next_points[0]["location"]).length, list(reversed(next_points)), base_points),
        ((base_points[-1]["location"] - next_points[-1]["location"]).length, base_points, list(reversed(next_points))),
    )
    distance, left, right = min(candidates, key=lambda item: item[0])
    if left[-1]["location"] == right[0]["location"]:
        return distance, left + right[1:]
    return distance, left + right


def _find_draw_stroke_to_continue(path_points, max_distance, exclude=None):
    if not path_points or max_distance <= 0.0:
        return None, None

    best_stroke = None
    best_points = None
    best_distance = None
    for stroke in _draw_strokes_in_collection(exclude=exclude):
        stroke_points = _draw_stroke_path_points(stroke)
        if len(stroke_points) < 2:
            continue
        distance, joined_points = _join_draw_stroke_points(stroke_points, path_points)
        if distance > max_distance:
            continue
        if best_distance is None or distance < best_distance:
            best_stroke = stroke
            best_points = joined_points
            best_distance = distance

    return best_stroke, best_points


def _join_draw_strokes(strokes, max_distance):
    remaining = [
        (stroke, _draw_stroke_path_points(stroke))
        for stroke in strokes
        if stroke.name in bpy.data.objects
    ]
    remaining = [
        (stroke, points)
        for stroke, points in remaining
        if len(points) >= 2
    ]
    if len(remaining) < 2:
        return None, 0

    base, base_points = remaining.pop(0)
    joined_count = 0
    while remaining:
        best_index = None
        best_distance = None
        best_points = None
        for index, (_, points) in enumerate(remaining):
            distance, candidate_points = _join_draw_stroke_points(base_points, points)
            if max_distance > 0.0 and distance > max_distance:
                continue
            if best_distance is None or distance < best_distance:
                best_index = index
                best_distance = distance
                best_points = candidate_points

        if best_index is None:
            break

        stroke, _ = remaining.pop(best_index)
        base_points = best_points
        bpy.data.objects.remove(stroke, do_unlink=True)
        joined_count += 1

    if joined_count:
        _write_draw_stroke_points(base, base_points)
    return base, joined_count


def _path_cutters_in_collection(exclude=None):
    exclude = set(exclude or [])
    return [
        obj
        for obj in _cutter_collection_objects()
        if obj not in exclude
        and obj.type == "CURVE"
        and obj.get(CUTTER_PROP)
        and obj.get(CUTTER_TYPE_PROP) == "PATH"
    ]


def _join_path_points(base_points, next_points):
    return _join_draw_stroke_points(base_points, next_points)


def _find_path_to_continue(path_points, max_distance, exclude=None):
    if not path_points or max_distance <= 0.0:
        return None, None

    best_path = None
    best_points = None
    best_distance = None
    for path in _path_cutters_in_collection(exclude=exclude):
        existing_points = _path_cutter_path_points(path)
        if len(existing_points) < 2:
            continue
        distance, joined_points = _join_path_points(existing_points, path_points)
        if distance > max_distance:
            continue
        if best_distance is None or distance < best_distance:
            best_path = path
            best_points = joined_points
            best_distance = distance

    return best_path, best_points


def _join_path_cutters(paths, max_distance):
    remaining = [
        (path, _path_cutter_path_points(path))
        for path in paths
        if path.name in bpy.data.objects
    ]
    remaining = [
        (path, points)
        for path, points in remaining
        if len(points) >= 2
    ]
    if len(remaining) < 2:
        return None, 0

    base, base_points = remaining.pop(0)
    joined_count = 0
    while remaining:
        best_index = None
        best_distance = None
        best_points = None
        for index, (_, points) in enumerate(remaining):
            distance, candidate_points = _join_path_points(base_points, points)
            if max_distance > 0.0 and distance > max_distance:
                continue
            if best_distance is None or distance < best_distance:
                best_index = index
                best_distance = distance
                best_points = candidate_points

        if best_index is None:
            break

        path, _ = remaining.pop(best_index)
        base_points = best_points
        bpy.data.objects.remove(path, do_unlink=True)
        joined_count += 1

    if joined_count:
        _write_cutter_path_points(base, base_points)
    return base, joined_count


def _selected_cutters(context, target):
    cutters = [
        obj
        for obj in context.selected_objects
        if obj != target and obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
    ]
    if cutters:
        return cutters

    return [
        obj
        for obj in _cutter_collection_objects()
        if obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
    ]


def _selected_cutters_only(context):
    return [
        obj
        for obj in context.selected_objects
        if obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
    ]


def _has_selected_cutters_for_apply(context):
    return bool(_selected_cutters_only(context))


def _mirror_matrix_from_target(target, axis):
    axis = axis if axis in {"X", "Y", "Z"} else "X"
    scale = {
        "X": (-1.0, 1.0, 1.0, 1.0),
        "Y": (1.0, -1.0, 1.0, 1.0),
        "Z": (1.0, 1.0, -1.0, 1.0),
    }[axis]
    pivot = target.matrix_world.translation
    return (
        Matrix.Translation(pivot)
        @ Matrix.Diagonal(scale)
        @ Matrix.Translation(-pivot)
    )


def _copy_mirror_cutter(cutter, mirror_matrix):
    mirrored = cutter.copy()
    mirrored.data = cutter.data.copy()
    mirrored.animation_data_clear()
    mirrored.name = f"{cutter.name}_Mirror"
    mirrored.matrix_world = mirror_matrix @ cutter.matrix_world

    _tool_collection(_tool_collection_type_for_cutter(cutter)).objects.link(mirrored)
    mirrored.select_set(True)
    return mirrored


def _curve_spline_points(spline):
    return spline.bezier_points if spline.type == "BEZIER" else spline.points


def _curve_point_local_co(point):
    return Vector((point.co.x, point.co.y, point.co.z))


def _selected_cutter_path_curves(context):
    return [
        obj
        for obj in context.selected_objects
        if obj.type == "CURVE"
        and obj.get(CUTTER_PROP)
        and obj.get(CUTTER_TYPE_PROP) in {"PATH", "DRAW_STROKE"}
    ]


def _update_curve_path_data_from_splines(obj):
    if obj.type != "CURVE" or not obj.data.splines:
        return

    data = []
    for spline in obj.data.splines:
        for point in _curve_spline_points(spline):
            data.append(
                {
                    "co": list(obj.matrix_world @ _curve_point_local_co(point)),
                    "normal": [0.0, 0.0, 1.0],
                },
            )
    if data:
        prop_name = CUTTER_DRAW_DATA_PROP if obj.get(CUTTER_TYPE_PROP) == "DRAW_STROKE" else CUTTER_PATH_DATA_PROP
        obj[prop_name] = json.dumps(data)


def _set_bezier_handle_auto(point):
    for value in ("AUTO", "AUTOMATIC"):
        try:
            point.handle_left_type = value
            point.handle_right_type = value
            return
        except TypeError:
            continue


def _is_cutter_name(obj):
    return "Seam_Cutter" in obj.name


def _is_target_mesh_candidate(obj):
    return (
        obj is not None
        and obj.type == "MESH"
        and not obj.get(CUTTER_PROP)
        and not _is_cutter_name(obj)
    )


def _prefer_highpoly_generated(objects):
    for obj in objects:
        if "Highpoly_Generated" in obj.name:
            return obj
    return objects[0] if objects else None


def _find_cutter_target(context):
    active = context.active_object
    if _is_target_mesh_candidate(active):
        return active

    selected = [
        obj
        for obj in context.selected_objects
        if _is_target_mesh_candidate(obj)
    ]
    target = _prefer_highpoly_generated(selected)
    if target is not None:
        return target

    scene_candidates = [
        obj
        for obj in context.scene.objects
        if _is_target_mesh_candidate(obj) and "Highpoly_Generated" in obj.name
    ]
    return _prefer_highpoly_generated(scene_candidates)


def _cutter_planes_world(cutter):
    if cutter.get(CUTTER_TYPE_PROP) == "PATH":
        return _path_cutter_planes_world(cutter)

    if cutter.type != "MESH" or not cutter.data.polygons:
        return []

    planes = []
    polygons = cutter.data.polygons if cutter.get(CUTTER_TYPE_PROP) == "ARC" else cutter.data.polygons[:1]
    for polygon in polygons:
        verts = [cutter.data.vertices[index].co for index in polygon.vertices]
        local_center = sum(verts, Vector()) / len(verts)
        world_center = cutter.matrix_world @ local_center
        normal = cutter.matrix_world.to_3x3().inverted().transposed() @ polygon.normal
        if normal.length < 0.000001:
            continue
        normal.normalize()
        planes.append((world_center, normal))
    return planes


def _path_cutter_planes_world(cutter):
    return [
        (segment["plane_co"], segment["plane_no"])
        for segment in _path_cutter_segments_world(cutter)
    ]


def _path_cutter_segments_world(cutter):
    points = _path_points_world(cutter)
    normals = _path_normals_world(cutter, len(points))
    tilts = _path_tilts(cutter, len(points))
    if len(points) < 2:
        return []

    planes = []
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        tangent = end - start
        if tangent.length < 0.000001:
            continue
        tangent.normalize()

        normal = normals[index] + normals[index + 1]
        if normal.length < 0.000001:
            normal = normals[index]
        if normal.length < 0.000001:
            continue
        normal.normalize()

        tilt = (tilts[index] + tilts[index + 1]) * 0.5
        if abs(tilt) > 0.000001:
            normal.rotate(Matrix.Rotation(tilt, 3, tangent))

        plane_no = tangent.cross(normal)
        if plane_no.length < 0.000001:
            continue
        plane_no.normalize()
        planes.append(
            {
                "start": start,
                "end": end,
                "plane_co": (start + end) * 0.5,
                "plane_no": plane_no,
            },
        )

    return planes


def _path_points_world(cutter):
    if cutter.type == "CURVE" and cutter.data.splines:
        spline = cutter.data.splines[0]
        return [
            cutter.matrix_world @ _curve_point_local_co(point)
            for point in _curve_spline_points(spline)
        ]

    return [
        Vector(item["co"])
        for item in _path_data(cutter)
    ]


def _path_normals_world(cutter, point_count):
    matrix = cutter.matrix_world.to_3x3().inverted().transposed()
    normals = []
    for item in _path_data(cutter):
        normal = matrix @ Vector(item.get("normal", (0.0, 0.0, 1.0)))
        if normal.length > 0.000001:
            normal.normalize()
        normals.append(normal)

    while len(normals) < point_count:
        normals.append(Vector((0.0, 0.0, 1.0)))
    return normals[:point_count]


def _path_tilts(cutter, point_count):
    tilts = []
    if cutter.type == "CURVE" and cutter.data.splines:
        for point in _curve_spline_points(cutter.data.splines[0]):
            tilts.append(getattr(point, "tilt", DEFAULT_CUTTER_PATH_TILT))

    while len(tilts) < point_count:
        tilts.append(DEFAULT_CUTTER_PATH_TILT)
    return tilts[:point_count]


def _path_data(cutter):
    try:
        data = json.loads(cutter.get(CUTTER_PATH_DATA_PROP, "[]"))
    except Exception:
        data = []
    return data if isinstance(data, list) else []


def _path_cutter_path_points(cutter):
    data = _path_data(cutter)
    if data:
        return [
            {
                "location": Vector(item.get("co", (0.0, 0.0, 0.0))),
                "normal": Vector(item.get("normal", (0.0, 0.0, 1.0))),
            }
            for item in data
        ]

    if cutter.type != "CURVE" or not cutter.data.splines:
        return []

    return [
        {
            "location": cutter.matrix_world @ _curve_point_local_co(point),
            "normal": Vector((0.0, 0.0, 1.0)),
        }
        for point in _curve_spline_points(cutter.data.splines[0])
    ]


def _world_plane_to_local(target, plane_co, plane_no):
    matrix = target.matrix_world
    local_co = matrix.inverted() @ plane_co
    local_no = matrix.to_3x3().transposed() @ plane_no
    if local_no.length < 0.000001:
        return None
    local_no.normalize()
    return local_co, local_no


def _clear_mesh_component_selection(mesh):
    for vertex in mesh.vertices:
        vertex.select = False
    for edge in mesh.edges:
        edge.select = False
    for polygon in mesh.polygons:
        polygon.select = False
    mesh.update()


def _path_boolean_material():
    material = bpy.data.materials.new(BOOLEAN_PATH_TEMP_MATERIAL_NAME)
    material.diffuse_color = (1.0, 0.08, 0.02, 1.0)
    material.use_nodes = False
    return material


def _path_placeholder_material():
    material = bpy.data.materials.new(BOOLEAN_PATH_PLACEHOLDER_MATERIAL_NAME)
    material.diffuse_color = (0.5, 0.5, 0.5, 1.0)
    material.use_nodes = False
    return material


def _ensure_material_slot(obj, material):
    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material or (slot_material and slot_material.name == material.name):
            return index

    obj.data.materials.append(material)
    return len(obj.data.materials) - 1


def _prepare_target_path_boolean_materials(target, temp_material):
    placeholder_material = None
    placeholder_index = None
    if not target.data.materials:
        placeholder_material = _path_placeholder_material()
        target.data.materials.append(placeholder_material)
        placeholder_index = 0
        for polygon in target.data.polygons:
            polygon.material_index = 0

    target.data.materials.append(temp_material)
    return len(target.data.materials) - 1, placeholder_index, placeholder_material


def _extend_arc_cutter_mesh_ends(obj, extension_distance):
    if obj.type != "MESH" or obj.get(CUTTER_TYPE_PROP) != "ARC" or extension_distance <= 0.0:
        return

    vertices = obj.data.vertices
    if len(vertices) < 4:
        return

    def pair_center(index):
        return (vertices[index].co + vertices[index + 1].co) * 0.5

    first_center = pair_center(0)
    second_center = pair_center(2)
    first_direction = first_center - second_center
    if first_direction.length > 0.000001:
        first_direction.normalize()
        vertices[0].co += first_direction * extension_distance
        vertices[1].co += first_direction * extension_distance

    last_index = len(vertices) - 2
    previous_index = len(vertices) - 4
    last_center = pair_center(last_index)
    previous_center = pair_center(previous_index)
    last_direction = last_center - previous_center
    if last_direction.length > 0.000001:
        last_direction.normalize()
        vertices[last_index].co += last_direction * extension_distance
        vertices[last_index + 1].co += last_direction * extension_distance

    obj.data.update()


def _duplicate_boolean_cutter_as_mesh(
    context,
    cutter,
    material,
    boolean_solidify_thickness=None,
    extension_distance=0.0,
):
    work = cutter.copy()
    work.data = cutter.data.copy()
    work.name = f"{cutter.name}_Boolean"
    work[CUTTER_PROP] = False
    work.hide_viewport = False
    work.hide_render = False
    work.hide_set(False)
    if boolean_solidify_thickness is None:
        for modifier in list(work.modifiers):
            if modifier.name == CUTTER_SOLIDIFY_MODIFIER_NAME:
                work.modifiers.remove(modifier)
    else:
        modifier = work.modifiers.get(CUTTER_SOLIDIFY_MODIFIER_NAME)
        if modifier is None:
            modifier = work.modifiers.new(CUTTER_SOLIDIFY_MODIFIER_NAME, "SOLIDIFY")
        modifier.thickness = boolean_solidify_thickness
        modifier.offset = 0.0
        if hasattr(modifier, "use_rim"):
            modifier.use_rim = True

    target_collection = cutter.users_collection[0] if cutter.users_collection else context.scene.collection
    target_collection.objects.link(work)

    bpy.ops.object.select_all(action="DESELECT")
    work.select_set(True)
    context.view_layer.objects.active = work

    if work.type != "MESH":
        source_data = work.data
        if work.type == "CURVE":
            settings = getattr(context.scene, "polygroups_object_seam_cutter_settings", None)
            work.data.dimensions = "3D"
            if hasattr(work.data, "fill_mode"):
                work.data.fill_mode = "FULL"
            if getattr(work.data, "extrude", 0.0) <= 0.000001:
                work.data.extrude = max(getattr(settings, "cutter_path_extrude", 0.015), 0.001)
        bpy.ops.object.convert(target="MESH")
        work = context.view_layer.objects.active
        if source_data and source_data.users == 0 and bpy.data.curves.get(source_data.name) == source_data:
            bpy.data.curves.remove(source_data)

    if work is None or work.type != "MESH" or not work.data.polygons:
        if work is not None:
            bpy.data.objects.remove(work, do_unlink=True)
        return None

    _extend_arc_cutter_mesh_ends(work, extension_distance)

    material_index = _ensure_material_slot(work, material)
    for polygon in work.data.polygons:
        polygon.material_index = material_index
        polygon.select = True
    work.data.update()

    if boolean_solidify_thickness is not None:
        modifier = work.modifiers.get(CUTTER_SOLIDIFY_MODIFIER_NAME)
        if modifier is None:
            modifier = work.modifiers.new(CUTTER_SOLIDIFY_MODIFIER_NAME, "SOLIDIFY")
            modifier.thickness = boolean_solidify_thickness
            modifier.offset = 0.0
            if hasattr(modifier, "use_rim"):
                modifier.use_rim = True
        if modifier is not None:
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except RuntimeError:
                pass
        material_index = _ensure_material_slot(work, material)
        for polygon in work.data.polygons:
            polygon.material_index = material_index
            polygon.select = True
        work.data.update()

    return work


def _apply_boolean_modifier(context, target, cutter_mesh, solver="FLOAT"):
    modifier = target.modifiers.new("Cutter Path Boolean Seam", "BOOLEAN")
    modifier.operation = "UNION"
    try:
        modifier.solver = solver
    except TypeError:
        modifier.solver = "FLOAT"
    if solver == "EXACT" and hasattr(modifier, "use_self"):
        modifier.use_self = True
    if solver == "EXACT" and hasattr(modifier, "use_hole_tolerant"):
        modifier.use_hole_tolerant = True
    modifier.object = cutter_mesh

    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def _bvh_from_cutter_mesh(target, cutter_mesh):
    from mathutils.bvhtree import BVHTree

    matrix = target.matrix_world.inverted() @ cutter_mesh.matrix_world
    vertices = [matrix @ vertex.co for vertex in cutter_mesh.data.vertices]
    faces = []
    for polygon in cutter_mesh.data.polygons:
        polygon_vertices = list(polygon.vertices)
        if len(polygon_vertices) < 3:
            continue
        for index in range(1, len(polygon_vertices) - 1):
            faces.append((polygon_vertices[0], polygon_vertices[index], polygon_vertices[index + 1]))
    if not vertices or not faces:
        return None
    return BVHTree.FromPolygons(vertices, faces)


def _point_near_cutter_bvh(point, cutter_bvh, threshold):
    nearest = cutter_bvh.find_nearest(point, threshold)
    return nearest is not None


def _mark_boolean_path_boundaries_and_remove_faces_bmesh(
    target,
    temp_material_index,
    original_face_count,
    cutter_bvh=None,
):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()

    material_faces = [
        face
        for face in bm.faces
        if face.material_index == temp_material_index
    ]
    new_material_faces = [
        face
        for index, face in enumerate(bm.faces)
        if index >= original_face_count and face.material_index == temp_material_index
    ]
    if new_material_faces:
        material_faces = new_material_faces
    elif not material_faces and original_face_count < len(bm.faces):
        material_faces = [
            face
            for index, face in enumerate(bm.faces)
            if index >= original_face_count
        ]

    if cutter_bvh and material_faces:
        _center, target_diagonal = _target_bounds(target)
        temp_faces = []
        for scale in (0.0001, 0.0005, 0.001):
            threshold = max(target_diagonal * scale, 0.00001)
            temp_faces = [
                face
                for face in material_faces
                if _point_near_cutter_bvh(face.calc_center_median(), cutter_bvh, threshold)
            ]
            if temp_faces:
                break
        temp_face_set = set(temp_faces)
        preserved_faces = [face for face in material_faces if face not in temp_face_set]
        fallback_index = max(0, temp_material_index - 1)
        for face in preserved_faces:
            face.material_index = fallback_index
    else:
        temp_faces = material_faces

    if not temp_faces:
        bm.free()
        return 0

    initial_seam_count = sum(1 for edge in bm.edges if edge.seam)
    temp_face_set = set(temp_faces)
    temp_edges = {edge for face in temp_faces for edge in face.edges}
    boundary_edges = set()
    for face in temp_faces:
        for edge in face.edges:
            has_regular_neighbor = any(neighbor not in temp_face_set for neighbor in edge.link_faces)
            if not has_regular_neighbor:
                continue

            boundary_edges.add(edge)
            edge.seam = True
            edge.select_set(True)

    bmesh.ops.delete(bm, geom=temp_faces, context="FACES_ONLY")
    loose_temp_edges = [
        edge
        for edge in temp_edges
        if edge.is_valid and edge not in boundary_edges and not edge.link_faces
    ]
    if loose_temp_edges:
        bmesh.ops.delete(bm, geom=loose_temp_edges, context="EDGES")
    loose_verts = [vert for vert in bm.verts if vert.is_valid and not vert.link_edges]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

    final_seam_count = sum(1 for edge in bm.edges if edge.is_valid and edge.seam)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return max(0, final_seam_count - initial_seam_count)


def _mesh_has_selected_edges(mesh):
    return any(edge.select for edge in mesh.edges)


def _split_selected_edges(context, target, separate_objects):
    if not _mesh_has_selected_edges(target.data):
        return []

    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    context.view_layer.objects.active = target

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="EDGE")
    bpy.ops.mesh.edge_split()

    if separate_objects:
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.separate(type="LOOSE")
        bpy.ops.object.mode_set(mode="OBJECT")
        return [obj for obj in context.selected_objects if obj.type == "MESH"]

    bpy.ops.object.mode_set(mode="OBJECT")
    return [target]


def _fill_split_cut_boundaries(objects):
    import bmesh

    filled_faces = 0
    for obj in objects:
        if obj.type != "MESH":
            continue

        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        cut_boundary_edges = [
            edge
            for edge in bm.edges
            if edge.is_boundary and (edge.seam or edge.select)
        ]
        if not cut_boundary_edges:
            bm.free()
            continue

        result = bmesh.ops.holes_fill(
            bm,
            edges=cut_boundary_edges,
            sides=0,
        )
        filled_faces += sum(
            1
            for item in result.get("geom", ())
            if isinstance(item, bmesh.types.BMFace)
        )
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

    return filled_faces


def _remove_material_slot_by_index(obj, material_index):
    if material_index < 0 or material_index >= len(obj.data.materials):
        return

    try:
        obj.data.materials.pop(index=material_index)
    except Exception:
        pass


def _remove_material_if_unused(material):
    if material is not None and bpy.data.materials.get(material.name) == material and material.users == 0:
        bpy.data.materials.remove(material)


def _material_slot_index(obj, material):
    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material or (slot_material and slot_material.name == material.name):
            return index
    return -1


def _candidate_faces_by_material_index(mesh, material_index, min_face_index=None):
    material_faces = [
        polygon
        for polygon in mesh.polygons
        if polygon.material_index == material_index
    ]
    if min_face_index is None:
        return material_faces

    new_material_faces = [
        polygon
        for polygon in material_faces
        if polygon.index >= min_face_index
    ]
    return new_material_faces or material_faces


def _select_faces_by_material_index(obj, material_index, min_face_index=None):
    selected_face_indices = {
        polygon.index
        for polygon in _candidate_faces_by_material_index(obj.data, material_index, min_face_index)
    }
    selected = 0
    for edge in obj.data.edges:
        edge.select = False
    for polygon in obj.data.polygons:
        is_selected = polygon.index in selected_face_indices
        polygon.select = is_selected
        if is_selected:
            selected += 1
    obj.data.update()
    return selected


def _selected_edge_snapshots(mesh):
    snapshots = []
    for edge in mesh.edges:
        if not edge.select:
            continue
        start = mesh.vertices[edge.vertices[0]].co.copy()
        end = mesh.vertices[edge.vertices[1]].co.copy()
        snapshots.append(
            {
                "midpoint": (start + end) * 0.5,
                "length": (end - start).length,
            },
        )
    return snapshots


def _mark_edges_matching_snapshots(mesh, edge_snapshots, threshold):
    if not edge_snapshots:
        return 0

    tree = kdtree.KDTree(len(edge_snapshots))
    for index, item in enumerate(edge_snapshots):
        tree.insert(item["midpoint"], index)
    tree.balance()

    marked = 0
    length_threshold = max(threshold * 10.0, 0.000001)
    for edge in mesh.edges:
        start = mesh.vertices[edge.vertices[0]].co
        end = mesh.vertices[edge.vertices[1]].co
        midpoint = (start + end) * 0.5
        nearest = tree.find(midpoint)
        if nearest is None:
            continue

        _co, index, distance = nearest
        if distance > threshold:
            continue
        if abs((end - start).length - edge_snapshots[index]["length"]) > length_threshold:
            continue

        edge.use_seam = True
        edge.select = True
        marked += 1
    mesh.update()
    return marked


def _apply_boolean_cutter_to_mesh(
    context,
    target,
    cutter,
    boolean_solidify_thickness=None,
    extension_distance=0.0,
    boolean_solver="FLOAT",
):
    material = _path_boolean_material()
    temp_material_index, placeholder_index, placeholder_material = _prepare_target_path_boolean_materials(
        target,
        material,
    )
    original_face_count = len(target.data.polygons)
    work = _duplicate_boolean_cutter_as_mesh(
        context,
        cutter,
        material,
        boolean_solidify_thickness=boolean_solidify_thickness,
        extension_distance=extension_distance,
    )
    if work is None:
        _remove_material_slot_by_index(target, temp_material_index)
        if placeholder_index is not None:
            _remove_material_slot_by_index(target, placeholder_index)
        _remove_material_if_unused(material)
        _remove_material_if_unused(placeholder_material)
        return 0

    cutter_bvh = _bvh_from_cutter_mesh(target, work)
    try:
        _apply_boolean_modifier(context, target, work, boolean_solver)
        return _mark_boolean_path_boundaries_and_remove_faces_bmesh(
            target,
            temp_material_index,
            original_face_count,
            cutter_bvh,
        )
    finally:
        if work.name in bpy.data.objects:
            work_data = work.data
            bpy.data.objects.remove(work, do_unlink=True)
            if work_data and work_data.users == 0:
                if hasattr(bpy.data, "meshes") and bpy.data.meshes.get(work_data.name) == work_data:
                    bpy.data.meshes.remove(work_data)
                elif hasattr(bpy.data, "curves") and bpy.data.curves.get(work_data.name) == work_data:
                    bpy.data.curves.remove(work_data)
        _remove_material_slot_by_index(target, temp_material_index)
        if placeholder_index is not None:
            _remove_material_slot_by_index(target, placeholder_index)
        _remove_material_if_unused(material)
        _remove_material_if_unused(placeholder_material)


def _apply_knife_intersect_cutter_to_mesh(
    context,
    target,
    cutter,
    extension_distance=0.0,
    boolean_solidify_thickness=None,
):
    material = _path_boolean_material()
    temp_material_index, placeholder_index, placeholder_material = _prepare_target_path_boolean_materials(
        target,
        material,
    )
    original_face_count = len(target.data.polygons)
    work = _duplicate_boolean_cutter_as_mesh(
        context,
        cutter,
        material,
        boolean_solidify_thickness=boolean_solidify_thickness,
        extension_distance=extension_distance,
    )
    if work is None:
        _remove_material_slot_by_index(target, temp_material_index)
        if placeholder_index is not None:
            _remove_material_slot_by_index(target, placeholder_index)
        _remove_material_if_unused(material)
        _remove_material_if_unused(placeholder_material)
        return 0

    work_name = work.name
    work_data = work.data
    try:
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        work.select_set(True)
        context.view_layer.objects.active = target
        bpy.ops.object.join()

        temp_material_index = _material_slot_index(target, material)
        if temp_material_index < 0:
            return 0

        target.active_material_index = temp_material_index
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.intersect(
            mode="SELECT",
            separate_mode="CUT",
            threshold=0.000001,
            solver="FLOAT",
        )

        bpy.ops.object.mode_set(mode="OBJECT")
        temp_face_count = _select_faces_by_material_index(
            target,
            temp_material_index,
            min_face_index=original_face_count,
        )
        if not temp_face_count:
            return 0

        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bpy.ops.mesh.region_to_loop()

        bpy.ops.object.mode_set(mode="OBJECT")
        edge_snapshots = _selected_edge_snapshots(target.data)

        _select_faces_by_material_index(
            target,
            temp_material_index,
            min_face_index=original_face_count,
        )
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bpy.ops.mesh.delete(type="FACE")
        bpy.ops.object.mode_set(mode="OBJECT")
        _clear_mesh_component_selection(target.data)
        _center, target_diagonal = _target_bounds(target)
        marked_edges = _mark_edges_matching_snapshots(
            target.data,
            edge_snapshots,
            max(target_diagonal * 0.000001, 0.000001),
        )
        target.data.update()

        return marked_edges
    finally:
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if bpy.data.objects.get(work_name) is not None:
            bpy.data.objects.remove(bpy.data.objects[work_name], do_unlink=True)
            if work_data and work_data.users == 0 and bpy.data.meshes.get(work_data.name) == work_data:
                bpy.data.meshes.remove(work_data)
        temp_material_index = _material_slot_index(target, material)
        if temp_material_index >= 0:
            _remove_material_slot_by_index(target, temp_material_index)
        if placeholder_index is not None:
            _remove_material_slot_by_index(target, placeholder_index)
        _remove_material_if_unused(material)
        _remove_material_if_unused(placeholder_material)


def _arc_heal_distance(context):
    model_settings = getattr(context.scene, "polygroups_model_preparation_settings", None)
    weld_distance = getattr(model_settings, "weld_distance", 0.0001)
    return weld_distance


def _boolean_seam_merge_distance(context):
    del context
    return BOOLEAN_SEAM_MERGE_DISTANCE


def _cutter_apply_method(context):
    settings = getattr(context.scene, "polygroups_object_seam_cutter_settings", None)
    return getattr(settings, "cutter_apply_method", "BOOLEAN")


def _cutter_boolean_solver(context):
    settings = getattr(context.scene, "polygroups_object_seam_cutter_settings", None)
    solver = getattr(settings, "cutter_boolean_solver", "FLOAT")
    return solver if solver in {"FLOAT", "EXACT"} else "FLOAT"


def _merge_selected_cut_vertices(target, merge_distance):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()

    selected_edges = [edge for edge in bm.edges if edge.select]
    if not selected_edges:
        bm.free()
        return 0

    selected_verts = {vert for edge in selected_edges for vert in edge.verts}
    before_vert_count = len(bm.verts)
    bmesh.ops.remove_doubles(
        bm,
        verts=list(selected_verts),
        dist=merge_distance,
    )

    for edge in bm.edges:
        if edge.is_valid and edge.select:
            edge.seam = True

    after_vert_count = len([vert for vert in bm.verts if vert.is_valid])
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return max(0, before_vert_count - after_vert_count)


def _merge_open_boundary_vertices(target, merge_distance):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()

    boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) < 2]
    if not boundary_edges:
        bm.free()
        return 0

    boundary_verts = {vert for edge in boundary_edges for vert in edge.verts}
    before_vert_count = len(bm.verts)
    bmesh.ops.remove_doubles(
        bm,
        verts=list(boundary_verts),
        dist=merge_distance,
    )

    after_vert_count = len([vert for vert in bm.verts if vert.is_valid])
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return max(0, before_vert_count - after_vert_count)


def _count_open_boundary_edges(target):
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(target.data)
    count = sum(1 for edge in bm.edges if len(edge.link_faces) < 2)
    bm.free()
    return count


def _delete_loose_geometry_for_autofix(context, target):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    loose_edges = [edge for edge in bm.edges if edge.is_valid and not edge.link_faces]
    loose_verts = [vert for vert in bm.verts if vert.is_valid and not vert.link_edges]
    loose_total = len(loose_edges) + len(loose_verts)
    if not loose_total or loose_total > AUTOFIX_MAX_LOOSE_GEOMETRY:
        bm.free()
        return 0

    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [vert for vert in bm.verts if vert.is_valid and not vert.link_edges]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return loose_total


def _boundary_hole_loops_for_autofix(mesh):
    edge_to_faces, _edge_directions = _edge_face_data(mesh)
    edge_by_key = {
        tuple(sorted(edge.vertices)): edge.index
        for edge in mesh.edges
    }
    boundary_edges = {
        edge_by_key[key]
        for key, faces in edge_to_faces.items()
        if len(faces) == 1 and key in edge_by_key
    }
    if not boundary_edges:
        return []

    vertex_to_edges = {}
    for edge_index in boundary_edges:
        edge = mesh.edges[edge_index]
        for vertex_index in edge.vertices:
            vertex_to_edges.setdefault(vertex_index, set()).add(edge_index)

    loops = []
    visited = set()
    for edge_index in boundary_edges:
        if edge_index in visited:
            continue

        component = []
        stack = [edge_index]
        visited.add(edge_index)
        while stack:
            current = stack.pop()
            component.append(current)
            for vertex_index in mesh.edges[current].vertices:
                for next_edge in vertex_to_edges.get(vertex_index, ()):
                    if next_edge in visited:
                        continue
                    visited.add(next_edge)
                    stack.append(next_edge)

        if len(component) <= AUTOFIX_MAX_HOLE_EDGE_COUNT:
            loops.append(sorted(component))

    loops.sort(key=len)
    return loops[:AUTOFIX_MAX_HOLE_LOOPS]


def _fill_boundary_hole_loop_for_autofix(context, target, edge_indices):
    if not edge_indices:
        return 0

    before_face_count = len(target.data.polygons)
    _select_edges(context, target, edge_indices)
    try:
        bpy.ops.mesh.fill()
    except RuntimeError:
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        return 0
    bpy.ops.object.mode_set(mode="OBJECT")

    return 1 if len(target.data.polygons) > before_face_count else 0


def _prepare_target_for_autofix(context, target):
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    context.view_layer.objects.active = target


def _apply_arc_cutters_to_mesh(context, target, cutters):
    marked_edges = 0
    _center, target_diagonal = _target_bounds(target)
    knife_extension_distance = target_diagonal * 2.0
    apply_method = _cutter_apply_method(context)
    boolean_solver = _cutter_boolean_solver(context)
    for cutter in cutters:
        if apply_method == "BOOLEAN":
            marked_edges += _apply_boolean_cutter_to_mesh(
                context,
                target,
                cutter,
                boolean_solidify_thickness=BOOLEAN_CUTTER_SOLIDIFY_THICKNESS,
                extension_distance=0.0,
                boolean_solver=boolean_solver,
            )
        else:
            marked_edges += _apply_knife_intersect_cutter_to_mesh(
                context,
                target,
                cutter,
                extension_distance=knife_extension_distance,
            )
    return marked_edges


def _apply_plane_cutters_to_mesh(target, cutters):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)

    marked_edges = 0
    for cutter in cutters:
        for plane in _cutter_planes_world(cutter):
            local_plane = _world_plane_to_local(target, plane[0], plane[1])
            if local_plane is None:
                continue

            geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
            result = bmesh.ops.bisect_plane(
                bm,
                geom=geom,
                plane_co=local_plane[0],
                plane_no=local_plane[1],
                clear_inner=False,
                clear_outer=False,
            )

            for element in result.get("geom_cut", ()):
                if isinstance(element, bmesh.types.BMEdge):
                    if not element.seam:
                        marked_edges += 1
                    element.seam = True
                    element.select_set(True)

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return marked_edges


def _apply_cutters_to_mesh(context, target, cutters):
    settings = context.scene.polygroups_object_seam_cutter_settings
    if settings.auto_convert_draw_strokes_on_apply:
        original_cutters = cutters
        converted_cutters = []
        for stroke in _draw_strokes_from_cutters(cutters):
            cutter = _convert_draw_stroke_to_cutter_path(context, stroke)
            if cutter is not None:
                converted_cutters.append(cutter)
        cutters = [
            cutter
            for cutter in cutters
            if cutter.get(CUTTER_TYPE_PROP) != "DRAW_STROKE"
        ] + converted_cutters
        if isinstance(original_cutters, list):
            original_cutters[:] = cutters

    plane_cutters = [cutter for cutter in cutters if cutter.get(CUTTER_TYPE_PROP) == "PLANE"]
    arc_cutters = [cutter for cutter in cutters if cutter.get(CUTTER_TYPE_PROP) == "ARC"]
    boolean_cutters = [
        cutter
        for cutter in cutters
        if cutter.get(CUTTER_TYPE_PROP) in {"PATH", "LOCAL_RING"}
    ]

    marked_edges = 0
    if plane_cutters:
        marked_edges += _apply_plane_cutters_to_mesh(target, plane_cutters)
    if arc_cutters:
        marked_edges += _apply_arc_cutters_to_mesh(context, target, arc_cutters)

    apply_method = _cutter_apply_method(context)
    boolean_solver = _cutter_boolean_solver(context)
    for cutter in boolean_cutters:
        if apply_method == "KNIFE":
            marked_edges += _apply_knife_intersect_cutter_to_mesh(
                context,
                target,
                cutter,
                boolean_solidify_thickness=BOOLEAN_CUTTER_SOLIDIFY_THICKNESS,
            )
        else:
            cutter_type = cutter.get(CUTTER_TYPE_PROP)
            solidify_thickness = (
                BOOLEAN_CUTTER_SOLIDIFY_THICKNESS
                if cutter_type in {"PATH", "LOCAL_RING"}
                else None
            )
            marked_edges += _apply_boolean_cutter_to_mesh(
                context,
                target,
                cutter,
                boolean_solidify_thickness=solidify_thickness,
                boolean_solver=boolean_solver,
            )

    return marked_edges


def _has_knife_cleanup_cutters(cutters):
    return any(
        cutter.get(CUTTER_TYPE_PROP) in {"ARC", "PATH", "LOCAL_RING"}
        for cutter in cutters
    )


def _has_boolean_solidify_cutters(cutters):
    return any(
        cutter.get(CUTTER_TYPE_PROP) in {"ARC", "PATH", "LOCAL_RING"}
        for cutter in cutters
    )


def _split_supported_cutters(cutters):
    return [
        cutter
        for cutter in cutters
        if cutter.get(CUTTER_TYPE_PROP) in {"PLANE", "ARC"}
    ]


def _draw_cutter_overlay(operator):
    if operator._start_pos is None:
        return

    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    start = Vector(operator._start_pos)
    end = Vector(operator._mouse_pos or operator._start_pos)
    color = (0.1, 0.65, 1.0, 1.0)
    guide_color = (1.0, 0.78, 0.18, 0.55)
    label_color = (1.0, 1.0, 1.0, 1.0)

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    def draw_lines(points, line_color):
        batch = batch_for_shader(shader, "LINES", {"pos": points})
        shader.bind()
        shader.uniform_float("color", line_color)
        batch.draw(shader)

    cross_size = 7.0
    points = [
        (start.x - cross_size, start.y),
        (start.x + cross_size, start.y),
        (start.x, start.y - cross_size),
        (start.x, start.y + cross_size),
    ]

    if (end - start).length > 1.0:
        if getattr(operator, "_shift_locked", False) and operator._start_region is not None:
            if _axis_lock_mode(start, end) == "HORIZONTAL":
                guide = [(0.0, start.y), (operator._start_region.width, start.y)]
            else:
                guide = [(start.x, 0.0), (start.x, operator._start_region.height)]
            draw_lines(guide, guide_color)

        points.extend(
            [
                (start.x, start.y),
                (end.x, end.y),
                (end.x - cross_size, end.y),
                (end.x + cross_size, end.y),
                (end.x, end.y - cross_size),
                (end.x, end.y + cross_size),
            ]
        )

    draw_lines(points, color)

    font_id = 0
    try:
        blf.size(font_id, 14)
    except TypeError:
        blf.size(font_id, 14, 72)

    blf.color(font_id, *label_color)
    blf.position(font_id, start.x + 10.0, start.y + 10.0, 0)
    blf.draw(font_id, "A")

    if (end - start).length > 1.0:
        blf.position(font_id, end.x + 10.0, end.y + 10.0, 0)
        blf.draw(font_id, "B")


def _draw_cutter_arc_overlay(operator):
    if not operator._points:
        return

    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    color = (0.1, 0.85, 1.0, 1.0)
    label_color = (1.0, 1.0, 1.0, 1.0)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    preview_points = list(operator._points)
    if operator._mouse_pos is not None and len(preview_points) < 3:
        preview_points.append(operator._mouse_pos)

    line_points = []
    if len(preview_points) == 3:
        arc_points = _screen_arc_points(
            preview_points[0],
            preview_points[1],
            preview_points[2],
            max(operator._preview_segments, 8),
        )
        if arc_points is not None:
            for start, end in zip(arc_points, arc_points[1:]):
                line_points.extend([start, end])

    if not line_points and len(preview_points) > 1:
        for start, end in zip(preview_points, preview_points[1:]):
            line_points.extend([start, end])

    cross_size = 7.0
    for point in preview_points:
        position = Vector(point)
        line_points.extend(
            [
                (position.x - cross_size, position.y),
                (position.x + cross_size, position.y),
                (position.x, position.y - cross_size),
                (position.x, position.y + cross_size),
            ]
        )

    if line_points:
        batch = batch_for_shader(shader, "LINES", {"pos": line_points})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    font_id = 0
    try:
        blf.size(font_id, 14)
    except TypeError:
        blf.size(font_id, 14, 72)

    labels = ("A", "B", "C")
    blf.color(font_id, *label_color)
    for index, point in enumerate(preview_points[:3]):
        position = Vector(point)
        blf.position(font_id, position.x + 10.0, position.y + 10.0, 0)
        blf.draw(font_id, labels[index])


def _draw_cutter_path_overlay(operator):
    if not getattr(operator, "_surface_points", None) and not getattr(operator, "_points", None):
        return

    try:
        import blf
        import gpu
        from bpy_extras import view3d_utils
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    color = (0.15, 1.0, 0.55, 1.0)
    label_color = (1.0, 1.0, 1.0, 1.0)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    preview_points = []
    region = getattr(operator, "_start_region", None)
    rv3d = getattr(operator, "_start_rv3d", None)
    surface_points = getattr(operator, "_surface_points", None) or []
    mouse_surface_point = getattr(operator, "_mouse_surface_point", None)
    if region is not None and rv3d is not None and surface_points:
        world_points = [item["location"] for item in surface_points]
        if mouse_surface_point is not None:
            world_points.append(mouse_surface_point["location"])
        for location in world_points:
            point = view3d_utils.location_3d_to_region_2d(region, rv3d, location)
            if point is not None:
                preview_points.append(point)
    else:
        preview_points = list(operator._points)
        if operator._mouse_pos is not None:
            preview_points.append(operator._mouse_pos)

    if not preview_points:
        return

    line_points = []
    if len(preview_points) > 1:
        for start, end in zip(preview_points, preview_points[1:]):
            line_points.extend([start, end])

    cross_size = 6.0
    for point in preview_points:
        position = Vector(point)
        line_points.extend(
            [
                (position.x - cross_size, position.y),
                (position.x + cross_size, position.y),
                (position.x, position.y - cross_size),
                (position.x, position.y + cross_size),
            ]
        )

    if line_points:
        batch = batch_for_shader(shader, "LINES", {"pos": line_points})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    font_id = 0
    try:
        blf.size(font_id, 13)
    except TypeError:
        blf.size(font_id, 13, 72)

    blf.color(font_id, *label_color)
    for index, point in enumerate(preview_points):
        if index >= 26:
            label = str(index + 1)
        else:
            label = chr(ord("A") + index)
        position = Vector(point)
        blf.position(font_id, position.x + 9.0, position.y + 9.0, 0)
        blf.draw(font_id, label)


def _draw_cutter_local_ring_overlay(operator):
    if operator._start_pos is None:
        return

    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    start = Vector(operator._start_pos)
    end = Vector(operator._mouse_pos or operator._start_pos)
    guide_color = (1.0, 0.78, 0.18, 0.85)
    label_color = (1.0, 1.0, 1.0, 1.0)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    guide_points = [(start.x, start.y), (end.x, end.y)]
    cross_size = 6.0
    for point in (start, end):
        guide_points.extend(
            [
                (point.x - cross_size, point.y),
                (point.x + cross_size, point.y),
                (point.x, point.y - cross_size),
                (point.x, point.y + cross_size),
            ],
        )
    batch = batch_for_shader(shader, "LINES", {"pos": guide_points})
    shader.bind()
    shader.uniform_float("color", guide_color)
    batch.draw(shader)

    font_id = 0
    try:
        blf.size(font_id, 13)
    except TypeError:
        blf.size(font_id, 13, 72)
    blf.color(font_id, *label_color)
    for label, point in (("A", start), ("B", end)):
        blf.position(font_id, point.x + 9.0, point.y + 9.0, 0)
        blf.draw(font_id, label)


class OBJECT_OT_polygroups_draw_cutter_plane(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_plane"
    bl_label = "Draw Cutter Plane"
    bl_description = "Draw an object-mode cutter plane from two viewport clicks"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the cutter start point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _start_pos = None
    _mouse_pos = None
    _draw_handle = None
    _shift_locked = False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._start_pos = None
        self._mouse_pos = None
        self._draw_handle = None
        self._shift_locked = False

        if self.use_event_as_start:
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if region is None:
                return {"CANCELLED"}

            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Cutter: A placed, click B. Hold Shift for horizontal/vertical lock")
        else:
            context.workspace.status_text_set("Object Seam Cutter: click A in the viewport. Hold Shift after A to lock axis")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._start_pos is not None and area == self._start_area and region == self._start_region:
                del rv3d
                self._shift_locked = event.shift
                self._mouse_pos = _axis_locked_region_pos(
                    self._start_pos,
                    region_pos,
                    self._shift_locked,
                )
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return {"RUNNING_MODAL"}

        if self._start_pos is None:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Cutter: A placed, click B. Hold Shift for horizontal/vertical lock")
            return {"RUNNING_MODAL"}

        if area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for both cutter points")
            return {"RUNNING_MODAL"}

        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        settings = context.scene.polygroups_object_seam_cutter_settings
        self._shift_locked = event.shift
        end_pos = _axis_locked_region_pos(self._start_pos, region_pos, self._shift_locked)
        plane = _screen_cut_plane(
            self._start_area,
            self._start_region,
            self._start_rv3d,
            self._start_pos,
            end_pos,
            target,
            settings.cutter_size_multiplier,
        )
        if plane is None:
            self.report({"WARNING"}, "Cutter line is too short")
            return {"RUNNING_MODAL"}

        cutter = _create_cutter_plane(
            "Seam_Cutter_Plane",
            plane[0],
            plane[1],
            plane[2],
            plane[3],
            settings.cutter_alpha,
            settings.cutter_solidify_thickness,
        )
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_draw_cutter_local_ring(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_local_ring"
    bl_label = "Draw Local Ring Cutter"
    bl_description = "Draw a local circular cutter disk from two viewport clicks"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the local ring start point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _start_pos = None
    _mouse_pos = None
    _draw_handle = None
    _shift_locked = False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._start_pos = None
        self._mouse_pos = None
        self._draw_handle = None
        self._shift_locked = False

        if self.use_event_as_start:
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if region is None:
                return {"CANCELLED"}
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Local Ring Cutter: A placed, click B to set diameter")
        else:
            context.workspace.status_text_set("Local Ring Cutter: click A in the viewport")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._start_pos is not None and area == self._start_area and region == self._start_region:
                del rv3d
                self._shift_locked = event.shift
                self._mouse_pos = _axis_locked_region_pos(
                    self._start_pos,
                    region_pos,
                    self._shift_locked,
                )
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return {"RUNNING_MODAL"}

        if self._start_pos is None:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Local Ring Cutter: A placed, click B to set diameter")
            return {"RUNNING_MODAL"}

        if area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for both local ring points")
            return {"RUNNING_MODAL"}

        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        settings = context.scene.polygroups_object_seam_cutter_settings
        self._shift_locked = event.shift
        end_pos = _axis_locked_region_pos(self._start_pos, region_pos, self._shift_locked)
        surface = _screen_local_ring_surface(
            self._start_area,
            self._start_region,
            self._start_rv3d,
            self._start_pos,
            end_pos,
            target,
            settings.cutter_local_ring_radius_offset,
            settings.cutter_local_ring_fit_mode,
        )
        if surface is None:
            self.report({"WARNING"}, "Local ring diameter is too short")
            return {"RUNNING_MODAL"}

        cutter = _create_cutter_local_ring(
            "Seam_Cutter_Local_Ring",
            surface[0],
            surface[1],
            surface[2],
            surface[3],
            settings.cutter_local_ring_segments,
            settings.cutter_alpha,
        )
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_local_ring_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_draw_cutter_arc(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_arc"
    bl_label = "Draw Cutter Arc"
    bl_description = "Draw an object-mode cutter arc from three viewport clicks"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the arc start point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _points = None
    _mouse_pos = None
    _draw_handle = None
    _preview_segments = 16

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._points = []
        self._mouse_pos = None
        self._draw_handle = None
        self._preview_segments = context.scene.polygroups_object_seam_cutter_settings.cutter_arc_segments

        if self.use_event_as_start:
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if region is None:
                return {"CANCELLED"}

            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._points.append(region_pos)
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Arc Cutter: A placed, click B")
        else:
            context.workspace.status_text_set("Object Seam Arc Cutter: click A in the viewport")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._points and area == self._start_area and region == self._start_region:
                del rv3d
                self._mouse_pos = region_pos
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return {"RUNNING_MODAL"}

        if not self._points:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._points.append(region_pos)
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Arc Cutter: A placed, click B")
            return {"RUNNING_MODAL"}

        if area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for all arc points")
            return {"RUNNING_MODAL"}

        self._points.append(region_pos)
        self._mouse_pos = region_pos
        if len(self._points) == 2:
            context.workspace.status_text_set("Object Seam Arc Cutter: B placed, click C")
            self._tag_redraw()
            return {"RUNNING_MODAL"}

        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        settings = context.scene.polygroups_object_seam_cutter_settings
        surface = _screen_arc_surface(
            self._start_area,
            self._start_region,
            self._start_rv3d,
            self._points[0],
            self._points[1],
            self._points[2],
            target,
            settings.cutter_size_multiplier,
            settings.cutter_arc_segments,
        )
        if surface is None:
            self.report({"WARNING"}, "Arc points are too close or almost collinear")
            self._points.pop()
            return {"RUNNING_MODAL"}

        cutter = _create_cutter_arc(
            "Seam_Cutter_Arc",
            surface[0],
            surface[1],
            surface[2],
            settings.cutter_alpha,
            settings.cutter_solidify_thickness,
        )
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_arc_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_draw_cutter_path(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_path"
    bl_label = "Draw Cutter Path"
    bl_description = "Draw an object-mode cutter path snapped to the active mesh surface"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the first path point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _points = None
    _surface_points = None
    _mouse_pos = None
    _mouse_surface_point = None
    _draw_handle = None
    _view_navigation_active = False

    def _is_view_navigation_event(self, event):
        if event.type == "MOUSEMOVE" and self._view_navigation_active:
            return True

        if event.type in {"MIDDLEMOUSE", "LEFTMOUSE"} and event.value == "RELEASE":
            self._view_navigation_active = False
            if event.type == "MIDDLEMOUSE":
                return True

        if event.type == "MIDDLEMOUSE" and event.value == "PRESS":
            self._view_navigation_active = True
            return True

        if event.type == "LEFTMOUSE" and event.alt:
            if event.value == "PRESS":
                self._view_navigation_active = True
            return True

        if event.type in {
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "WHEELINMOUSE",
            "WHEELOUTMOUSE",
            "TRACKPADPAN",
            "TRACKPADZOOM",
            "NDOF_MOTION",
            "NDOF_BUTTON_MENU",
            "NDOF_BUTTON_FIT",
            "NDOF_BUTTON_TOP",
            "NDOF_BUTTON_BOTTOM",
            "NDOF_BUTTON_LEFT",
            "NDOF_BUTTON_RIGHT",
            "NDOF_BUTTON_FRONT",
            "NDOF_BUTTON_BACK",
        }:
            return True

        return False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._points = []
        self._surface_points = []
        self._mouse_pos = None
        self._mouse_surface_point = None
        self._draw_handle = None
        self._view_navigation_active = False

        if self.use_event_as_start:
            if not self._add_point_from_event(context, event):
                return {"CANCELLED"}
            self._add_draw_handler()
            context.workspace.status_text_set(
                "Object Seam Path Cutter: Ctrl+Click points, navigate view normally, Enter/Space to confirm",
            )
        else:
            context.workspace.status_text_set("Object Seam Path Cutter: Ctrl+Click first surface point")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if self._is_view_navigation_event(event):
            return {"PASS_THROUGH"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type in {"RET", "NUMPAD_ENTER", "SPACE"} and event.value == "PRESS":
            if len(self._surface_points) < 2:
                self.report({"WARNING"}, "Cutter path needs at least two points")
                return {"RUNNING_MODAL"}
            return self._create_path(context)

        if event.type == "BACK_SPACE" and event.value == "PRESS":
            if self._surface_points:
                self._points.pop()
                self._surface_points.pop()
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._surface_points and area == self._start_area and region == self._start_region:
                self._mouse_pos = region_pos
                self._mouse_surface_point = self._surface_point_from_region(context, region, rv3d, region_pos)
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"PASS_THROUGH"}

        if not event.ctrl:
            return {"PASS_THROUGH"}

        if not self._add_point_from_event(context, event):
            return {"RUNNING_MODAL"}

        if self._draw_handle is None:
            self._add_draw_handler()
        context.workspace.status_text_set(
            "Object Seam Path Cutter: Ctrl+Click points, navigate view normally, Enter/Space to confirm",
        )
        return {"RUNNING_MODAL"}

    def _add_point_from_event(self, context, event):
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            return False

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return False

        if not self._points:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
        elif area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for all path points")
            return False

        hit = _surface_hit_from_region_pos(region, rv3d, region_pos, target)
        if hit is None:
            self.report({"WARNING"}, "No surface under cursor")
            return False

        if self._surface_points:
            previous = self._surface_points[-1]["location"]
            if (hit[0] - previous).length < 0.000001:
                return False

        self._points.append(region_pos)
        self._surface_points.append(
            {
                "location": hit[0],
                "normal": hit[1],
            },
        )
        self._mouse_pos = region_pos
        self._mouse_surface_point = None
        self._tag_redraw()
        return True

    def _surface_point_from_region(self, context, region, rv3d, region_pos):
        del context
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            return None

        hit = _surface_hit_from_region_pos(region, rv3d, region_pos, target)
        if hit is None:
            return None

        if self._surface_points and (hit[0] - self._surface_points[-1]["location"]).length < 0.000001:
            return None

        return {
            "location": hit[0],
            "normal": hit[1],
        }

    def _create_path(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        cutter = None
        if settings.continue_path_cutters:
            cutter, joined_points = _find_path_to_continue(
                self._surface_points,
                settings.cutter_path_join_distance,
            )
            if cutter is not None:
                _write_cutter_path_points(cutter, joined_points)

        if cutter is None:
            cutter = _create_cutter_path(
                "Seam_Cutter_Path",
                self._surface_points,
                settings.cutter_path_render_u,
                settings.cutter_path_extrude,
                settings.cutter_alpha,
            )
        bpy.ops.object.select_all(action="DESELECT")
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_path_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._mouse_surface_point = None
        self._tag_redraw()


class OBJECT_OT_polygroups_draw_cutter_draw(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_draw"
    bl_label = "Draw Cutter Path"
    bl_description = "Draw a freehand cutter path snapped to the active mesh surface"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the first stroke point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _points = None
    _surface_points = None
    _mouse_pos = None
    _draw_handle = None
    _view_navigation_active = False
    _is_drawing = False

    def _is_view_navigation_event(self, event):
        if event.type == "MOUSEMOVE" and self._view_navigation_active:
            return True

        if event.type in {"MIDDLEMOUSE", "LEFTMOUSE"} and event.value == "RELEASE":
            self._view_navigation_active = False
            if event.type == "MIDDLEMOUSE":
                return True

        if event.type == "MIDDLEMOUSE" and event.value == "PRESS":
            self._view_navigation_active = True
            return True

        if event.type == "LEFTMOUSE" and event.alt:
            if event.value == "PRESS":
                self._view_navigation_active = True
            return True

        if event.type in {
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "WHEELINMOUSE",
            "WHEELOUTMOUSE",
            "TRACKPADPAN",
            "TRACKPADZOOM",
            "NDOF_MOTION",
            "NDOF_BUTTON_MENU",
            "NDOF_BUTTON_FIT",
            "NDOF_BUTTON_TOP",
            "NDOF_BUTTON_BOTTOM",
            "NDOF_BUTTON_LEFT",
            "NDOF_BUTTON_RIGHT",
            "NDOF_BUTTON_FRONT",
            "NDOF_BUTTON_BACK",
        }:
            return True

        return False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._points = []
        self._surface_points = []
        self._mouse_pos = None
        self._draw_handle = None
        self._view_navigation_active = False
        self._is_drawing = False

        if self.use_event_as_start:
            self._is_drawing = True
            if not self._add_point_from_event(context, event, force=True):
                return {"CANCELLED"}
            self._add_draw_handler()
        context.workspace.status_text_set(
            "Object Seam Draw Cutter: hold Ctrl and drag on surface, release to finish",
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not self._is_drawing and self._is_view_navigation_event(event):
            return {"PASS_THROUGH"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS" and event.ctrl:
            self._is_drawing = True
            self._add_point_from_event(context, event, force=True)
            if self._draw_handle is None:
                self._add_draw_handler()
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._points and area == self._start_area and region == self._start_region:
                del rv3d
                self._mouse_pos = region_pos
                self._tag_redraw()
            if self._is_drawing and event.ctrl:
                self._add_point_from_event(context, event)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._is_drawing:
            self._add_point_from_event(context, event)
            if len(self._surface_points) < 2:
                self.report({"WARNING"}, "Cutter draw stroke needs at least two points")
                self._finish(context)
                return {"CANCELLED"}
            return self._create_draw_result(context)

        return {"PASS_THROUGH"}

    def _add_point_from_event(self, context, event, force=False):
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            return False

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return False

        if not self._points:
            self._start_area = area
            self._start_region = region
        elif area != self._start_area or region != self._start_region:
            return False

        hit = _surface_hit_from_region_pos(region, rv3d, region_pos, target)
        if hit is None:
            return False

        settings = context.scene.polygroups_object_seam_cutter_settings
        if self._surface_points and not force:
            previous = self._surface_points[-1]["location"]
            if (hit[0] - previous).length < settings.cutter_draw_min_point_distance:
                return False

        self._points.append(region_pos)
        self._surface_points.append(
            {
                "location": hit[0],
                "normal": hit[1],
            },
        )
        self._mouse_pos = region_pos
        self._tag_redraw()
        return True

    def _create_draw_result(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        path_points = _simplify_path_points(
            self._surface_points,
            settings.cutter_draw_simplify_distance,
        )

        cutter = None
        if settings.continue_path_cutters:
            cutter, joined_points = _find_path_to_continue(
                path_points,
                settings.cutter_path_join_distance,
            )
            if cutter is not None:
                _write_cutter_path_points(cutter, joined_points)

        if cutter is None:
            cutter = _create_cutter_path(
                "Seam_Cutter_Path",
                path_points,
                settings.cutter_path_render_u,
                settings.cutter_path_extrude,
                settings.cutter_alpha,
                "DRAW",
            )

        bpy.ops.object.select_all(action="DESELECT")
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_path_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_convert_draw_strokes_to_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_convert_draw_strokes_to_cutter_paths"
    bl_label = "Convert Draw Strokes To Cutter Paths"
    bl_description = "Convert freehand cutter draw strokes to cutter path curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected = [
            obj
            for obj in context.selected_objects
            if obj.type == "CURVE" and obj.get(CUTTER_PROP) and obj.get(CUTTER_TYPE_PROP) == "DRAW_STROKE"
        ]
        strokes = selected or _draw_strokes_from_cutters(_selected_cutters(context, context.active_object))
        if not strokes:
            self.report({"WARNING"}, "No cutter draw strokes found")
            return {"CANCELLED"}

        converted = []
        for stroke in strokes:
            cutter = _convert_draw_stroke_to_cutter_path(context, stroke)
            if cutter is not None:
                converted.append(cutter)

        if not converted:
            self.report({"WARNING"}, "No cutter draw strokes could be converted")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        for cutter in converted:
            cutter.select_set(True)
        context.view_layer.objects.active = converted[-1]
        self.report({"INFO"}, f"Converted {len(converted)} draw stroke(s) to cutter path(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_join_draw_strokes(bpy.types.Operator):
    bl_idname = "object.polygroups_join_draw_strokes"
    bl_label = "Join Selected Draw Strokes"
    bl_description = "Join selected cutter draw strokes into one continuous draw stroke"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        strokes = [
            obj
            for obj in context.selected_objects
            if obj.type == "CURVE" and obj.get(CUTTER_PROP) and obj.get(CUTTER_TYPE_PROP) == "DRAW_STROKE"
        ]
        if len(strokes) < 2:
            self.report({"WARNING"}, "Select at least two cutter draw strokes")
            return {"CANCELLED"}

        stroke, joined_count = _join_draw_strokes(strokes, settings.cutter_draw_join_distance)
        if stroke is None or not joined_count:
            self.report({"WARNING"}, "No draw strokes were close enough to join")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        stroke.select_set(True)
        context.view_layer.objects.active = stroke
        self.report({"INFO"}, f"Joined {joined_count + 1} draw stroke(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_join_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_join_cutter_paths"
    bl_label = "Join Selected Cutter Paths"
    bl_description = "Join selected cutter path curves into one continuous cutter path"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        paths = [
            obj
            for obj in context.selected_objects
            if obj.type == "CURVE" and obj.get(CUTTER_PROP) and obj.get(CUTTER_TYPE_PROP) == "PATH"
        ]
        if len(paths) < 2:
            self.report({"WARNING"}, "Select at least two cutter paths")
            return {"CANCELLED"}

        path, joined_count = _join_path_cutters(paths, settings.cutter_path_join_distance)
        if path is None or not joined_count:
            self.report({"WARNING"}, "No cutter paths were close enough to join")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        path.select_set(True)
        context.view_layer.objects.active = path
        self.report({"INFO"}, f"Joined {joined_count + 1} cutter path(s)")
        return {"FINISHED"}


def _run_selected_cutter_curve_edit_op(context, curves, operator_callback):
    original_active = context.view_layer.objects.active
    original_selection = tuple(context.selected_objects)
    changed = 0

    if context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass

    try:
        for obj in curves:
            if obj.name not in context.view_layer.objects:
                continue
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.curve.select_all(action="SELECT")
            operator_callback(obj)
            bpy.ops.object.mode_set(mode="OBJECT")
            _update_curve_path_data_from_splines(obj)
            changed += 1
    finally:
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        for obj in original_selection:
            if obj.name in context.view_layer.objects:
                obj.select_set(True)
        if original_active and original_active.name in context.view_layer.objects:
            context.view_layer.objects.active = original_active

    return changed


class OBJECT_OT_polygroups_bezier_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_bezier_cutter_paths"
    bl_label = "Bezier Cutter Paths"
    bl_description = "Convert selected cutter path and draw curves to Bezier splines with automatic handles"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def convert_to_bezier(obj):
            del obj
            try:
                bpy.ops.curve.spline_type_set(type="BEZIER")
            except RuntimeError:
                pass
            try:
                bpy.ops.curve.handle_type_set(type="AUTO")
            except (RuntimeError, TypeError):
                try:
                    bpy.ops.curve.handle_type_set(type="AUTOMATIC")
                except (RuntimeError, TypeError):
                    pass

        changed = _run_selected_cutter_curve_edit_op(context, curves, convert_to_bezier)
        for obj in curves:
            for spline in obj.data.splines:
                if spline.type != "BEZIER":
                    continue
                for point in spline.bezier_points:
                    _set_bezier_handle_auto(point)
                    if hasattr(point, "tilt") and abs(point.tilt) < 0.000001:
                        point.tilt = DEFAULT_CUTTER_PATH_TILT
            obj.data.update_tag()

        self.report({"INFO"}, f"Converted {changed} cutter curve(s) to Bezier")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_toggle_cyclic_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_toggle_cyclic_cutter_paths"
    bl_label = "Toggle Cyclic Cutter Paths"
    bl_description = "Toggle cyclic state on selected cutter path and draw curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def toggle_cyclic(obj):
            try:
                bpy.ops.curve.cyclic_toggle(direction="CYCLIC_U")
            except (RuntimeError, TypeError):
                for spline in obj.data.splines:
                    spline.use_cyclic_u = not spline.use_cyclic_u

        changed = _run_selected_cutter_curve_edit_op(context, curves, toggle_cyclic)
        self.report({"INFO"}, f"Toggled cyclic on {changed} cutter curve(s)")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_smooth_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_smooth_cutter_paths"
    bl_label = "Smooth Cutter Paths"
    bl_description = "Smooth selected cutter path and draw curve points"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def smooth_curve(obj):
            del obj
            try:
                bpy.ops.curve.smooth()
            except RuntimeError:
                pass

        changed = _run_selected_cutter_curve_edit_op(context, curves, smooth_curve)
        self.report({"INFO"}, f"Smoothed {changed} cutter curve(s)")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_smooth_cutter_path_tilt(bpy.types.Operator):
    bl_idname = "object.polygroups_smooth_cutter_path_tilt"
    bl_label = "Smooth Cutter Path Tilt"
    bl_description = "Smooth tilt values on selected cutter path and draw curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def smooth_tilt(obj):
            del obj
            try:
                bpy.ops.curve.smooth_tilt()
            except RuntimeError:
                pass

        changed = _run_selected_cutter_curve_edit_op(context, curves, smooth_tilt)
        self.report({"INFO"}, f"Smoothed tilt on {changed} cutter curve(s)")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_tilt_cutter_path(bpy.types.Operator):
    bl_idname = "object.polygroups_tilt_cutter_path"
    bl_label = "Tilt Cutter Path"
    bl_description = "Apply tilt to selected cutter path curves"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        items=(
            ("DECREASE", "Decrease", "Decrease tilt"),
            ("INCREASE", "Increase", "Increase tilt"),
            ("RESET", "Reset", "Reset tilt"),
        ),
        default="INCREASE",
    )

    def execute(self, context):
        if context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        delta = CUTTER_PATH_TILT_STEP
        if self.mode == "DECREASE":
            delta = -delta

        changed = 0
        changed_objects = []
        for obj in context.selected_objects:
            if (
                obj.type != "CURVE"
                or not obj.get(CUTTER_PROP)
                or obj.get(CUTTER_TYPE_PROP) not in {"PATH", "DRAW_STROKE"}
            ):
                continue

            object_changed = False
            for spline in obj.data.splines:
                for point in _curve_spline_points(spline):
                    if not hasattr(point, "tilt"):
                        continue
                    if self.mode == "RESET":
                        point.tilt = DEFAULT_CUTTER_PATH_TILT
                    else:
                        point.tilt += delta
                    changed += 1
                    object_changed = True
            if object_changed:
                _update_curve_path_data_from_splines(obj)
                changed_objects.append(obj)

        if not changed:
            self.report({"WARNING"}, "No selected cutter path curves")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        for obj in changed_objects:
            obj.select_set(True)
        context.view_layer.objects.active = changed_objects[0]
        bpy.ops.object.mode_set(mode="OBJECT")
        self.report({"INFO"}, f"Updated tilt on {changed} path point(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_copy_mirror_cutters(bpy.types.Operator):
    bl_idname = "object.polygroups_copy_mirror_cutters"
    bl_label = "Copy Mirror Cutters"
    bl_description = "Copy selected cutter objects and mirror them in Object Mode around the active mesh origin"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = context.active_object
        return (
            _is_target_mesh_candidate(target)
            and bool(_selected_cutters_only(context))
        )

    def execute(self, context):
        target = context.active_object
        cutters = _selected_cutters_only(context)
        settings = context.scene.polygroups_object_seam_cutter_settings
        if target is None or not cutters:
            self.report({"WARNING"}, "Select cutter objects and make the mirror mesh active")
            return {"CANCELLED"}

        mirror_matrix = _mirror_matrix_from_target(target, settings.cutter_mirror_axis)
        mirrored_cutters = []
        for cutter in cutters:
            mirrored = _copy_mirror_cutter(cutter, mirror_matrix)
            if mirrored is not None:
                mirrored_cutters.append(mirrored)
        if not mirrored_cutters:
            self.report({"WARNING"}, "Selected cutters could not be mirrored")
            return {"CANCELLED"}

        context.view_layer.objects.active = target
        target.select_set(True)
        self.report(
            {"INFO"},
            f"Copied and mirrored {len(mirrored_cutters)} cutter(s) on {settings.cutter_mirror_axis}",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_auto_fix_after_cutter(bpy.types.Operator):
    bl_idname = "object.polygroups_auto_fix_after_cutter"
    bl_label = "Autofix After Cutter"
    bl_description = "Run lightweight mesh autofix after cutter seams in cancelable steps"
    bl_options = {"REGISTER", "UNDO"}

    target_name: bpy.props.StringProperty(default="")

    _timer = None
    _stage = 0
    _hole_loops = None
    _before_total = 0
    _deleted_protrusions = 0
    _deleted_loose = 0
    _filled_holes = 0

    def _target(self, context):
        target = bpy.data.objects.get(self.target_name)
        if target is not None and target.type == "MESH":
            return target
        active = context.active_object
        if active is not None and active.type == "MESH":
            return active
        return None

    def _finish(self, context, target):
        after = _refresh_mesh_check(context, target)
        after_total = _fixable_issue_total(after)
        fixed_total = max(0, self._before_total - after_total)
        message = (
            f"Autofix finished: {fixed_total} issue(s), "
            f"{self._deleted_protrusions} protrusion face(s), "
            f"{self._deleted_loose} loose item(s), "
            f"{self._filled_holes} hole loop(s)"
        )
        self.report({"INFO"}, message)
        return {"FINISHED"}

    def _cleanup_timer(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def invoke(self, context, event):
        del event
        target = self._target(context)
        if target is None:
            self.report({"WARNING"}, "No mesh target found for autofix")
            return {"CANCELLED"}

        _prepare_target_for_autofix(context, target)
        self._stage = 0
        self._hole_loops = None
        self._deleted_protrusions = 0
        self._deleted_loose = 0
        self._filled_holes = 0
        self._before_total = _fixable_issue_total(analyze_mesh(target))
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "Autofix started. Press ESC to cancel.")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        target = self._target(context)
        if target is None:
            self._cleanup_timer(context)
            self.report({"WARNING"}, "Autofix cancelled: mesh target was removed")
            return {"CANCELLED"}

        if event.type == "ESC":
            self._cleanup_timer(context)
            _prepare_target_for_autofix(context, target)
            _refresh_mesh_check(context, target, "Autofix cancelled")
            self.report({"INFO"}, "Autofix cancelled")
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"RUNNING_MODAL"}

        _prepare_target_for_autofix(context, target)
        if self._stage == 0:
            edge_to_faces, _edge_directions = _edge_face_data(target.data)
            protrusion_faces = sorted(_thin_protrusion_faces(target.data, edge_to_faces))
            if len(protrusion_faces) <= AUTOFIX_MAX_PROTRUSION_FACES:
                self._deleted_protrusions = _delete_faces_by_indices(context, target, protrusion_faces)
            self._stage = 1
            return {"RUNNING_MODAL"}

        if self._stage == 1:
            self._deleted_loose = _delete_loose_geometry_for_autofix(context, target)
            self._stage = 2
            return {"RUNNING_MODAL"}

        if self._stage == 2:
            self._hole_loops = _boundary_hole_loops_for_autofix(target.data)
            self._stage = 3
            return {"RUNNING_MODAL"}

        if self._stage == 3 and self._hole_loops:
            edge_indices = self._hole_loops.pop(0)
            self._filled_holes += _fill_boundary_hole_loop_for_autofix(context, target, edge_indices)
            return {"RUNNING_MODAL"}

        self._cleanup_timer(context)
        return self._finish(context, target)


class OBJECT_OT_polygroups_apply_cutter_seams(bpy.types.Operator):
    bl_idname = "object.polygroups_apply_cutter_seams"
    bl_label = "Apply Cutter Seams To Active"
    bl_description = "Apply selected cutter planes to the active mesh and mark cut edges as seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and _find_cutter_target(context) is not None
            and _has_selected_cutters_for_apply(context)
        )

    def execute(self, context):
        target = _find_cutter_target(context)
        if target is None:
            self.report({"WARNING"}, "No active mesh target found")
            return {"CANCELLED"}
        context.view_layer.objects.active = target
        settings = context.scene.polygroups_object_seam_cutter_settings
        cutters = [cutter for cutter in _selected_cutters_only(context) if cutter != target]
        if not cutters:
            self.report({"WARNING"}, "Select at least one cutter object")
            return {"CANCELLED"}

        apply_method = _cutter_apply_method(context)
        use_boolean_seam_cleanup = (
            apply_method == "BOOLEAN"
            and _has_boolean_solidify_cutters(cutters)
        )
        use_knife_seam_cleanup = (
            apply_method != "BOOLEAN"
            and _has_knife_cleanup_cutters(cutters)
        )
        open_edges_before = _count_open_boundary_edges(target) if use_knife_seam_cleanup else 0
        _clear_mesh_component_selection(target.data)
        marked_edges = _apply_cutters_to_mesh(context, target, cutters)
        if use_boolean_seam_cleanup and marked_edges:
            heal_distance = _boolean_seam_merge_distance(context)
            _merge_selected_cut_vertices(target, heal_distance)
        if use_knife_seam_cleanup and marked_edges:
            heal_distance = _arc_heal_distance(context)
            _merge_selected_cut_vertices(target, heal_distance)
            _merge_open_boundary_vertices(target, heal_distance)
            open_edges_after = _count_open_boundary_edges(target)
            if open_edges_after > open_edges_before:
                self.report(
                    {"WARNING"},
                    "Cutter seam applied, but open boundary edges remain. The local weld distance was not increased.",
                )

        settings.last_cutter_count = len(cutters)
        settings.last_marked_edge_count = marked_edges

        if settings.delete_cutters_after_apply:
            for cutter in cutters:
                bpy.data.objects.remove(cutter, do_unlink=True)
        elif settings.hide_cutters_after_apply:
            for cutter in cutters:
                cutter.hide_set(True)
                cutter.hide_viewport = True

        report_message = f"Applied {len(cutters)} cutter object(s), marked {marked_edges} seam edge(s)"
        self.report({"INFO"}, report_message)
        if settings.cutter_auto_fix_mesh and marked_edges:
            bpy.ops.object.polygroups_auto_fix_after_cutter("INVOKE_DEFAULT", target_name=target.name)
        play_operation_done_sound(context)
        return {"FINISHED"}


class OBJECT_OT_polygroups_split_object_by_cutters(bpy.types.Operator):
    bl_idname = "object.polygroups_split_object_by_cutters"
    bl_label = "Split Object"
    bl_description = "Split the active mesh into separate objects using selected cutter planes or arcs"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def execute(self, context):
        target = context.active_object
        settings = context.scene.polygroups_object_seam_cutter_settings
        cutters = _split_supported_cutters(_selected_cutters(context, target))
        if not cutters:
            self.report({"WARNING"}, "Select at least one cutter plane or arc")
            return {"CANCELLED"}

        _clear_mesh_component_selection(target.data)
        marked_edges = _apply_cutters_to_mesh(context, target, cutters)
        if not marked_edges:
            self.report({"WARNING"}, "No cut edges were created")
            return {"CANCELLED"}

        parts = _split_selected_edges(context, target, separate_objects=True)
        filled_faces = _fill_split_cut_boundaries(parts) if settings.fill_split_cutters else 0
        settings.last_cutter_count = len(cutters)
        settings.last_marked_edge_count = marked_edges

        if len(parts) > 4:
            self.report(
                {"WARNING"},
                "Split created many parts. Make sure the plane or arc fully crosses the mesh.",
            )
            return {"FINISHED"}

        self.report(
            {"INFO"},
            f"Split object with {len(cutters)} cutter object(s), created {len(parts)} part(s), filled {filled_faces} face(s)",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_select_cutter_planes(bpy.types.Operator):
    bl_idname = "object.polygroups_select_cutter_planes"
    bl_label = "Select Cutter Planes"
    bl_description = "Select all PolyGroups cutter plane objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.object.select_all(action="DESELECT")
        cutters = [
            obj
            for obj in _cutter_collection_objects()
            if obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
        ]
        if not cutters:
            return {"CANCELLED"}

        for obj in cutters:
            obj.hide_set(False)
            obj.hide_viewport = False
            obj.select_set(True)

        context.view_layer.objects.active = cutters[-1]
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_cutter_planes(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_cutter_planes"
    bl_label = "Clear Cutter Planes"
    bl_description = "Delete all PolyGroups cutter plane objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cutters = [
            obj
            for obj in _cutter_collection_objects()
            if obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
        ]
        if not cutters:
            return {"CANCELLED"}

        for cutter in cutters:
            bpy.data.objects.remove(cutter, do_unlink=True)
        return {"FINISHED"}
