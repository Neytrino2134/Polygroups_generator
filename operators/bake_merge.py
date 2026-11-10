"""Bake merge helpers."""
from array import array
import bpy
from .bake_constants import (
    BAKE_ALPHA_IMAGE_PROP,
    BAKE_ALPHA_NODE,
    BAKE_BASE_COLOR_IMAGE_PROP,
    BAKE_BASE_COLOR_NODE,
    BAKE_MERGED_MATERIAL_PROP,
    BAKE_NORMAL_IMAGE_PROP,
    BAKE_NORMAL_NODE,
    BAKE_PACK_NAME_PROP,
    BAKE_PACK_OBJECTS_PROP,
    BAKE_PACK_TYPE_MERGED,
    BAKE_PACK_TYPE_PROP,
    BAKE_SOURCE_ALPHA_IMAGE_PROP,
    BAKE_SOURCE_BASE_COLOR_IMAGE_PROP,
    BAKE_SOURCE_NORMAL_IMAGE_PROP,
    BAKE_TEMP_IMAGE_PREFIX,
)
from .bake_images import (
    _apply_bake_roughness,
    _find_material_bake_image,
    _find_object_source_bake_image,
    _image_is_readable,
    _image_resolution,
    _principled_bsdf,
    _read_image_pixels,
    _target_bake_material,
)


def _collect_bake_texture_packs(objects, settings):
    material_users = {}
    legacy_users = {}
    for obj in objects:
        slots = obj.material_slots
        if not slots or not obj.data.polygons:
            continue
        used_indices = (0,) if len(slots) == 1 else sorted({polygon.material_index for polygon in obj.data.polygons})
        used_materials = {slots[index].material for index in used_indices if index < len(slots)}
        used_materials.discard(None)
        legacy_material = _target_bake_material(obj)
        if legacy_material is None and len(used_materials) == 1:
            legacy_material = next(iter(used_materials))
        if legacy_material in used_materials:
            legacy_users.setdefault(legacy_material, []).append(obj)
        for index in used_indices:
            if index < len(slots) and (material := slots[index].material) is not None:
                material_users.setdefault(material, []).append((obj, index))

    channels = (
        ("base", BAKE_BASE_COLOR_NODE, BAKE_BASE_COLOR_IMAGE_PROP, BAKE_SOURCE_BASE_COLOR_IMAGE_PROP, "BaseColor"),
        ("normal", BAKE_NORMAL_NODE, BAKE_NORMAL_IMAGE_PROP, BAKE_SOURCE_NORMAL_IMAGE_PROP, "Normal"),
        ("alpha", BAKE_ALPHA_NODE, BAKE_ALPHA_IMAGE_PROP, BAKE_SOURCE_ALPHA_IMAGE_PROP, "MergeMask"),
    )
    packs = []
    for material, users in material_users.items():
        images = {key: _find_material_bake_image(material, node) for key, node, *_ in channels}
        # Older bakes may only identify their textures through object properties.
        if not (images["alpha"] and (images["base"] or images["normal"])):
            for obj in legacy_users.get(material, ()):
                candidate = {
                    key: images[key] or _find_object_source_bake_image(obj, settings, node, current, source, suffix)
                    for key, node, current, source, suffix in channels
                }
                if candidate["alpha"] and (candidate["base"] or candidate["normal"]):
                    images = candidate
                    break
        if images["alpha"] and (images["base"] or images["normal"]):
            packs.append({"material": material, "users": users, **images})
    return packs


def _pack_resolution(pack):
    alpha_resolution = _image_resolution(pack["alpha"])
    if alpha_resolution is None:
        return None
    resolutions = [
        resolution
        for resolution in (
            _image_resolution(pack["base"]),
            _image_resolution(pack["normal"]),
        )
        if resolution is not None
    ]
    if not resolutions or any(resolution != alpha_resolution for resolution in resolutions):
        return None
    return alpha_resolution


def _validate_pack_resolutions(packs):
    resolution = _pack_resolution(packs[0])
    if resolution is None:
        return None

    for pack in packs[1:]:
        pack_resolution = _pack_resolution(pack)
        if pack_resolution is None or pack_resolution != resolution:
            return None
    return resolution


