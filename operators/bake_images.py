"""Bake images helpers."""
import re
from array import array
import bpy
from ..core.datablock_names import take_name
from ..core.generated_index import bake_output_name, fix_object_generated_index
from .bake_constants import (
    BAKE_ALPHA_IMAGE_PROP,
    BAKE_ALPHA_NODE,
    BAKE_BASE_COLOR_IMAGE_PROP,
    BAKE_BASE_COLOR_NODE,
    BAKE_MATERIAL_ROUGHNESS,
    BAKE_NORMAL_IMAGE_PROP,
    BAKE_NORMAL_NODE,
    BAKE_PACK_TYPE_MERGED,
    BAKE_PACK_TYPE_PROP,
    BAKE_SOURCE_ALPHA_IMAGE_PROP,
    BAKE_SOURCE_BASE_COLOR_IMAGE_PROP,
    BAKE_SOURCE_NORMAL_IMAGE_PROP,
    BAKE_TARGET_MATERIAL_PROP,
)


def _safe_path_name(name):
    safe_name = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .")
    return safe_name or "Object"


def _principled_bsdf(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node

    return material.node_tree.nodes.get("Principled BSDF")


def _apply_bake_roughness(bsdf):
    """Prepared bake materials use a fixed Roughness; a textured (linked) Roughness is left alone."""
    roughness = bsdf.inputs.get("Roughness") if bsdf is not None else None
    if roughness is not None and not roughness.is_linked:
        roughness.default_value = BAKE_MATERIAL_ROUGHNESS


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
    object_name = _safe_path_name(bake_output_name(target))
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
    resolution=None,
):
    resolution = settings.bake_resolution if resolution is None else resolution
    image = None
    image_name = target.get(prop_name, "")
    if image_name:
        image = bpy.data.images.get(image_name)

    desired_name = _bake_data_name(settings, target, suffix)
    # A re-created bake image replaces the previous one of this target/channel
    # instead of becoming <name>.001.
    if not _image_matches_resolution(image, resolution):
        image = _make_image(
            desired_name,
            resolution,
            colorspace,
        )
        take_name(bpy.data.images, image, desired_name, replace=True)
        target[prop_name] = image.name
    elif image.name != desired_name:
        take_name(bpy.data.images, image, desired_name, replace=True)
        target[prop_name] = image.name

    if source_prop_name is not None:
        target[source_prop_name] = image.name

    if suffix in {"MergeMask", "ArtifactMask"}:
        image["polygroups_bake_mask"] = suffix
    if generated_color is not None:
        image.generated_color = generated_color

    return image


def _ensure_target_bake_material(target, settings):
    material = None
    material_name = target.get(BAKE_TARGET_MATERIAL_PROP, "")
    if material_name:
        material = bpy.data.materials.get(material_name)

    desired_name = _bake_data_name(settings, target, "Material")
    if material is None:
        # Reuse this target's previous bake material rather than creating <name>.001.
        existing = bpy.data.materials.get(desired_name)
        material = existing if existing is not None and existing.library is None \
            else bpy.data.materials.new(desired_name)
        target[BAKE_TARGET_MATERIAL_PROP] = material.name
    elif material.name != desired_name:
        take_name(bpy.data.materials, material, desired_name, replace=True)
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
    _apply_bake_roughness(bsdf)

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

    alpha_image = _ensure_target_image(
        target,
        settings,
        BAKE_ALPHA_IMAGE_PROP,
        "MergeMask",
        "Non-Color",
        generated_color=(0.0, 0.0, 0.0, 1.0),
        source_prop_name=BAKE_SOURCE_ALPHA_IMAGE_PROP if update_source_images else None,
    )

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

    alpha_node = nodes.get(BAKE_ALPHA_NODE)
    if alpha_node is None:
        alpha_node = nodes.new("ShaderNodeTexImage")
        alpha_node.name = BAKE_ALPHA_NODE
        alpha_node.label = "Bake MergeMask"
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
    if image is None and suffix == "MergeMask":
        image = bpy.data.images.get(_bake_data_name(settings, target, "AlphaMap"))
    if image is None and suffix == "MergeMask":
        image = bpy.data.images.get(_bake_data_name(settings, target, "Alpha"))
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


def _coverage_from_pixels(pixels, resolution):
    pixel_count = resolution[0] * resolution[1]
    coverage = array("f", [0.0]) * pixel_count
    for pixel_index in range(pixel_count):
        coverage[pixel_index] = max(0.0, min(1.0, pixels[pixel_index * 4 + 3]))
    return coverage


def _coverage_from_image(image, resolution):
    return _coverage_from_pixels(_read_image_pixels(image, resolution), resolution)


def _alpha_map_pixels(coverage):
    output = array("f", [0.0]) * (len(coverage) * 4)
    for pixel_index, value in enumerate(coverage):
        index = pixel_index * 4
        output[index] = value
        output[index + 1] = value
        output[index + 2] = value
        output[index + 3] = 1.0
    return output


