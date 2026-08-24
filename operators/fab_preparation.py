import os
import re
import shutil

import bpy

from ..localization import t


SOURCE_TEXTURE_GROUP_LABEL = "Source Texture Group"
SOURCE_TEXTURE_GROUP_PREFIX = "PolyGroups Source Textures"
NORMAL_MAP_NODE_LABEL = "FAB Normal Map"

FAB_VARIANTS = (
    ("HIGH", "HIGH", "Prepare selected mesh as HIGH"),
    ("MID", "MID", "Prepare selected mesh as MID"),
    ("LOW", "LOW", "Prepare selected mesh as LOW"),
)

VARIANT_ORDER = {
    "HIGH": 0,
    "MID": 1,
    "LOW": 2,
}

BSDF_TEXTURE_INPUTS = {
    "Base Color",
    "Metallic",
    "Roughness",
    "Alpha",
    "Normal",
    "Emission Color",
    "Emission Strength",
}

TEXTURE_SUFFIX_PATTERNS = (
    ("BaseColor", ("basecolor", "base_color", "diffuse", "albedo", "color", "col", "alb")),
    ("Normal", ("normalmap", "normal_map", "normal", "normals", "nmap", "norm", "nor")),
    ("Roughness", ("roughness", "rough", "rou")),
    ("Metallic", ("metalness", "metallic", "metal")),
    ("AO", ("ambientocclusion", "ambient_occlusion", "occlusion", "ao", "occ")),
    ("Emissive", ("emission", "emissive", "emit")),
    ("Opacity", ("opacity", "alpha", "mask")),
    ("Height", ("displacement", "heightmap", "height", "displ", "disp")),
)


def _safe_asset_token(value, fallback="Asset"):
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value or "").strip("_")
    value = re.sub(r"_+", "_", value)
    return value or fallback


def _safe_index_token(value):
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value or "").strip("_")
    value = re.sub(r"_+", "_", value)
    return value


def _name_parts(asset_name, asset_index, *suffixes):
    parts = [asset_name]
    if asset_index:
        parts.append(asset_index)
    parts.extend(item for item in suffixes if item)
    return "_".join(parts)


def _object_name(asset_name, asset_index, variant):
    return f"SM_{_name_parts(asset_name, asset_index, variant)}"


def _material_name(asset_name, asset_index, variant):
    suffix = "HIGH" if variant == "HIGH" else ""
    return f"M_{_name_parts(asset_name, asset_index, suffix)}"


def _texture_base_name(asset_name, asset_index, variant):
    suffix = "HIGH" if variant == "HIGH" else ""
    return f"T_{_name_parts(asset_name, asset_index, suffix)}"


def _collection_name(asset_name):
    return f"{asset_name}_Collection"


def _ensure_asset_collection(context, asset_name):
    collection_name = _collection_name(asset_name)
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)
        context.scene.collection.children.link(collection)
    return collection


def _apply_collection_color_tag(collection, settings):
    color_tag = getattr(settings, "fab_collection_color_tag", "NONE")
    if color_tag == "NONE":
        return
    try:
        collection.color_tag = color_tag
    except Exception:
        pass


def _move_object_to_collection(obj, collection):
    if obj.name not in collection.objects:
        collection.objects.link(obj)

    for source_collection in tuple(obj.users_collection):
        if source_collection is collection:
            continue
        source_collection.objects.unlink(obj)


def _increment_index(settings):
    if not settings.fab_auto_increment_index:
        return

    index = settings.fab_asset_index
    match = re.match(r"^(.*?)(\d+)$", index)
    if match is None:
        return

    prefix, number = match.groups()
    settings.fab_asset_index = f"{prefix}{int(number) + 1:0{len(number)}d}"