def _pack_coverage(pack, resolution):
    alpha_image = pack.get("alpha")
    if alpha_image is not None and _image_is_readable(alpha_image, resolution):
        pixels = _read_image_pixels(alpha_image, resolution)
        coverage = array("f", [0.0]) * (resolution[0] * resolution[1])
        for pixel_index in range(len(coverage)):
            coverage[pixel_index] = max(0.0, min(1.0, pixels[pixel_index * 4]))
        return coverage
    return array("f", [0.0]) * (resolution[0] * resolution[1])


def _merge_pack_coverage(packs, resolution):
    output = array("f", [0.0]) * (resolution[0] * resolution[1])
    for pack in packs:
        source = _pack_coverage(pack, resolution)
        for index, source_alpha in enumerate(source):
            output[index] = source_alpha + output[index] * (1.0 - source_alpha)
    return output


def _merge_base_color_pixels(packs, resolution):
    pixel_count = resolution[0] * resolution[1] * 4
    output = array("f", [0.0]) * pixel_count
    for pack in packs:
        image = pack["base"]
        if image is None or not _image_is_readable(image, resolution):
            continue

        pixels = _read_image_pixels(image, resolution)
        coverage = _pack_coverage(pack, resolution)
        for index in range(0, pixel_count, 4):
            source_alpha = coverage[index // 4]
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
        output[index + 3] = 0.0

    for pack in packs:
        normal_image = pack["normal"]
        if normal_image is None or not _image_is_readable(normal_image, resolution):
            continue

        normal_pixels = _read_image_pixels(normal_image, resolution)
        coverage = _pack_coverage(pack, resolution)
        for index in range(0, pixel_count, 4):
            mask = coverage[index // 4]
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
            output[index + 3] = mask + output[index + 3] * (1.0 - mask)

    return output


def _count_unreadable_pack_images(packs, resolution):
    count = 0
    for pack in packs:
        for key in ("base", "normal", "alpha"):
            image = pack[key]
            if image is not None and not _image_is_readable(image, resolution):
                count += 1
    return count


def _short_merge_name(name):
    return f"{name[:6]}___{name[-6:]}" if len(name) > 12 else name


def _merged_pack_name(materials, active_material):
    first = active_material if active_material in materials else materials[0]
    if len(materials) == 2:
        second = next(material for material in materials if material != first)
        suffix = _short_merge_name(second.name).encode("utf-8")
    else:
        suffix = f"{len(materials)}_Materials".encode("utf-8")
    # Keep both sides of the name within Blender's datablock name limit.
    prefix = _short_merge_name(first.name).encode("utf-8")
    if len(prefix) + len(suffix) > 62:
        prefix_limit = max(31, 62 - len(suffix))
        prefix = prefix[:prefix_limit]
        suffix = suffix[:62 - len(prefix)]
    return f"{prefix.decode('utf-8', 'ignore')}+{suffix.decode('utf-8', 'ignore')}"


def _ensure_merged_material(pack_name, base_image, normal_image, alpha_image, objects, *, material_name=None):
    material = bpy.data.materials.new(material_name or pack_name)
    material.use_nodes = True
    material[BAKE_PACK_TYPE_PROP] = BAKE_PACK_TYPE_MERGED
    material[BAKE_PACK_NAME_PROP] = pack_name
    material[BAKE_PACK_OBJECTS_PROP] = ";".join(obj.name for obj in objects)

    tree = material.node_tree
    nodes = tree.nodes
    bsdf = _principled_bsdf(material)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    _apply_bake_roughness(bsdf)

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

    alpha_node = nodes.get(BAKE_ALPHA_NODE)
    if alpha_node is None:
        alpha_node = nodes.new("ShaderNodeTexImage")
        alpha_node.name = BAKE_ALPHA_NODE
        alpha_node.label = "Merged MergeMask"
        alpha_node.location = (-560, -340)
    alpha_node.image = alpha_image

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


def _assign_material_to_object(obj, material, indices):
    if (obj.data.users > 1 or not obj.data.is_editable) and any(
        obj.material_slots[index].link == "DATA" for index in indices
    ):
        obj.data = obj.data.copy()
    for index in indices:
        obj.material_slots[index].material = material
    if obj.active_material_index not in indices:
        obj.active_material_index = indices[0]
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
