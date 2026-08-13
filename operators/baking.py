import bpy


BAKE_MATERIAL_NAME = "Bake_Target"
BAKE_BASE_COLOR_NODE = "PolyGroups Bake Base Color"
BAKE_NORMAL_NODE = "PolyGroups Bake Normal"


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


def _ensure_bake_material(target, settings):
    if target.data.uv_layers.active is None:
        target.data.uv_layers.new(name="UVMap")

    material = bpy.data.materials.get(BAKE_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(BAKE_MATERIAL_NAME)
    material.use_nodes = True

    if target.data.materials:
        target.data.materials[0] = material
    else:
        target.data.materials.append(material)
    for polygon in target.data.polygons:
        polygon.material_index = 0

    tree = material.node_tree
    nodes = tree.nodes
    bsdf = _principled_bsdf(material)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    base_image = bpy.data.images.get(f"{settings.image_prefix}_BaseColor")
    if base_image is None or base_image.size[0] != settings.bake_resolution:
        base_image = _make_image(
            f"{settings.image_prefix}_BaseColor",
            settings.bake_resolution,
            "sRGB",
        )

    normal_image = bpy.data.images.get(f"{settings.image_prefix}_Normal")
    if normal_image is None or normal_image.size[0] != settings.bake_resolution:
        normal_image = _make_image(
            f"{settings.image_prefix}_Normal",
            settings.bake_resolution,
            "Non-Color",
        )
        normal_image.generated_color = (0.5, 0.5, 1.0, 1.0)

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

        material, base_node, normal_node = _ensure_bake_material(target, settings)
        target.active_material = material
        _select_sources_and_target(context, sources, target)

        if settings.bake_base_color:
            _bake_to_node(context, target, base_node, "DIFFUSE", settings)

        if settings.bake_normal:
            _bake_to_node(context, target, normal_node, "NORMAL", settings)

        self.report(
            {"INFO"},
            f"Prepared {changed_count} material(s) and finished bake",
        )
        return {"FINISHED"}
