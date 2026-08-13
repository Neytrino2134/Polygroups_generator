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


def create_source_texture_group(source_material):
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


def _connect_source_textures(material, bsdf, texture_group, texture_outputs, color, material_mode):
    if bsdf is None or texture_group is None:
        return False

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    group_node = nodes.new("ShaderNodeGroup")
    group_node.node_tree = texture_group
    group_node.label = "Source Texture Group"
    group_node.location = (-520, 80)

    used_base_texture = False
    base_output = group_node.outputs.get("Base Color")
    base_input = bsdf.inputs.get("Base Color")

    if base_output is not None and base_input is not None and material_mode == "TEXTURE_ONLY":
        links.new(base_output, base_input)
        used_base_texture = True
    elif base_output is not None and base_input is not None and material_mode == "TEXTURE_TINT":
        mix_node = nodes.new("ShaderNodeMix")
        mix_node.label = "PolyGroup Color Tint"
        mix_node.data_type = "RGBA"
        mix_node.blend_type = "MULTIPLY"
        mix_node.location = (-240, 130)
        mix_node.inputs["Factor"].default_value = 1.0
        mix_node.inputs[7].default_value = color
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
            links.new(output_socket, input_socket)
        except Exception:
            pass

    return used_base_texture


def create_material(name, color, texture_group=None, texture_outputs=None, material_mode="COLOR_ONLY"):
    texture_outputs = texture_outputs or set()
    material, bsdf = _new_principled_material(name)

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


def assign_materials(obj, groups, prefix="FaceSet", material_mode="COLOR_ONLY"):
    source_material = source_material_from_object(obj)
    texture_group = None
    texture_outputs = set()

    if material_mode in {"TEXTURE_ONLY", "TEXTURE_TINT"}:
        texture_group, texture_outputs = create_source_texture_group(source_material)
        if texture_group is None:
            material_mode = "COLOR_ONLY"

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
