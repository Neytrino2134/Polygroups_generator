import bpy
import random


TEXTURE_BSDF_INPUTS = (
    "Base Color",
    "Metallic",
    "Roughness",
    "Alpha",
    "Normal",
    "Emission Color",
    "Emission Strength",
)

SOURCE_TEXTURE_GROUP_PREFIX = "PolyGroups Source Textures"
SOURCE_TEXTURE_GROUP_NODE_LABEL = "Source Texture Group"
POLYGROUP_COLOR_TINT_LABEL = "PolyGroup Color Tint"


def clear_materials(obj):
    obj.data.materials.clear()


def random_color():
    return (
        random.uniform(0.15, 0.9),
        random.uniform(0.15, 0.9),
        random.uniform(0.15, 0.9),
        1.0,
    )


def source_material_from_object(obj):
    if obj.active_material is not None:
        return obj.active_material

    for material in obj.data.materials:
        if material is not None:
            return material

    return None


def _principled_bsdf(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node

    return material.node_tree.nodes.get("Principled BSDF")


def _socket_type(socket):
    return {
        "RGBA": "NodeSocketColor",
        "VECTOR": "NodeSocketVector",
        "VALUE": "NodeSocketFloat",
        "INT": "NodeSocketInt",
        "BOOLEAN": "NodeSocketBool",
        "SHADER": "NodeSocketShader",
    }.get(getattr(socket, "type", ""), "NodeSocketFloat")


def _matching_socket(sockets, source_socket):
    identifier = getattr(source_socket, "identifier", None)
    if identifier:
        socket = sockets.get(identifier)
        if socket is not None:
            return socket

    socket = sockets.get(source_socket.name)
    if socket is not None:
        return socket

    for index, item in enumerate(source_socket.node.outputs if source_socket.is_output else source_socket.node.inputs):
        if item == source_socket and index < len(sockets):
            return sockets[index]

    return None


def _copy_default_value(source_socket, target_socket):
    if source_socket is None or target_socket is None:
        return
    if not hasattr(source_socket, "default_value") or not hasattr(target_socket, "default_value"):
        return

    try:
        value = source_socket.default_value
        if hasattr(value, "__len__") and not isinstance(value, str):
            target_socket.default_value = tuple(value)
        else:
            target_socket.default_value = value
    except Exception:
        pass


def _copy_node_settings(source_node, target_node):
    skip = {
        "rna_type",
        "type",
        "dimensions",
        "inputs",
        "outputs",
        "internal_links",
        "select",
        "location",
        "name",
        "label",
        "parent",
    }

    target_node.label = source_node.label or source_node.name
    target_node.location = source_node.location
    target_node.width = source_node.width

    for prop in source_node.bl_rna.properties:
        if prop.identifier in skip or prop.is_readonly:
            continue
        try:
            setattr(target_node, prop.identifier, getattr(source_node, prop.identifier))
        except Exception:
            pass

    for source_input in source_node.inputs:
        if source_input.is_linked:
            continue
        target_input = _matching_socket(target_node.inputs, source_input)
        _copy_default_value(source_input, target_input)


def _clone_upstream_node(source_node, group_tree, node_map):
    if source_node in node_map:
        return node_map[source_node]

    try:
        cloned_node = group_tree.nodes.new(source_node.bl_idname)
    except Exception:
        return None

    node_map[source_node] = cloned_node
    _copy_node_settings(source_node, cloned_node)

    for source_input in source_node.inputs:
        if not source_input.is_linked:
            continue

        target_input = _matching_socket(cloned_node.inputs, source_input)
        if target_input is None:
            continue

        link = source_input.links[0]
        upstream_node = _clone_upstream_node(link.from_node, group_tree, node_map)
        if upstream_node is None:
            continue

        target_output = _matching_socket(upstream_node.outputs, link.from_socket)
        if target_output is None:
            continue

        try:
            group_tree.links.new(target_output, target_input)
        except Exception:
            pass

    return cloned_node


def _texture_links_from_material(source_material):
    bsdf = _principled_bsdf(source_material)
    if bsdf is None:
        return {}

    links = {}
    for input_name in TEXTURE_BSDF_INPUTS:
        socket = bsdf.inputs.get(input_name)
        if socket is not None and socket.is_linked:
            links[input_name] = socket.links[0].from_socket

    return links


def _source_texture_group_node(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    for node in material.node_tree.nodes:
        if node.bl_idname != "ShaderNodeGroup" or node.node_tree is None:
            continue
        if node.label == SOURCE_TEXTURE_GROUP_NODE_LABEL or node.name.startswith(SOURCE_TEXTURE_GROUP_NODE_LABEL):
            return node

    return None


def _source_texture_group_from_object(obj):
    if obj is None or obj.type != "MESH":
        return None, set()

    for material in obj.data.materials:
        group_node = _source_texture_group_node(material)
        if group_node is None:
            continue

        output_names = {
            output.name
            for output in group_node.outputs
            if output.name and output.name != "Geometry"
        }
        if output_names:
            return group_node.node_tree, output_names

    return None, set()


def create_source_texture_group(source_material):
    existing_group_node = _source_texture_group_node(source_material)
    if existing_group_node is not None:
        output_names = {
            output.name
            for output in existing_group_node.outputs
            if output.name and output.name != "Geometry"
        }
        if output_names:
            return existing_group_node.node_tree, output_names

    texture_links = _texture_links_from_material(source_material)
    if not texture_links:
        return None, set()

    group_name = f"{SOURCE_TEXTURE_GROUP_PREFIX} - {source_material.name}"
    group_tree = bpy.data.node_groups.new(group_name, "ShaderNodeTree")
    group_output = group_tree.nodes.new("NodeGroupOutput")
    group_output.location = (420, 0)
    node_map = {}
    exported_names = set()

    for input_name, source_socket in texture_links.items():
        cloned_node = _clone_upstream_node(source_socket.node, group_tree, node_map)
        if cloned_node is None:
            continue

        cloned_socket = _matching_socket(cloned_node.outputs, source_socket)
        if cloned_socket is None:
            continue

        try:
            group_tree.interface.new_socket(
                input_name,
                in_out="OUTPUT",
                socket_type=_socket_type(source_socket),
            )
        except Exception:
            continue

        output_socket = group_output.inputs.get(input_name)
        if output_socket is None:
            continue

        try:
            group_tree.links.new(cloned_socket, output_socket)
            exported_names.add(input_name)
        except Exception:
            pass

    if not exported_names:
        bpy.data.node_groups.remove(group_tree)
        return None, set()

    return group_tree, exported_names


def _new_principled_material(name):
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    bsdf = _principled_bsdf(material)
    return material, bsdf


def _clear_input_links(tree, input_socket):
    if input_socket is None:
        return
    for link in list(input_socket.links):
        tree.links.remove(link)


def _find_source_texture_group_node(material, texture_group):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    fallback = None
    for node in material.node_tree.nodes:
        if node.bl_idname != "ShaderNodeGroup" or node.node_tree is None:
            continue
        if node.node_tree == texture_group:
            return node
        if node.label == SOURCE_TEXTURE_GROUP_NODE_LABEL or node.name.startswith(SOURCE_TEXTURE_GROUP_NODE_LABEL):
            fallback = node

    return fallback


def _ensure_source_texture_group_node(material, texture_group):
    nodes = material.node_tree.nodes
    group_node = _find_source_texture_group_node(material, texture_group)
    if group_node is None:
        group_node = nodes.new("ShaderNodeGroup")
        group_node.location = (-520, 80)

    group_node.node_tree = texture_group
    group_node.label = SOURCE_TEXTURE_GROUP_NODE_LABEL
    return group_node


def _find_tint_node(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    for node in material.node_tree.nodes:
        if node.label == POLYGROUP_COLOR_TINT_LABEL or node.name.startswith(POLYGROUP_COLOR_TINT_LABEL):
            return node

    return None


def _ensure_tint_node(material):
    tint_node = _find_tint_node(material)
    if tint_node is None:
        tint_node = material.node_tree.nodes.new("ShaderNodeMix")
        tint_node.location = (-240, 130)

    tint_node.label = POLYGROUP_COLOR_TINT_LABEL
    tint_node.data_type = "RGBA"
    tint_node.blend_type = "MULTIPLY"
    tint_node.inputs["Factor"].default_value = 1.0
    return tint_node


def _polygroup_color_from_material(material):
    tint_node = _find_tint_node(material)
    if tint_node is not None and len(tint_node.inputs) > 7:
        try:
            return tuple(tint_node.inputs[7].default_value)
        except Exception:
            pass

    bsdf = _principled_bsdf(material)
    if bsdf is not None:
        base_input = bsdf.inputs.get("Base Color")
        if base_input is not None and hasattr(base_input, "default_value"):
            try:
                return tuple(base_input.default_value)
            except Exception:
                pass

    return tuple(material.diffuse_color) if material is not None else random_color()


def _link_once(tree, from_socket, to_socket):
    if from_socket is None or to_socket is None:
        return False

    for link in tree.links:
        if link.from_socket == from_socket and link.to_socket == to_socket:
            return False

    tree.links.new(from_socket, to_socket)
    return True


def _connect_source_textures(material, bsdf, texture_group, texture_outputs, color, material_mode):
    if bsdf is None or texture_group is None:
        return False

    links = material.node_tree.links
    group_node = _ensure_source_texture_group_node(material, texture_group)

    used_base_texture = False
    base_output = group_node.outputs.get("Base Color")
    base_input = bsdf.inputs.get("Base Color")

    if base_output is not None and base_input is not None and material_mode == "TEXTURE_ONLY":
        _clear_input_links(material.node_tree, base_input)
        links.new(base_output, base_input)
        used_base_texture = True
    elif base_output is not None and base_input is not None and material_mode == "TEXTURE_TINT":
        mix_node = _ensure_tint_node(material)
        mix_node.inputs[7].default_value = color
        _clear_input_links(material.node_tree, mix_node.inputs[6])
        _clear_input_links(material.node_tree, base_input)
        links.new(base_output, mix_node.inputs[6])
        links.new(mix_node.outputs[2], base_input)
        used_base_texture = True

    for output_name in texture_outputs:
        if output_name == "Base Color":
            continue

        output_socket = group_node.outputs.get(output_name)
        input_socket = bsdf.inputs.get(output_name)
        if output_socket is None or input_socket is None:
            continue

        try:
            _clear_input_links(material.node_tree, input_socket)
            links.new(output_socket, input_socket)
        except Exception:
            pass

    return used_base_texture


def apply_material_mode(material, material_mode, texture_group=None, texture_outputs=None, color=None):
    if material is None:
        return False

    material.use_nodes = True
    bsdf = _principled_bsdf(material)
    if bsdf is None:
        return False

    texture_outputs = texture_outputs or set()
    color = color or _polygroup_color_from_material(material)
    material.diffuse_color = color

    if material_mode == "COLOR_ONLY" or texture_group is None:
        for input_name in TEXTURE_BSDF_INPUTS:
            _clear_input_links(material.node_tree, bsdf.inputs.get(input_name))
        base_input = bsdf.inputs.get("Base Color")
        if base_input is not None:
            base_input.default_value = color
        return True

    _connect_source_textures(
        material,
        bsdf,
        texture_group,
        texture_outputs,
        color,
        material_mode,
    )
    return True


def create_material(name, color, texture_group=None, texture_outputs=None, material_mode="COLOR_ONLY"):
    texture_outputs = texture_outputs or set()
    material, bsdf = _new_principled_material(name)
    material.diffuse_color = color

    use_textures = material_mode in {"TEXTURE_ONLY", "TEXTURE_TINT"} and texture_group is not None
    used_base_texture = False
    if use_textures:
        used_base_texture = _connect_source_textures(
            material,
            bsdf,
            texture_group,
            texture_outputs,
            color,
            material_mode,
        )

    if bsdf is not None and not used_base_texture:
        bsdf.inputs["Base Color"].default_value = color

    return material


def texture_group_for_object(obj, material_mode):
    texture_group = None
    texture_outputs = set()

    if material_mode not in {"TEXTURE_ONLY", "TEXTURE_TINT"}:
        return None, set(), material_mode

    texture_group, texture_outputs = _source_texture_group_from_object(obj)
    if texture_group is None:
        texture_group, texture_outputs = create_source_texture_group(source_material_from_object(obj))

    if texture_group is None:
        material_mode = "COLOR_ONLY"

    return texture_group, texture_outputs, material_mode


def apply_material_mode_to_object(obj, material_mode):
    texture_group, texture_outputs, material_mode = texture_group_for_object(obj, material_mode)
    changed_count = 0

    for material in obj.data.materials:
        if apply_material_mode(
            material,
            material_mode,
            texture_group=texture_group,
            texture_outputs=texture_outputs,
        ):
            changed_count += 1

    return changed_count, material_mode


def assign_materials(obj, groups, prefix="FaceSet", material_mode="COLOR_ONLY"):
    texture_group, texture_outputs, material_mode = texture_group_for_object(obj, material_mode)

    clear_materials(obj)

    for index, group in enumerate(groups, start=1):
        material = create_material(
            f"{prefix}_{index:03d}",
            random_color(),
            texture_group=texture_group,
            texture_outputs=texture_outputs,
            material_mode=material_mode,
        )
        obj.data.materials.append(material)
        material_index = len(obj.data.materials) - 1

        for face in group:
            face.material_index = material_index
