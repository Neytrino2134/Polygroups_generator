import os
import re
from array import array

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


BAKE_MATERIAL_NAME = "Bake_Target"
BAKE_BASE_COLOR_NODE = "PolyGroups Bake Base Color"
BAKE_NORMAL_NODE = "PolyGroups Bake Normal"
BAKE_TARGET_MATERIAL_PROP = "polygroups_bake_target_material"
BAKE_BASE_COLOR_IMAGE_PROP = "polygroups_bake_base_color_image"
BAKE_NORMAL_IMAGE_PROP = "polygroups_bake_normal_image"
BAKE_SOURCE_BASE_COLOR_IMAGE_PROP = "polygroups_bake_source_base_color_image"
BAKE_SOURCE_NORMAL_IMAGE_PROP = "polygroups_bake_source_normal_image"
BAKE_MERGED_BASE_COLOR_IMAGE_PROP = "polygroups_bake_merged_base_color_image"
BAKE_MERGED_NORMAL_IMAGE_PROP = "polygroups_bake_merged_normal_image"
BAKE_MERGED_MATERIAL_PROP = "polygroups_bake_merged_material"
BAKE_PACK_TYPE_PROP = "polygroups_bake_pack_type"
BAKE_PACK_NAME_PROP = "polygroups_bake_pack_name"
BAKE_PACK_OBJECTS_PROP = "polygroups_bake_pack_objects"
BAKE_PACK_TYPE_MERGED = "MERGED"
BAKE_TEMP_IMAGE_PREFIX = "Bake_Temp_"
AUTO_CAGE_INTERSECTION_EPSILON = 0.00001


def _safe_path_name(name):
    safe_name = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .")
    return safe_name or "Object"


