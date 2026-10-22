"""Cutter paths helpers."""
import json
from mathutils import Matrix
from mathutils import Vector
from .cutter_constants import (
    CUTTER_DRAW_DATA_PROP,
    CUTTER_PATH_DATA_PROP,
    CUTTER_PROP,
    CUTTER_TYPE_PROP,
    DEFAULT_CUTTER_PATH_TILT,
)


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


def _join_path_points(base_points, next_points):
    return _join_draw_stroke_points(base_points, next_points)


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
