"""Cutter objects helpers."""
import json
import bpy
from math import cos
from math import sin
from math import tau
from mathutils import Matrix
from .cutter_constants import (
    CUTTER_BACKUP_OWNER_PROP,
    CUTTER_COLLECTION_BY_TOOL,
    CUTTER_COLLECTION_NAME,
    CUTTER_DRAW_DATA_PROP,
    CUTTER_PATH_DATA_PROP,
    CUTTER_PROP,
    CUTTER_SOLIDIFY_MODIFIER_NAME,
    CUTTER_SOURCE_TOOL_PROP,
    CUTTER_TYPE_PROP,
    DEFAULT_CUTTER_PATH_TILT,
    DEFAULT_NON_PLANE_CUTTER_THICKNESS,
)
from .cutter_paths import (
    _draw_stroke_path_points,
    _join_draw_stroke_points,
    _join_path_points,
    _path_cutter_path_points,
    _simplify_path_points,
    _write_cutter_path_points,
    _write_draw_stroke_points,
)


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


def _is_local_contour_cutter(obj):
    if obj.type != "MESH" or obj.get(CUTTER_BACKUP_OWNER_PROP):
        return False
    base, dot, suffix = obj.name.rpartition(".")
    name = base if dot and suffix.isdigit() else obj.name
    return (
        name == "Local_Contour_Sketch"
        or bool(obj.get("polygroups_local_contour_sketch"))
        or any(collection.name == CUTTER_COLLECTION_BY_TOOL["LOCAL_CONTOUR"]
               for collection in obj.users_collection)
    )


def _is_cutter_object(obj):
    return obj.type in {"MESH", "CURVE"} and (
        bool(obj.get(CUTTER_PROP)) or _is_local_contour_cutter(obj)
    )


def _ensure_local_contour_cutter(obj):
    if _is_local_contour_cutter(obj):
        obj[CUTTER_PROP] = True
        if not obj.get(CUTTER_TYPE_PROP):
            obj[CUTTER_TYPE_PROP] = "LOCAL_CONTOUR"


def _tool_collection_type_for_cutter(cutter):
    cutter_type = cutter.get(CUTTER_TYPE_PROP)
    if cutter_type == "DRAW_STROKE":
        return "DRAW"
    return cutter_type or ("LOCAL_CONTOUR" if _is_local_contour_cutter(cutter) else "")


def _collection_objects_recursive(collection, seen=None):
    seen = set() if seen is None else seen
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
    objects = []
    seen = set()
    for name in (CUTTER_COLLECTION_NAME, *CUTTER_COLLECTION_BY_TOOL.values()):
        collection = bpy.data.collections.get(name)
        if collection is not None:
            objects.extend(_collection_objects_recursive(collection, seen))
    return objects


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


def _create_cutter_local_ring(name, center, axis_a, axis_b, radius, segments, alpha, thickness):
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
    modifier = _add_solidify_modifier(obj, thickness)
    if hasattr(modifier, "use_rim"):
        modifier.use_rim = True
    _tool_collection("LOCAL_RING").objects.link(obj)
    return obj


def _create_cutter_path(
    name, path_points, render_u, extrude, alpha, collection_type="PATH",
    thickness=DEFAULT_NON_PLANE_CUTTER_THICKNESS,
):
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
    obj[CUTTER_SOURCE_TOOL_PROP] = collection_type
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
    _add_solidify_modifier(obj, max(thickness, 0.0001))
    _tool_collection(collection_type).objects.link(obj)
    return obj


def _create_cutter_draw_stroke(
    name, path_points, render_u, alpha, thickness, extrude=0.1,
):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = render_u
    curve.render_resolution_u = render_u
    curve.extrude = extrude
    curve.bevel_depth = 0.0
    curve.bevel_resolution = 0

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
    obj[CUTTER_SOURCE_TOOL_PROP] = "DRAW"
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
    _add_solidify_modifier(obj, max(thickness, 0.0001))
    _tool_collection("DRAW").objects.link(obj)
    return obj


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
        settings.cutter_extrude,
        settings.cutter_alpha,
        collection_type="DRAW",
        thickness=settings.cutter_thickness,
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
        if obj != target and _is_cutter_object(obj)
    ]
    if cutters:
        return cutters

    return [
        obj
        for obj in _cutter_collection_objects()
        if _is_cutter_object(obj)
    ]


def _selected_cutters_only(context):
    return [
        obj
        for obj in context.selected_objects
        if _is_cutter_object(obj)
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
    if _is_local_contour_cutter(cutter):
        mirrored[CUTTER_PROP] = True
        mirrored[CUTTER_TYPE_PROP] = cutter.get(CUTTER_TYPE_PROP) or "LOCAL_CONTOUR"
    mirrored.name = f"{cutter.name}_Mirror"
    mirrored.matrix_world = mirror_matrix @ cutter.matrix_world

    _tool_collection(_tool_collection_type_for_cutter(cutter)).objects.link(mirrored)
    mirrored.select_set(True)
    return mirrored


def _apply_mirrored_cutter_scales(context, objects):
    """Apply only scale to the supplied objects, preserving location and rotation."""
    objects = [obj for obj in objects if obj is not None and obj.name in bpy.data.objects]
    if not objects:
        return False

    selected = list(context.selected_objects)
    active = context.view_layer.objects.active
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = objects[0]
    try:
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    except RuntimeError:
        return False
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if active is not None and active.name in bpy.data.objects:
            context.view_layer.objects.active = active
    return True


def _is_cutter_name(obj):
    return "Seam_Cutter" in obj.name


def _is_target_mesh_candidate(obj):
    return (
        obj is not None
        and obj.type == "MESH"
        and not _is_cutter_object(obj)
        and not obj.get("polygroups_local_contour_sketch")
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
