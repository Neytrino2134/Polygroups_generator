import bpy


BASE_COLOR_KEYWORDS = (
    "base color",
    "base_color",
    "basecolor",
    "albedo",
    "diffuse",
    "color",
    "colour",
    "col",
)
NORMAL_KEYWORDS = (
    "normal",
    "norm",
    "nrm",
)


def _selected_mesh_objects(context):
    return [
        obj
        for obj in context.selected_objects
        if obj.type == "MESH"
    ]


def _node_text(node):
    parts = [node.name, node.label]
    image = getattr(node, "image", None)
    if image is not None:
        parts.append(image.name)
        parts.append(image.filepath)
    return " ".join(part for part in parts if part).lower()


def _principled_bsdf(material):
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node

    node = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    node.location = (0, 120)
    return node


def _material_output(material):
    output = None
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeOutputMaterial" and getattr(node, "is_active_output", False):
            output = node
            break

    if output is None:
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeOutputMaterial":
                output = node
                break

    if output is None:
        output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 120)

    return output


def _image_texture_nodes(material):
    return [
        node
        for node in material.node_tree.nodes
        if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None) is not None
    ]


def _is_normal_node(node):
    text = _node_text(node)
    return any(keyword in text for keyword in NORMAL_KEYWORDS)


def _is_base_color_node(node):
    if _is_normal_node(node):
        return False

    text = _node_text(node)
    return any(keyword in text for keyword in BASE_COLOR_KEYWORDS)


def _first_image_node_by_role(nodes, predicate):
    for node in nodes:
        if predicate(node):
            return node
    return None


def _ensure_link(tree, from_socket, to_socket):
    if from_socket is None or to_socket is None:
        return False

    changed = False
    already_linked = False
    for link in list(to_socket.links):
        if link.from_socket == from_socket:
            already_linked = True
        else:
            tree.links.remove(link)
            changed = True

    if not already_linked:
        tree.links.new(from_socket, to_socket)
        changed = True

    return changed


def _ensure_non_color(image):
    if image is None:
        return False

    try:
        if image.colorspace_settings.name != "Non-Color":
            image.colorspace_settings.name = "Non-Color"
            return True
    except Exception:
        return False

    return False


def _ensure_normal_map_node(material):
    nodes = material.node_tree.nodes
    node = nodes.get("AI Retopo Normal Map")
    if node is None or node.bl_idname != "ShaderNodeNormalMap":
        node = nodes.new("ShaderNodeNormalMap")
        node.name = "AI Retopo Normal Map"
        node.label = "Normal Map"
        node.location = (-260, -120)
    return node


def _check_material(material):
    if material is None:
        return {
            "materials": 0,
            "links": 0,
            "normal_colorspace": 0,
        }

    material.use_nodes = True
    tree = material.node_tree
    bsdf = _principled_bsdf(material)
    output = _material_output(material)
    image_nodes = _image_texture_nodes(material)

    stats = {
        "materials": 1,
        "links": 0,
        "normal_colorspace": 0,
    }

    if _ensure_link(tree, bsdf.outputs.get("BSDF"), output.inputs.get("Surface")):
        stats["links"] += 1

    normal_nodes = [node for node in image_nodes if _is_normal_node(node)]
    for node in normal_nodes:
        if _ensure_non_color(node.image):
            stats["normal_colorspace"] += 1

    base_node = _first_image_node_by_role(image_nodes, _is_base_color_node)
    if base_node is None and len(image_nodes) == 1 and not _is_normal_node(image_nodes[0]):
        base_node = image_nodes[0]

    normal_node = normal_nodes[0] if normal_nodes else None

    if base_node is not None:
        if _ensure_link(
            tree,
            base_node.outputs.get("Color"),
            bsdf.inputs.get("Base Color"),
        ):
            stats["links"] += 1

    if normal_node is not None:
        normal_map = _ensure_normal_map_node(material)
        if _ensure_link(
            tree,
            normal_node.outputs.get("Color"),
            normal_map.inputs.get("Color"),
        ):
            stats["links"] += 1
        if _ensure_link(
            tree,
            normal_map.outputs.get("Normal"),
            bsdf.inputs.get("Normal"),
        ):
            stats["links"] += 1

    return stats


class OBJECT_OT_polygroups_check_material_textures(bpy.types.Operator):
    bl_idname = "object.polygroups_check_material_textures"
    bl_label = "Check Material/Textures"
    bl_description = "Fix selected object materials for Base Color, Normal, and Material Output connections"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_selected_mesh_objects(context))

    def execute(self, context):
        objects = _selected_mesh_objects(context)
        materials = []
        for obj in objects:
            for slot in obj.material_slots:
                material = slot.material
                if material is not None and material not in materials:
                    materials.append(material)

        if not materials:
            self.report({"WARNING"}, "Selected mesh objects have no materials")
            return {"CANCELLED"}

        totals = {
            "materials": 0,
            "links": 0,
            "normal_colorspace": 0,
        }
        for material in materials:
            stats = _check_material(material)
            for key, value in stats.items():
                totals[key] += value

        self.report(
            {"INFO"},
            (
                f"Checked {totals['materials']} material(s), "
                f"fixed {totals['links']} link(s), "
                f"set {totals['normal_colorspace']} normal image(s) to Non-Color"
            ),
        )
        return {"FINISHED"}