def _active_mesh(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    return obj


def _source_meshes(context, target):
    return [
        obj
        for obj in context.selected_objects
        if obj != target and obj.type == "MESH"
    ]


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


def _principled_bsdf(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node

    return material.node_tree.nodes.get("Principled BSDF")


def _set_polygroup_material_texture_only(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return False

    tree = material.node_tree
    bsdf = _principled_bsdf(material)
    if bsdf is None:
        return False

    base_input = bsdf.inputs.get("Base Color")
    if base_input is None:
        return False

    group_node = None
    for node in tree.nodes:
        if node.bl_idname == "ShaderNodeGroup" and node.outputs.get("Base Color") is not None:
            if node.label == "Source Texture Group" or node.name.startswith("Source Texture Group"):
                group_node = node
                break

    if group_node is None:
        return False

    changed = False
    if base_input.is_linked:
        for link in list(base_input.links):
            if link.from_node.label == "PolyGroup Color Tint" or link.from_node.name.startswith("PolyGroup Color Tint"):
                tree.links.remove(link)
                changed = True

    base_output = group_node.outputs.get("Base Color")
    if base_output is None:
        return changed

    already_linked = any(
        link.from_socket == base_output and link.to_socket == base_input
        for link in tree.links
    )
    if not already_linked:
        tree.links.new(base_output, base_input)
        changed = True

    return changed


def _make_image(name, resolution, colorspace):
    image = bpy.data.images.new(name=name, width=resolution, height=resolution, alpha=True)
    image.generated_color = (0.0, 0.0, 0.0, 1.0)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    return image


def _bake_data_name(settings, target, suffix):
    object_name = _safe_path_name(target.name)
    prefix = _safe_path_name(settings.image_prefix)
    return f"{prefix}_{object_name}_{suffix}"


def _bake_pack_data_name(settings, pack_name, suffix):
    prefix = _safe_path_name(settings.image_prefix)
    return f"{prefix}_{_safe_path_name(pack_name)}_{suffix}"


def _image_matches_resolution(image, resolution):
    return image is not None and image.size[0] == resolution and image.size[1] == resolution


def _ensure_target_image(
    target,
    settings,
    prop_name,
    suffix,
    colorspace,
    generated_color=None,
    source_prop_name=None,
):
    image = None
    image_name = target.get(prop_name, "")
    if image_name:
        image = bpy.data.images.get(image_name)

    if not _image_matches_resolution(image, settings.bake_resolution):
        image = _make_image(
            _bake_data_name(settings, target, suffix),
            settings.bake_resolution,
            colorspace,
        )
        target[prop_name] = image.name

    if source_prop_name is not None:
        target[source_prop_name] = image.name

    if generated_color is not None:
        image.generated_color = generated_color

    return image


def _ensure_target_bake_material(target, settings):
    material = None
    material_name = target.get(BAKE_TARGET_MATERIAL_PROP, "")
    if material_name:
        material = bpy.data.materials.get(material_name)

    if material is None:
        material = bpy.data.materials.new(_bake_data_name(settings, target, "Material"))
        target[BAKE_TARGET_MATERIAL_PROP] = material.name

    return material


def _ensure_bake_material(target, settings, base_image=None, normal_image=None, update_source_images=True):
    if target.data.uv_layers.active is None:
        target.data.uv_layers.new(name="UVMap")

    material = _ensure_target_bake_material(target, settings)
    material.use_nodes = True

    if target.data.materials:
        target.data.materials[0] = material
    else:
        target.data.materials.append(material)
    target.active_material_index = 0
    for polygon in target.data.polygons:
        polygon.material_index = 0

    tree = material.node_tree
    nodes = tree.nodes
    bsdf = _principled_bsdf(material)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    if base_image is None:
        base_image = _ensure_target_image(
            target,
            settings,
            BAKE_BASE_COLOR_IMAGE_PROP,
            "BaseColor",
            "sRGB",
            source_prop_name=BAKE_SOURCE_BASE_COLOR_IMAGE_PROP,
        )
    else:
        target[BAKE_BASE_COLOR_IMAGE_PROP] = base_image.name
        if update_source_images:
            target[BAKE_SOURCE_BASE_COLOR_IMAGE_PROP] = base_image.name

    if normal_image is None:
        normal_image = _ensure_target_image(
            target,
            settings,
            BAKE_NORMAL_IMAGE_PROP,
            "Normal",
            "Non-Color",
            generated_color=(0.5, 0.5, 1.0, 1.0),
            source_prop_name=BAKE_SOURCE_NORMAL_IMAGE_PROP,
        )
    else:
        target[BAKE_NORMAL_IMAGE_PROP] = normal_image.name
        if update_source_images:
            target[BAKE_SOURCE_NORMAL_IMAGE_PROP] = normal_image.name

    base_node = nodes.get(BAKE_BASE_COLOR_NODE)
    if base_node is None:
        base_node = nodes.new("ShaderNodeTexImage")
        base_node.name = BAKE_BASE_COLOR_NODE
        base_node.label = "Bake Base Color"
        base_node.location = (-560, 100)
    base_node.image = base_image

    normal_node = nodes.get(BAKE_NORMAL_NODE)
    if normal_node is None:
        normal_node = nodes.new("ShaderNodeTexImage")
        normal_node.name = BAKE_NORMAL_NODE
        normal_node.label = "Bake Normal"
        normal_node.location = (-560, -120)
    normal_node.image = normal_image

    if bsdf is not None:
        base_input = bsdf.inputs.get("Base Color")
        if base_input is not None and not any(link.from_node == base_node for link in base_input.links):
            tree.links.new(base_node.outputs["Color"], base_input)

        normal_input = bsdf.inputs.get("Normal")
        if normal_input is not None:
            normal_map = nodes.get("PolyGroups Bake Normal Map")
            if normal_map is None:
                normal_map = nodes.new("ShaderNodeNormalMap")
                normal_map.name = "PolyGroups Bake Normal Map"
                normal_map.label = "Bake Normal Map"
                normal_map.location = (-260, -120)

            color_input = normal_map.inputs.get("Color")
            normal_output = normal_map.outputs.get("Normal")
            if color_input is not None and not any(link.from_node == normal_node for link in color_input.links):
                tree.links.new(normal_node.outputs["Color"], color_input)
            if normal_output is not None and not any(link.from_node == normal_map for link in normal_input.links):
                tree.links.new(normal_output, normal_input)

    return material, base_node, normal_node


def _find_bake_image(target, node_name):
    for material_slot in target.material_slots:
        material = material_slot.material
        if material is None or not material.use_nodes or material.node_tree is None:
            continue

        node = material.node_tree.nodes.get(node_name)
        if node is not None and getattr(node, "image", None) is not None:
            return node.image

    return None


def _find_material_bake_image(material, node_name):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    node = material.node_tree.nodes.get(node_name)
    if node is not None and getattr(node, "image", None) is not None:
        return node.image

    return None


def _find_object_bake_image(target, node_name, prop_name):
    image_name = target.get(prop_name, "")
    if image_name:
        image = bpy.data.images.get(image_name)
        if image is not None:
            return image

    return _find_bake_image(target, node_name)


def _target_bake_material(target):
    material_name = target.get(BAKE_TARGET_MATERIAL_PROP, "")
    if material_name:
        material = bpy.data.materials.get(material_name)
        if material is not None:
            return material

    return None


def _is_merged_image(image):
    return (
        image is not None
        and (
            image.get(BAKE_PACK_TYPE_PROP) == BAKE_PACK_TYPE_MERGED
            or "_Merged_" in image.name
            or "_Merged" in image.name
        )
    )


def _is_merged_material(material):
    return (
        material is not None
        and material.get(BAKE_PACK_TYPE_PROP) == BAKE_PACK_TYPE_MERGED
    )


def _find_current_bake_image(target, node_name, prop_name):
    image = _image_from_object_prop(target, prop_name)
    if image is not None and not _is_merged_image(image):
        return image

    material = _target_bake_material(target)
    image = _find_material_bake_image(material, node_name)
    if image is not None and not _is_merged_image(image):
        target[prop_name] = image.name
        return image

    for material_slot in target.material_slots:
        material = material_slot.material
        if _is_merged_material(material):
            continue

        image = _find_material_bake_image(material, node_name)
        if image is not None and not _is_merged_image(image):
            target[prop_name] = image.name
            return image

    return None


def _image_from_object_prop(target, prop_name):
    image_name = target.get(prop_name, "")
    return bpy.data.images.get(image_name) if image_name else None


def _find_object_source_bake_image(target, settings, node_name, current_prop_name, source_prop_name, suffix):
    image = _image_from_object_prop(target, current_prop_name)
    if image is not None and not _is_merged_image(image):
        target[source_prop_name] = image.name
        return image

    image = _image_from_object_prop(target, source_prop_name)
    if image is not None:
        return image

    image = bpy.data.images.get(_bake_data_name(settings, target, suffix))
    if image is not None:
        target[source_prop_name] = image.name
        return image

    image = _find_bake_image(target, node_name)
    if image is not None and not _is_merged_image(image):
        target[source_prop_name] = image.name
        return image

    return None


def _selected_bake_targets(context):
    return [
        obj
        for obj in context.selected_objects
        if obj.type == "MESH"
    ]


def _image_resolution(image):
    if image is None:
        return None

    for should_reload in (False, True):
        if should_reload:
            try:
                image.reload()
            except Exception:
                pass

        width = int(image.size[0])
        height = int(image.size[1])
        try:
            pixel_length = len(image.pixels)
        except Exception:
            pixel_length = 0

        if width > 0 and height > 0 and pixel_length == width * height * 4:
            return width, height

        if width <= 0 or height <= 0:
            pixel_count = pixel_length // 4
            if pixel_count == 1:
                return 1, 1

    return None


def _image_is_readable(image, resolution):
    image_resolution = _image_resolution(image)
    return image_resolution is not None and image_resolution == resolution


def _read_image_pixels(image, resolution):
    pixel_count = resolution[0] * resolution[1] * 4
    if not _image_is_readable(image, resolution):
        raise ValueError(f"Image {image.name if image else '<None>'} has no readable pixel buffer")

    pixels = array("f", [0.0]) * pixel_count
    image.pixels.foreach_get(pixels)
    return pixels


def _ensure_output_image(name, resolution, colorspace, generated_color):
    resolution = max(1, int(resolution[0])), max(1, int(resolution[1]))
    image = bpy.data.images.get(name)
    if image is None or image.size[0] != resolution[0] or image.size[1] != resolution[1]:
        if image is not None:
            bpy.data.images.remove(image)
        image = bpy.data.images.new(name=name, width=resolution[0], height=resolution[1], alpha=True)

    image.generated_color = generated_color
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    return image


def _collect_bake_texture_packs(objects, settings):
    packs = []
    for obj in objects:
        base_image = _find_object_source_bake_image(
            obj,
            settings,
            BAKE_BASE_COLOR_NODE,
            BAKE_BASE_COLOR_IMAGE_PROP,
            BAKE_SOURCE_BASE_COLOR_IMAGE_PROP,
            "BaseColor",
        )
        normal_image = _find_object_source_bake_image(
            obj,
            settings,
            BAKE_NORMAL_NODE,
            BAKE_NORMAL_IMAGE_PROP,
            BAKE_SOURCE_NORMAL_IMAGE_PROP,
            "Normal",
        )
        if base_image is None and normal_image is None:
            continue

        packs.append(
            {
                "object": obj,
                "base": base_image,
                "normal": normal_image,
            },
        )
    return packs


def _pack_resolution(pack):
    base_resolution = _image_resolution(pack["base"])
    normal_resolution = _image_resolution(pack["normal"])
    if base_resolution is not None and normal_resolution is not None and base_resolution != normal_resolution:
        return None

    return base_resolution or normal_resolution


def _validate_pack_resolutions(packs):
    resolution = _pack_resolution(packs[0])
    if resolution is None:
        return None

    for pack in packs[1:]:
        pack_resolution = _pack_resolution(pack)
        if pack_resolution is None or pack_resolution != resolution:
            return None
    return resolution


def _merge_base_color_pixels(packs, resolution):
    pixel_count = resolution[0] * resolution[1] * 4
    output = array("f", [0.0]) * pixel_count
    for pack in packs:
        image = pack["base"]
        if image is None or not _image_is_readable(image, resolution):
            continue

        pixels = _read_image_pixels(image, resolution)
        for index in range(0, pixel_count, 4):
            source_alpha = max(0.0, min(1.0, pixels[index + 3]))
            if source_alpha <= 0.0:
                continue

            destination_alpha = max(0.0, min(1.0, output[index + 3]))
            out_alpha = source_alpha + destination_alpha * (1.0 - source_alpha)
            if out_alpha <= 0.0:
                continue

            for channel in range(3):
                source_value = pixels[index + channel]
                destination_value = output[index + channel]
                output[index + channel] = (
                    source_value * source_alpha
                    + destination_value * destination_alpha * (1.0 - source_alpha)
                ) / out_alpha
            output[index + 3] = out_alpha

    return output


def _normal_to_vector(pixels, index):
    return [
        pixels[index] * 2.0 - 1.0,
        pixels[index + 1] * 2.0 - 1.0,
        pixels[index + 2] * 2.0 - 1.0,
    ]


def _normalized_to_color(vector):
    length = sum(item * item for item in vector) ** 0.5
    if length <= 0.000001:
        return 0.5, 0.5, 1.0

    return tuple((item / length) * 0.5 + 0.5 for item in vector)


def _merge_normal_pixels(packs, resolution):
    pixel_count = resolution[0] * resolution[1] * 4
    output = array("f", [0.0]) * pixel_count
    for index in range(0, pixel_count, 4):
        output[index] = 0.5
        output[index + 1] = 0.5
        output[index + 2] = 1.0
        output[index + 3] = 1.0

    for pack in packs:
        normal_image = pack["normal"]
        if normal_image is None or not _image_is_readable(normal_image, resolution):
            continue

        normal_pixels = _read_image_pixels(normal_image, resolution)
        base_pixels = (
            _read_image_pixels(pack["base"], resolution)
            if pack["base"] is not None and _image_is_readable(pack["base"], resolution)
            else None
        )
        for index in range(0, pixel_count, 4):
            mask = base_pixels[index + 3] if base_pixels is not None else normal_pixels[index + 3]
            mask = max(0.0, min(1.0, mask))
            if mask <= 0.001:
                continue

            if mask >= 0.999:
                output[index] = normal_pixels[index]
                output[index + 1] = normal_pixels[index + 1]
                output[index + 2] = normal_pixels[index + 2]
            else:
                destination = _normal_to_vector(output, index)
                source = _normal_to_vector(normal_pixels, index)
                blended = [
                    source[channel] * mask + destination[channel] * (1.0 - mask)
                    for channel in range(3)
                ]
                output[index], output[index + 1], output[index + 2] = _normalized_to_color(blended)
            output[index + 3] = 1.0

    return output


def _count_unreadable_pack_images(packs, resolution):
    count = 0
    for pack in packs:
        for key in ("base", "normal"):
            image = pack[key]
            if image is not None and not _image_is_readable(image, resolution):
                count += 1
    return count


def _merged_pack_name(objects):
    names = []
    for obj in sorted(objects, key=lambda item: item.name.lower()):
        safe_name = _safe_path_name(obj.name)
        if safe_name not in names:
            names.append(safe_name)

    if len(names) <= 3:
        base_name = " + ".join(names)
    else:
        base_name = f"{names[0]} + {names[1]} + {len(names) - 2} more"

    return f"{base_name} Merged"


def _ensure_merged_material(pack_name, base_image, normal_image, objects):
    material_name = f"Merged Material - {_safe_path_name(pack_name)}"
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(material_name)

    material.use_nodes = True
    material[BAKE_PACK_TYPE_PROP] = BAKE_PACK_TYPE_MERGED
    material[BAKE_PACK_NAME_PROP] = pack_name
    material[BAKE_PACK_OBJECTS_PROP] = ";".join(obj.name for obj in objects)

    tree = material.node_tree
    nodes = tree.nodes
    bsdf = _principled_bsdf(material)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    base_node = nodes.get(BAKE_BASE_COLOR_NODE)
    if base_node is None:
        base_node = nodes.new("ShaderNodeTexImage")
        base_node.name = BAKE_BASE_COLOR_NODE
        base_node.label = "Merged Base Color"
        base_node.location = (-560, 100)
    base_node.image = base_image

    normal_node = nodes.get(BAKE_NORMAL_NODE)
    if normal_node is None:
        normal_node = nodes.new("ShaderNodeTexImage")
        normal_node.name = BAKE_NORMAL_NODE
        normal_node.label = "Merged Normal"
        normal_node.location = (-560, -120)
    normal_node.image = normal_image

    if bsdf is not None:
        base_input = bsdf.inputs.get("Base Color")
        if base_input is not None and not any(link.from_node == base_node for link in base_input.links):
            tree.links.new(base_node.outputs["Color"], base_input)

        normal_input = bsdf.inputs.get("Normal")
        if normal_input is not None:
            normal_map = nodes.get("PolyGroups Bake Normal Map")
            if normal_map is None:
                normal_map = nodes.new("ShaderNodeNormalMap")
                normal_map.name = "PolyGroups Bake Normal Map"
                normal_map.label = "Merged Normal Map"
                normal_map.location = (-260, -120)

            color_input = normal_map.inputs.get("Color")
            normal_output = normal_map.outputs.get("Normal")
            if color_input is not None and not any(link.from_node == normal_node for link in color_input.links):
                tree.links.new(normal_node.outputs["Color"], color_input)
            if normal_output is not None and not any(link.from_node == normal_map for link in normal_input.links):
                tree.links.new(normal_output, normal_input)

    return material


def _assign_material_to_object(obj, material):
    material_index = None
    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material:
            material_index = index
            break

    if material_index is None:
        obj.data.materials.append(material)
        material_index = len(obj.data.materials) - 1

    obj.active_material_index = material_index
    for polygon in obj.data.polygons:
        polygon.material_index = material_index

    obj[BAKE_MERGED_MATERIAL_PROP] = material.name


def _tag_merged_image(image, pack_name):
    image[BAKE_PACK_TYPE_PROP] = BAKE_PACK_TYPE_MERGED
    image[BAKE_PACK_NAME_PROP] = pack_name


def _bake_temp_images():
    return [
        image
        for image in bpy.data.images
        if image.name.startswith(BAKE_TEMP_IMAGE_PREFIX)
    ]


def _write_pixels(image, pixels):
    if len(pixels) != len(image.pixels):
        raise ValueError(
            f"Image pixel buffer mismatch: image expects {len(image.pixels)}, got {len(pixels)}",
        )
    image.pixels.foreach_set(pixels)
    image.update()


def _save_image_as_png(image, filepath):
    image.filepath_raw = filepath
    image.file_format = "PNG"
    image.save()

    try:
        image.filepath = bpy.path.relpath(filepath)
        image.filepath_raw = bpy.path.relpath(filepath)
    except Exception:
        image.filepath = filepath
        image.filepath_raw = filepath
    image.file_format = "PNG"

    try:
        image.reload()
    except Exception:
        pass


def _set_active_bake_node(target, node):
    material = target.active_material
    if material is None or material.node_tree is None:
        return

    for item in material.node_tree.nodes:
        item.select = False

    node.select = True
    material.node_tree.nodes.active = node


def _select_sources_and_target(context, sources, target):
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in sources:
        obj.select_set(True)
    target.select_set(True)
    context.view_layer.objects.active = target


def _configure_bake_settings(context, settings, bake_type):
    scene = context.scene
    scene.render.engine = "CYCLES"
    if hasattr(scene, "cycles"):
        scene.cycles.bake_type = bake_type

    bake = scene.render.bake
    bake.use_selected_to_active = settings.use_selected_to_active
    bake.cage_extrusion = settings.cage_extrusion
    bake.max_ray_distance = settings.ray_distance
    bake.margin = settings.bake_margin
    bake.use_clear = True

    if bake_type == "DIFFUSE":
        bake.use_pass_direct = False
        bake.use_pass_indirect = False
        bake.use_pass_color = True
    elif bake_type == "NORMAL":
        bake.normal_space = "TANGENT"


def _bake_to_node(context, target, node, bake_type, settings):
    _set_active_bake_node(target, node)
    _configure_bake_settings(context, settings, bake_type)
    result = bpy.ops.object.bake(type=bake_type)
    return result


class OBJECT_OT_polygroups_prepare_highpoly_bake_materials(bpy.types.Operator):
    bl_idname = "object.polygroups_prepare_highpoly_bake_materials"
    bl_label = "Prepare Highpoly Texture Only"
    bl_description = "Switch selected PolyGroup source materials from Texture + Color to Source Texture"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = _active_mesh(context)
        return target is not None and bool(_source_meshes(context, target))

    def execute(self, context):
        target = _active_mesh(context)
        sources = _source_meshes(context, target)
        changed_count = 0

        for obj in sources:
            for material in obj.data.materials:
                if _set_polygroup_material_texture_only(material):
                    changed_count += 1

        self.report({"INFO"}, f"Prepared {changed_count} highpoly material(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_prepare_lowpoly_bake_material(bpy.types.Operator):
    bl_idname = "object.polygroups_prepare_lowpoly_bake_material"
    bl_label = "Prepare Lowpoly Bake Material"
    bl_description = "Create bake material and temporary bake images on the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        target = _active_mesh(context)
        settings = context.scene.polygroups_baking_settings
        if target.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        _ensure_bake_material(target, settings)
        self.report({"INFO"}, "Prepared lowpoly bake material and images")
        return {"FINISHED"}


class OBJECT_OT_polygroups_calculate_auto_cage(bpy.types.Operator):
    bl_idname = "object.polygroups_calculate_auto_cage"
    bl_label = "Calculate AutoCage"
    bl_description = "Calculate cage extrusion from selected highpoly meshes and the active lowpoly mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = _active_mesh(context)
        return target is not None and bool(_source_meshes(context, target))

    def execute(self, context):
        target = _active_mesh(context)
        sources = _source_meshes(context, target)
        settings = context.scene.polygroups_baking_settings

        if target.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        try:
            result = calculate_auto_cage(context, target, sources, settings)
        except ValueError as error:
            settings.auto_cage_status = f"AutoCage failed: {error}"
            self.report({"WARNING"}, settings.auto_cage_status)
            return {"CANCELLED"}

        settings.cage_extrusion = result["cage"]
        settings.auto_cage_status = (
            f"Cage {result['cage']:.5f} m | Coverage {result['coverage']:.1f}% | "
            f"Safe {result['safe_zone']:.1f}% | Outliers {result['outliers']} | "
            f"Intersections {result['intersections']}"
        )
        self.report({"INFO"}, settings.auto_cage_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_save_blend_file(bpy.types.Operator):
    bl_idname = "object.polygroups_save_blend_file"
    bl_label = "Save Blend File"
    bl_description = "Save the current blend file so baked textures can be written next to it"
    bl_options = {"REGISTER"}

    def execute(self, context):
        del context
        if bpy.data.filepath:
            result = bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
            if "FINISHED" in result:
                self.report({"INFO"}, "Saved blend file")
            return result

        return bpy.ops.wm.save_as_mainfile("INVOKE_DEFAULT")


class OBJECT_OT_polygroups_save_blend_file_as(bpy.types.Operator):
    bl_idname = "object.polygroups_save_blend_file_as"
    bl_label = "Save Blend File As"
    bl_description = "Choose where to save the current blend file before saving baked textures"
    bl_options = {"REGISTER"}

    def execute(self, context):
        del context
        return bpy.ops.wm.save_as_mainfile("INVOKE_DEFAULT")


class OBJECT_OT_polygroups_save_bake_textures(bpy.types.Operator):
    bl_idname = "object.polygroups_save_bake_textures"
    bl_label = "Save Textures"
    bl_description = "Save baked Base Color and Normal images next to the blend file"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        target = _active_mesh(context)
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the blend file first")
            return {"CANCELLED"}

        active_material = target.active_material
        is_merged = _is_merged_material(active_material)
        if is_merged:
            pack_name = active_material.get(BAKE_PACK_NAME_PROP, f"{target.name} Merged")
            output_name = _safe_path_name(pack_name)
            base_image = _find_material_bake_image(active_material, BAKE_BASE_COLOR_NODE)
            normal_image = _find_material_bake_image(active_material, BAKE_NORMAL_NODE)
        else:
            output_name = _safe_path_name(target.name)
            base_image = _find_current_bake_image(
                target,
                BAKE_BASE_COLOR_NODE,
                BAKE_BASE_COLOR_IMAGE_PROP,
            )
            normal_image = _find_current_bake_image(
                target,
                BAKE_NORMAL_NODE,
                BAKE_NORMAL_IMAGE_PROP,
            )

        if base_image is None and normal_image is None:
            self.report({"WARNING"}, "No bake images found on the active mesh")
            return {"CANCELLED"}

        blend_dir = os.path.dirname(bpy.data.filepath)
        output_dir = os.path.join(blend_dir, "Bakes", output_name)
        os.makedirs(output_dir, exist_ok=True)

        saved_paths = []
        if base_image is not None:
            filepath = os.path.join(output_dir, f"{output_name}_Bake_BaseColor.png")
            _save_image_as_png(base_image, filepath)
            saved_paths.append(filepath)

        if normal_image is not None:
            filepath = os.path.join(output_dir, f"{output_name}_Bake_Normal.png")
            _save_image_as_png(normal_image, filepath)
            saved_paths.append(filepath)

        self.report({"INFO"}, f"Saved {len(saved_paths)} texture(s) to {output_dir}")
        return {"FINISHED"}


class OBJECT_OT_polygroups_merge_bake_textures(bpy.types.Operator):
    bl_idname = "object.polygroups_merge_bake_textures"
    bl_label = "Merge Materials/Textures"
    bl_description = "Merge baked texture packs from selected objects into one pack on the active object"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = _active_mesh(context)
        return target is not None and len(_selected_bake_targets(context)) >= 2

    def execute(self, context):
        target = _active_mesh(context)
        settings = context.scene.polygroups_baking_settings
        objects = _selected_bake_targets(context)
        packs = _collect_bake_texture_packs(objects, settings)
        if len(packs) < 2:
            self.report({"WARNING"}, "Select at least two objects with baked texture packs")
            return {"CANCELLED"}

        resolution = _validate_pack_resolutions(packs)
        if resolution is None:
            self.report({"ERROR"}, "Selected bake textures must be loaded and have the same resolution")
            return {"CANCELLED"}

        base_pixels = _merge_base_color_pixels(packs, resolution)
        normal_pixels = _merge_normal_pixels(packs, resolution)

        pack_objects = [pack["object"] for pack in packs]
        pack_name = _merged_pack_name(pack_objects)

        base_image = _ensure_output_image(
            _bake_pack_data_name(settings, pack_name, "Merged_BaseColor"),
            resolution,
            "sRGB",
            (0.0, 0.0, 0.0, 0.0),
        )
        normal_image = _ensure_output_image(
            _bake_pack_data_name(settings, pack_name, "Merged_Normal"),
            resolution,
            "Non-Color",
            (0.5, 0.5, 1.0, 1.0),
        )
        _write_pixels(base_image, base_pixels)
        _write_pixels(normal_image, normal_pixels)
        _tag_merged_image(base_image, pack_name)
        _tag_merged_image(normal_image, pack_name)

        material = _ensure_merged_material(pack_name, base_image, normal_image, pack_objects)
        for obj in pack_objects:
            obj[BAKE_MERGED_BASE_COLOR_IMAGE_PROP] = base_image.name
            obj[BAKE_MERGED_NORMAL_IMAGE_PROP] = normal_image.name
            _assign_material_to_object(obj, material)
        target.active_material = material

        skipped = len(objects) - len(packs)
        message = f"Merged {len(packs)} texture pack(s) into {pack_name}"
        if skipped:
            message += f", skipped {skipped} object(s)"
        unreadable_images = _count_unreadable_pack_images(packs, resolution)
        if unreadable_images:
            message += f", ignored {unreadable_images} unreadable image(s)"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_bake_temp_images(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_bake_temp_images"
    bl_label = "Clear All Bake Images"
    bl_description = "Delete all Bake_Temp images from the current blend file"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_bake_temp_images())

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=440,
            confirm_text="Clear All Bake Images",
        )

    def draw(self, context):
        images = _bake_temp_images()
        layout = self.layout
        layout.label(text="This will delete temporary bake images from the blend file.", icon="ERROR")
        layout.label(text=f"Images found: {len(images)}")
        layout.label(text="Only images starting with Bake_Temp_ will be removed.")

    def execute(self, context):
        images = _bake_temp_images()
        if not images:
            self.report({"INFO"}, "No Bake_Temp images found")
            return {"CANCELLED"}

        removed_count = 0
        for image in images:
            bpy.data.images.remove(image)
            removed_count += 1

        self.report({"INFO"}, f"Removed {removed_count} Bake_Temp image(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_bake_selected_to_active(bpy.types.Operator):
    bl_idname = "object.polygroups_bake_selected_to_active"
    bl_label = "Bake Selected To Active"
    bl_description = "Bake Base Color and Normal from selected highpoly meshes to the active lowpoly mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = _active_mesh(context)
        return target is not None and bool(_source_meshes(context, target))

    def execute(self, context):
        target = _active_mesh(context)
        sources = _source_meshes(context, target)
        settings = context.scene.polygroups_baking_settings

        if not settings.bake_base_color and not settings.bake_normal:
            self.report({"WARNING"}, "Enable at least one bake pass")
            return {"CANCELLED"}

        if target.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if not _apply_auto_cage_if_enabled(context, target, sources, settings, self.report):
            return {"CANCELLED"}
        material, base_node, normal_node = _ensure_bake_material(target, settings)
        target.active_material = material
        _select_sources_and_target(context, sources, target)

        if settings.bake_base_color:
            _bake_to_node(context, target, base_node, "DIFFUSE", settings)

        if settings.bake_normal:
            _bake_to_node(context, target, normal_node, "NORMAL", settings)

        self.report({"INFO"}, "Bake finished")
        return {"FINISHED"}


class OBJECT_OT_polygroups_prepare_and_bake(bpy.types.Operator):
    bl_idname = "object.polygroups_prepare_and_bake"
    bl_label = "Prepare And Bake"
    bl_description = "Prepare highpoly materials, prepare lowpoly target, then bake selected-to-active"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = _active_mesh(context)
        return target is not None and bool(_source_meshes(context, target))

    def execute(self, context):
        target = _active_mesh(context)
        sources = _source_meshes(context, target)
        settings = context.scene.polygroups_baking_settings

        if target.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        changed_count = 0
        for obj in sources:
            for material in obj.data.materials:
                if _set_polygroup_material_texture_only(material):
                    changed_count += 1

        if not _apply_auto_cage_if_enabled(context, target, sources, settings, self.report):
            return {"CANCELLED"}

        material, base_node, normal_node = _ensure_bake_material(target, settings)
        target.active_material = material
        _select_sources_and_target(context, sources, target)

        if settings.bake_base_color:
            _bake_to_node(context, target, base_node, "DIFFUSE", settings)

        if settings.bake_normal:
            _bake_to_node(context, target, normal_node, "NORMAL", settings)

        if settings.auto_save_textures_after_bake:
            try:
                save_result = bpy.ops.object.polygroups_save_bake_textures()
            except Exception as error:
                self.report({"WARNING"}, f"Auto save textures failed: {error}")
            else:
                if "FINISHED" not in save_result:
                    self.report({"WARNING"}, "Auto save textures was not completed")

        self.report(
            {"INFO"},
            f"Prepared {changed_count} material(s) and finished bake",
        )
        return {"FINISHED"}
