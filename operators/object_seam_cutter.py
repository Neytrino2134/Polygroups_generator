import json
import bpy
from math import atan2
from math import cos
from math import radians
from math import sin
from math import tau
from mathutils import Matrix
from mathutils import Vector


CUTTER_COLLECTION_NAME = "Seam Cutters"
CUTTER_PROP = "polygroups_object_seam_cutter"
CUTTER_TYPE_PROP = "polygroups_object_seam_cutter_type"
CUTTER_PATH_DATA_PROP = "polygroups_object_seam_cutter_path_data"
CUTTER_SOLIDIFY_MODIFIER_NAME = "Cutter Plane Thickness"
BOOLEAN_PATH_TEMP_MATERIAL_NAME = "__AI_RETOPO_PATH_CUTTER_TEMP__"
BOOLEAN_PATH_PLACEHOLDER_MATERIAL_NAME = "__AI_RETOPO_PATH_ORIGINAL_TEMP__"


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


def _collection():
    collection = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(CUTTER_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    return collection


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
    obj.show_in_front = True
    obj.display_type = "TEXTURED"
    obj[CUTTER_PROP] = True
    obj[CUTTER_TYPE_PROP] = "PLANE"
    obj.data.materials.append(_material(alpha))
    _add_solidify_modifier(obj, thickness)
    _collection().objects.link(obj)
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
    obj.show_in_front = True
    obj.display_type = "TEXTURED"
    obj[CUTTER_PROP] = True
    obj[CUTTER_TYPE_PROP] = "ARC"
    obj.data.materials.append(_material(alpha))
    modifier = _add_solidify_modifier(obj, thickness)
    if hasattr(modifier, "use_rim"):
        modifier.use_rim = False
    _collection().objects.link(obj)
    return obj


def _create_cutter_path(name, path_points, render_u, extrude, alpha):
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

    obj = bpy.data.objects.new(name, curve)
    obj.show_in_front = True
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
    _collection().objects.link(obj)
    return obj


def _selected_cutters(context, target):
    cutters = [
        obj
        for obj in context.selected_objects
        if obj != target and obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
    ]
    if cutters:
        return cutters

    collection = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
    if collection is None:
        return []

    return [
        obj
        for obj in collection.objects
        if obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
    ]


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
            cutter.matrix_world @ Vector((point.co.x, point.co.y, point.co.z))
            for point in spline.points
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
        for point in cutter.data.splines[0].points:
            tilts.append(getattr(point, "tilt", 0.0))

    while len(tilts) < point_count:
        tilts.append(0.0)
    return tilts[:point_count]


def _path_data(cutter):
    try:
        data = json.loads(cutter.get(CUTTER_PATH_DATA_PROP, "[]"))
    except Exception:
        data = []
    return data if isinstance(data, list) else []


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


def _apply_boolean_modifier(context, target, cutter_mesh):
    modifier = target.modifiers.new("Cutter Path Boolean Seam", "BOOLEAN")
    modifier.operation = "UNION"
    modifier.solver = "FLOAT"
    modifier.object = cutter_mesh

    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def _mark_boolean_path_boundaries_and_remove_faces(target, temp_material_index, original_face_count):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()

    temp_faces = [
        face
        for face in bm.faces
        if face.material_index == temp_material_index
    ]
    if not temp_faces and original_face_count < len(bm.faces):
        temp_faces = [
            face
            for index, face in enumerate(bm.faces)
            if index >= original_face_count
        ]

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


def _apply_boolean_cutter_to_mesh(
    context,
    target,
    cutter,
    boolean_solidify_thickness=None,
    extension_distance=0.0,
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

    try:
        _apply_boolean_modifier(context, target, work)
        return _mark_boolean_path_boundaries_and_remove_faces(
            target,
            temp_material_index,
            original_face_count,
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


def _arc_boolean_thickness(context):
    model_settings = getattr(context.scene, "polygroups_model_preparation_settings", None)
    weld_distance = getattr(model_settings, "weld_distance", 0.0001)
    return max(min(weld_distance * 0.01, 0.000001), 0.0000001)


def _arc_heal_distance(context):
    model_settings = getattr(context.scene, "polygroups_model_preparation_settings", None)
    weld_distance = getattr(model_settings, "weld_distance", 0.0001)
    return weld_distance


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


def _apply_arc_cutters_to_mesh(context, target, cutters):
    marked_edges = 0
    boolean_thickness = _arc_boolean_thickness(context)
    _center, target_diagonal = _target_bounds(target)
    extension_distance = target_diagonal * 2.0
    for cutter in cutters:
        marked_edges += _apply_boolean_cutter_to_mesh(
            context,
            target,
            cutter,
            boolean_solidify_thickness=boolean_thickness,
            extension_distance=extension_distance,
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
    plane_cutters = [cutter for cutter in cutters if cutter.get(CUTTER_TYPE_PROP) == "PLANE"]
    arc_cutters = [cutter for cutter in cutters if cutter.get(CUTTER_TYPE_PROP) == "ARC"]
    boolean_cutters = [
        cutter
        for cutter in cutters
        if cutter.get(CUTTER_TYPE_PROP) == "PATH"
    ]

    marked_edges = 0
    if plane_cutters:
        marked_edges += _apply_plane_cutters_to_mesh(target, plane_cutters)
    if arc_cutters:
        marked_edges += _apply_arc_cutters_to_mesh(context, target, arc_cutters)

    for cutter in boolean_cutters:
        marked_edges += _apply_boolean_cutter_to_mesh(context, target, cutter)

    return marked_edges


def _has_arc_cutters(cutters):
    return any(cutter.get(CUTTER_TYPE_PROP) == "ARC" for cutter in cutters)


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
    if not operator._points:
        return

    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    color = (0.15, 1.0, 0.55, 1.0)
    label_color = (1.0, 1.0, 1.0, 1.0)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    preview_points = list(operator._points)
    if operator._mouse_pos is not None:
        preview_points.append(operator._mouse_pos)

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
            "Seam_Cutter",
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
            if self._points:
                self._points.pop()
                self._surface_points.pop()
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._points and area == self._start_area and region == self._start_region:
                del rv3d
                self._mouse_pos = region_pos
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
        self._tag_redraw()
        return True

    def _create_path(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

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
        self._tag_redraw()


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
        settings = context.scene.polygroups_object_seam_cutter_settings
        delta = radians(settings.cutter_path_tilt_step_degrees)
        if self.mode == "DECREASE":
            delta = -delta

        changed = 0
        for obj in context.selected_objects:
            if obj.type != "CURVE" or not obj.get(CUTTER_PROP) or obj.get(CUTTER_TYPE_PROP) != "PATH":
                continue

            for spline in obj.data.splines:
                for point in spline.points:
                    if not hasattr(point, "tilt"):
                        continue
                    if self.mode == "RESET":
                        point.tilt = 0.0
                    else:
                        point.tilt += delta
                    changed += 1

        if not changed:
            self.report({"WARNING"}, "No selected cutter path curves")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Updated tilt on {changed} path point(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_apply_cutter_seams(bpy.types.Operator):
    bl_idname = "object.polygroups_apply_cutter_seams"
    bl_label = "Apply Cutter Seams To Active"
    bl_description = "Apply selected cutter planes to the active mesh and mark cut edges as seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def execute(self, context):
        target = context.active_object
        settings = context.scene.polygroups_object_seam_cutter_settings
        cutters = _selected_cutters(context, target)
        if not cutters:
            self.report({"WARNING"}, "No cutter planes found")
            return {"CANCELLED"}

        use_arc_split_cleanup = _has_arc_cutters(cutters)
        open_edges_before = _count_open_boundary_edges(target) if use_arc_split_cleanup else 0
        _clear_mesh_component_selection(target.data)
        marked_edges = _apply_cutters_to_mesh(context, target, cutters)
        if use_arc_split_cleanup and marked_edges:
            heal_distance = _arc_heal_distance(context)
            _merge_selected_cut_vertices(target, heal_distance)
            _merge_open_boundary_vertices(target, heal_distance)
            open_edges_after = _count_open_boundary_edges(target)
            if open_edges_after > open_edges_before:
                self.report(
                    {"WARNING"},
                    "Arc seam applied, but open boundary edges remain. The local weld distance was not increased.",
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

        self.report(
            {"INFO"},
            f"Applied {len(cutters)} cutter object(s), marked {marked_edges} seam edge(s)",
        )
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
            f"Split object with {len(cutters)} cutter object(s), created {len(parts)} part(s)",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_select_cutter_planes(bpy.types.Operator):
    bl_idname = "object.polygroups_select_cutter_planes"
    bl_label = "Select Cutter Planes"
    bl_description = "Select all PolyGroups cutter plane objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.object.select_all(action="DESELECT")
        collection = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
        if collection is None:
            return {"CANCELLED"}

        selected = 0
        for obj in collection.objects:
            if obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP):
                obj.hide_set(False)
                obj.hide_viewport = False
                obj.select_set(True)
                selected += 1

        if selected:
            context.view_layer.objects.active = next(
                obj for obj in collection.objects if obj.select_get()
            )
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_cutter_planes(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_cutter_planes"
    bl_label = "Clear Cutter Planes"
    bl_description = "Delete all PolyGroups cutter plane objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collection = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
        if collection is None:
            return {"CANCELLED"}

        cutters = [
            obj
            for obj in collection.objects
            if obj.type in {"MESH", "CURVE"} and obj.get(CUTTER_PROP)
        ]
        for cutter in cutters:
            bpy.data.objects.remove(cutter, do_unlink=True)
        return {"FINISHED"}