def _texture_suffix(image, node):
    text = " ".join(
        item
        for item in (
            getattr(node, "name", ""),
            getattr(node, "label", ""),
            getattr(image, "name", ""),
            getattr(image, "filepath", ""),
        )
        if item
    ).lower()
    text = text.replace("-", "_").replace(" ", "_")

    for suffix, patterns in TEXTURE_SUFFIX_PATTERNS:
        for pattern in patterns:
            if re.search(rf"(^|_|\.){re.escape(pattern)}($|_|\.)", text):
                return suffix

    return "Map"


def _principled_bsdf(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node

    return material.node_tree.nodes.get("Principled BSDF")


def _source_texture_group_nodes(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return []

    group_nodes = []
    for node in material.node_tree.nodes:
        if node.bl_idname != "ShaderNodeGroup" or node.node_tree is None:
            continue
        if (
            node.label == SOURCE_TEXTURE_GROUP_LABEL
            or node.name.startswith(SOURCE_TEXTURE_GROUP_LABEL)
            or node.node_tree.name.startswith(SOURCE_TEXTURE_GROUP_PREFIX)
        ):
            group_nodes.append(node)

    return group_nodes


def _group_output_node(node_tree):
    for node in node_tree.nodes:
        if node.bl_idname == "NodeGroupOutput" and getattr(node, "is_active_output", True):
            return node

    for node in node_tree.nodes:
        if node.bl_idname == "NodeGroupOutput":
            return node

    return None


def _linked_source_socket(input_socket):
    if input_socket is None or not input_socket.is_linked:
        return None
    return input_socket.links[0].from_socket


def _trace_image_texture_node(socket, visited=None):
    if socket is None:
        return None

    visited = visited or set()
    node = socket.node
    if node in visited:
        return None
    visited.add(node)

    if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None) is not None:
        return node

    for input_socket in node.inputs:
        image_node = _trace_image_texture_node(_linked_source_socket(input_socket), visited)
        if image_node is not None:
            return image_node

    return None


def _copy_image_node_settings(source_node, target_node):
    target_node.image = source_node.image
    target_node.extension = source_node.extension
    target_node.interpolation = source_node.interpolation
    target_node.projection = source_node.projection
    target_node.label = source_node.label or source_node.name
    target_node.name = source_node.name


def _clear_input_links(tree, input_socket):
    if input_socket is None:
        return
    for link in list(input_socket.links):
        tree.links.remove(link)


def _link_once(tree, from_socket, to_socket):
    if from_socket is None or to_socket is None:
        return False

    for link in tree.links:
        if link.from_socket == from_socket and link.to_socket == to_socket:
            return False

    tree.links.new(from_socket, to_socket)
    return True


def _ensure_normal_map_node(material):
    nodes = material.node_tree.nodes
    node = nodes.get(NORMAL_MAP_NODE_LABEL)
    if node is None or node.bl_idname != "ShaderNodeNormalMap":
        node = nodes.new("ShaderNodeNormalMap")
        node.name = NORMAL_MAP_NODE_LABEL
        node.label = NORMAL_MAP_NODE_LABEL
        node.location = (-260, -360)
    return node


def _connect_texture_to_bsdf(material, texture_node, input_name):
    bsdf = _principled_bsdf(material)
    if bsdf is None:
        return False

    tree = material.node_tree
    input_socket = bsdf.inputs.get(input_name)
    if input_socket is None:
        return False

    if input_name == "Normal":
        normal_map = _ensure_normal_map_node(material)
        color_input = normal_map.inputs.get("Color")
        normal_output = normal_map.outputs.get("Normal")
        _clear_input_links(tree, color_input)
        _clear_input_links(tree, input_socket)
        linked_color = _link_once(tree, texture_node.outputs.get("Color"), color_input)
        linked_normal = _link_once(tree, normal_output, input_socket)
        return linked_color or linked_normal

    output_socket = texture_node.outputs.get("Alpha") if input_name == "Alpha" else None
    output_socket = output_socket or texture_node.outputs.get("Color") or texture_node.outputs.get("Alpha")
    _clear_input_links(tree, input_socket)
    return _link_once(tree, output_socket, input_socket)


def _ungroup_source_texture_nodes(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return 0

    nodes = material.node_tree.nodes
    ungrouped_count = 0
    for group_node in list(_source_texture_group_nodes(material)):
        group_output = _group_output_node(group_node.node_tree)
        if group_output is None:
            continue

        group_ungrouped = 0
        for output_socket in group_node.outputs:
            input_name = output_socket.name
            if input_name not in BSDF_TEXTURE_INPUTS:
                continue

            group_input = group_output.inputs.get(input_name)
            image_node = _trace_image_texture_node(_linked_source_socket(group_input))
            if image_node is None:
                continue

            texture_node = nodes.new("ShaderNodeTexImage")
            texture_node.location = (
                group_node.location.x - 280,
                group_node.location.y - 90 * ungrouped_count,
            )
            _copy_image_node_settings(image_node, texture_node)
            if _connect_texture_to_bsdf(material, texture_node, input_name):
                ungrouped_count += 1
                group_ungrouped += 1

        if group_ungrouped:
            nodes.remove(group_node)

    return ungrouped_count


def _iter_image_texture_nodes(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return

    _ungroup_source_texture_nodes(material)

    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None) is not None:
            yield node


def _texture_output_directory(settings, asset_name):
    if not bpy.data.filepath:
        return None

    blend_dir = os.path.dirname(bpy.data.filepath)
    return os.path.join(blend_dir, "Textures", asset_name)


def _external_image_filepath(image):
    filepath = image.filepath_raw or image.filepath
    if not filepath:
        return ""

    return bpy.path.abspath(filepath)


def _copy_and_rename_material_textures(material, settings, asset_name, asset_index, variant, report=None):
    texture_base_name = _texture_base_name(asset_name, asset_index, variant)
    output_dir = _texture_output_directory(settings, asset_name)
    suffix_counts = {}
    copied_count = 0
    renamed_count = 0
    ungrouped_count = _ungroup_source_texture_nodes(material)

    if settings.fab_copy_textures and output_dir is None and report:
        report({"WARNING"}, "Save the blend file before copying FAB textures")

    for node in _iter_image_texture_nodes(material):
        image = node.image
        suffix = _texture_suffix(image, node)
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
        suffix_name = suffix if suffix_counts[suffix] == 1 else f"{suffix}_{suffix_counts[suffix]}"
        texture_name = f"{texture_base_name}_{suffix_name}"

        image.name = texture_name
        renamed_count += 1

        if not settings.fab_copy_textures or output_dir is None:
            continue

        source_filepath = _external_image_filepath(image)
        if not source_filepath or not os.path.isfile(source_filepath):
            continue

        extension = os.path.splitext(source_filepath)[1] or ".png"
        destination_filepath = os.path.join(output_dir, f"{texture_name}{extension.lower()}")
        os.makedirs(output_dir, exist_ok=True)

        try:
            if os.path.abspath(source_filepath) != os.path.abspath(destination_filepath):
                shutil.copy2(source_filepath, destination_filepath)
            image.filepath = bpy.path.relpath(destination_filepath)
            image.filepath_raw = bpy.path.relpath(destination_filepath)
            copied_count += 1
        except OSError as error:
            if report:
                report({"WARNING"}, f"{image.name}: {error}")

    return renamed_count, copied_count, ungrouped_count


def _ensure_fab_material(obj, material_name):
    existing_material = bpy.data.materials.get(material_name)
    source_material = obj.active_material or (obj.data.materials[0] if obj.data.materials else None)

    if existing_material is not None:
        material = existing_material
    elif source_material is not None:
        material = source_material
        material.name = material_name
    else:
        material = bpy.data.materials.new(material_name)
        material.use_nodes = True

    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj.active_material_index = 0
    for polygon in obj.data.polygons:
        polygon.material_index = 0

    return material


def prepare_object_for_fab(context, obj, variant, settings, report=None):
    if obj is None or obj.type != "MESH":
        return False

    asset_name = _safe_asset_token(settings.fab_asset_name)
    asset_index = _safe_index_token(settings.fab_asset_index)
    object_name = _object_name(asset_name, asset_index, variant)
    material_name = _material_name(asset_name, asset_index, variant)

    if obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    obj.name = object_name
    obj.data.name = object_name
    material = _ensure_fab_material(obj, material_name)
    renamed_textures, copied_textures, ungrouped_textures = _copy_and_rename_material_textures(
        material,
        settings,
        asset_name,
        asset_index,
        variant,
        report,
    )

    if report:
        report(
            {"INFO"},
            (
                f"Prepared {obj.name}: material {material.name}, "
                f"ungrouped {ungrouped_textures} texture node(s), "
                f"renamed {renamed_textures} texture(s), copied {copied_textures}"
            ),
        )

    return True


def classify_fab_variant(obj):
    name = obj.name.lower()
    sm_match = re.match(r"^sm_.+_(high|mid|low)$", name)
    if sm_match is not None:
        return sm_match.group(1).upper()
    if "smartdecimated" in name:
        return "LOW"
    if name.startswith("retopo_"):
        return "MID"
    if name.startswith("highpoly_generated"):
        return "HIGH"
    return ""


class OBJECT_OT_polygroups_prepare_fab_variant(bpy.types.Operator):
    bl_idname = "object.polygroups_prepare_fab_variant"
    bl_label = "Prepare FAB Variant"
    bl_description = "Rename the active mesh and prepare its material/textures for FAB and Unreal"
    bl_options = {"REGISTER", "UNDO"}

    variant: bpy.props.EnumProperty(
        name="Variant",
        items=FAB_VARIANTS,
        default="LOW",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        obj = context.active_object
        if not prepare_object_for_fab(context, obj, self.variant, settings, self.report):
            self.report({"ERROR"}, "Active object must be a mesh")
            return {"CANCELLED"}

        _increment_index(settings)
        return {"FINISHED"}


class OBJECT_OT_polygroups_auto_prepare_fab_selection(bpy.types.Operator):
    bl_idname = "object.polygroups_auto_prepare_fab_selection"
    bl_label = "Auto Prepare FAB Selection"
    bl_description = "Auto-detect selected HIGH, MID, and LOW meshes, then prepare FAB names, materials, and textures"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=420,
            confirm_text=t(context, "continue"),
        )

    def draw(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        layout = self.layout
        layout.label(text=t(context, "fab_rename_set_warning"), icon="ERROR")
        layout.prop(settings, "fab_asset_name", text=t(context, "fab_asset_name"))

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        mesh_objects = [obj for obj in context.selected_objects if obj.type == "MESH"]
        asset_name = _safe_asset_token(settings.fab_asset_name)
        asset_collection = _ensure_asset_collection(context, asset_name)
        _apply_collection_color_tag(asset_collection, settings)
        prepared_count = 0
        skipped_count = 0

        classified_objects = []
        for obj in mesh_objects:
            variant = classify_fab_variant(obj)
            if not variant:
                skipped_count += 1
                self.report({"WARNING"}, f"{obj.name}: could not detect LOW/MID/HIGH role")
                continue
            classified_objects.append((VARIANT_ORDER[variant], obj.name.lower(), obj, variant))

        for _order, _name, obj, variant in sorted(classified_objects):
            context.view_layer.objects.active = obj
            obj.select_set(True)
            if prepare_object_for_fab(context, obj, variant, settings, self.report):
                _move_object_to_collection(obj, asset_collection)
                prepared_count += 1

        if prepared_count:
            _increment_index(settings)

        self.report(
            {"INFO"},
            (
                f"Auto prepared {prepared_count} FAB mesh object(s), "
                f"moved to {asset_collection.name}, skipped {skipped_count}"
            ),
        )
        return {"FINISHED"} if prepared_count else {"CANCELLED"}