def _extend_background_rgb(pixels, coverage, resolution):
    """Fill uncovered pixels from nearby covered pixels without external dependencies."""
    width, height = resolution
    output = array("f", pixels)
    populated_rows = bytearray(height)
    left_sources = array("i", [-1]) * width

    for y in range(height):
        row_pixel = y * width
        left_source = -1
        for x in range(width):
            if coverage[row_pixel + x] > 0.0001:
                left_source = x
                populated_rows[y] = 1
            left_sources[x] = left_source

        if not populated_rows[y]:
            continue

        right_source = -1
        for x in range(width - 1, -1, -1):
            pixel_index = row_pixel + x
            if coverage[pixel_index] > 0.0001:
                right_source = x
                continue
            left_source = left_sources[x]
            source_x = left_source
            if right_source >= 0 and (left_source < 0 or right_source - x < x - left_source):
                source_x = right_source
            if source_x < 0:
                continue
            destination = pixel_index * 4
            source = (row_pixel + source_x) * 4
            output[destination] = output[source]
            output[destination + 1] = output[source + 1]
            output[destination + 2] = output[source + 2]

    populated = [y for y, value in enumerate(populated_rows) if value]
    if not populated:
        return output

    populated_index = 0
    for y in range(height):
        if populated_rows[y]:
            while populated_index + 1 < len(populated) and populated[populated_index + 1] <= y:
                populated_index += 1
            continue
        lower = populated[populated_index] if populated[populated_index] < y else None
        upper_index = populated_index if populated[populated_index] > y else populated_index + 1
        upper = populated[upper_index] if upper_index < len(populated) else None
        if lower is None:
            source_y = upper
        elif upper is None:
            source_y = lower
        else:
            source_y = lower if y - lower <= upper - y else upper
        source_start = source_y * width * 4
        destination_start = y * width * 4
        output[destination_start:destination_start + width * 4] = output[
            source_start:source_start + width * 4
        ]

    return output


def _apply_bake_background(pixels, coverage, resolution, mode):
    if mode == "EXTEND":
        output = _extend_background_rgb(pixels, coverage, resolution)
    else:
        output = array("f", pixels)
        for pixel_index, mask in enumerate(coverage):
            index = pixel_index * 4
            output[index] *= mask
            output[index + 1] *= mask
            output[index + 2] *= mask

    for index in range(3, len(output), 4):
        output[index] = 1.0
    return output


def _fill_normal_background(pixels, coverage):
    """Use a flat tangent-space normal wherever the bake has no coverage."""
    output = array("f", pixels)
    for pixel_index, mask in enumerate(coverage):
        index = pixel_index * 4
        background = 1.0 - mask
        output[index] = output[index] * mask + 0.5 * background
        output[index + 1] = output[index + 1] * mask + 0.5 * background
        output[index + 2] = output[index + 2] * mask + background
        output[index + 3] = 1.0
    return output


def _finalize_bake_images(target, settings):
    base_image = _find_current_bake_image(
        target, BAKE_BASE_COLOR_NODE, BAKE_BASE_COLOR_IMAGE_PROP,
    ) if settings.bake_base_color else None
    normal_image = _find_current_bake_image(
        target, BAKE_NORMAL_NODE, BAKE_NORMAL_IMAGE_PROP,
    ) if settings.bake_normal else None
    coverage_source = base_image or normal_image
    resolution = _image_resolution(coverage_source)
    if resolution is None:
        return None

    coverage = _coverage_from_image(coverage_source, resolution)
    alpha_image = _ensure_target_image(
        target,
        settings,
        BAKE_ALPHA_IMAGE_PROP,
        "MergeMask",
        "Non-Color",
        generated_color=(0.0, 0.0, 0.0, 1.0),
        source_prop_name=BAKE_SOURCE_ALPHA_IMAGE_PROP,
    )
    _write_pixels(alpha_image, _alpha_map_pixels(coverage))

    if base_image is not None and _image_is_readable(base_image, resolution):
        pixels = _read_image_pixels(base_image, resolution)
        _write_pixels(
            base_image,
            _apply_bake_background(pixels, coverage, resolution, settings.bake_background_mode),
        )
    if normal_image is not None and _image_is_readable(normal_image, resolution):
        pixels = _read_image_pixels(normal_image, resolution)
        _write_pixels(normal_image, _fill_normal_background(pixels, coverage))
    return alpha_image


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


def _connected_texture_nodes(node_tree, output_type="OUTPUT_MATERIAL", visited=None):
    """Find image nodes upstream of material outputs, including node groups."""
    visited = set() if visited is None else visited
    if node_tree is None or node_tree in visited:
        return []
    visited.add(node_tree)
    pending = [node for node in node_tree.nodes if node.type == output_type
               and getattr(node, "is_active_output", True)]
    seen = set()
    textures = []
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        if node.type == "TEX_IMAGE" and node.image is not None:
            textures.append(node)
        if node.type == "GROUP":
            textures.extend(_connected_texture_nodes(node.node_tree, "GROUP_OUTPUT", visited))
        for socket in node.inputs:
            pending.extend(link.from_node for link in socket.links)
    return textures
