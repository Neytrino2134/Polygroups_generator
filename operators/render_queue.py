import json
import os
import re
from math import radians

import bpy


ASSET_COLLECTION_SUFFIX = "_Collection"
ASSET_RENDER_SUFFIXES = ("LOW", "MID")
BLENDER_NUMERIC_SUFFIX_RE = re.compile(r"\.\d{3}$")
MULTIVIEW_PROP = "polygroups_render_multiview"
MULTIVIEW_COLLECTION_SUFFIX = "_Multi_View"
TEMP_FREESTYLE_RENDER_LAYERS_NODE = "__POLYGROUPS_FREESTYLE_RENDER_LAYERS__"
TEMP_FREESTYLE_COMPOSITE_NODE = "__POLYGROUPS_FREESTYLE_COMPOSITE__"
TEMP_FREESTYLE_PASS_MATERIAL = "__POLYGROUPS_FREESTYLE_PASS_MATTE__"


def _collection_objects_recursive(collection, seen=None):
    seen = seen or set()
    objects = []
    for obj in collection.objects:
        if obj.name in seen:
            continue
        seen.add(obj.name)
        objects.append(obj)
    for child in collection.children:
        objects.extend(_collection_objects_recursive(child, seen))
    return objects


def _asset_name_from_collection(collection):
    collection_name = _base_name(collection.name)
    if not collection_name.upper().endswith(ASSET_COLLECTION_SUFFIX.upper()):
        return ""
    return collection_name[: -len(ASSET_COLLECTION_SUFFIX)]


def _base_name(name):
    return BLENDER_NUMERIC_SUFFIX_RE.sub("", name)


def _clean_name(name):
    return bpy.path.clean_name(name)


def _render_output_base_directory(settings):
    directory = (settings.output_directory or "Renders").strip() or "Renders"
    if directory.startswith("//"):
        return bpy.path.abspath(directory)
    if os.path.isabs(directory):
        return bpy.path.abspath(directory)
    return os.path.join(bpy.path.abspath("//"), directory)


def _normalize_render_output_setting(settings):
    directory = (settings.output_directory or "").strip()
    if directory.startswith("//"):
        settings.output_directory = bpy.path.abspath(directory)


def _freestyle_pass_path(output_path):
    root, _ = os.path.splitext(output_path)
    return f"{root}_freestyle_pass.png"


def _freestyle_overlay_path(output_path):
    root, _ = os.path.splitext(output_path)
    return f"{root}_freestyle_overlay.png"


def _render_suffix_from_name(name):
    upper_name = _base_name(name).upper()
    for suffix in ASSET_RENDER_SUFFIXES:
        if upper_name.endswith(f"_{suffix}"):
            return suffix
    return ""


def _find_asset_objects(collection, asset_name, settings):
    include_suffixes = set()
    if settings.render_low:
        include_suffixes.add("LOW")
    if settings.render_mid:
        include_suffixes.add("MID")

    objects_by_suffix = {}
    for obj in _collection_objects_recursive(collection):
        if obj.type != "MESH":
            continue
        suffix = _render_suffix_from_name(obj.name)
        if suffix not in include_suffixes:
            continue
        objects_by_suffix.setdefault(suffix, obj)

    return [objects_by_suffix[suffix] for suffix in ASSET_RENDER_SUFFIXES if suffix in objects_by_suffix]


def _scan_render_queue(settings):
    base_directory = _render_output_base_directory(settings)
    queue = []
    collection_names = set()

    for collection in bpy.data.collections:
        asset_name = _asset_name_from_collection(collection)
        if not asset_name:
            continue

        collection_names.add(collection.name)
        objects = _find_asset_objects(collection, asset_name, settings)
        if not objects:
            continue

        asset_directory = os.path.join(base_directory, _clean_name(asset_name))
        for obj in objects:
            suffix = _render_suffix_from_name(obj.name)
            output_path = os.path.join(asset_directory, f"{_clean_name(_base_name(obj.name))}.png")
            queue.append(
                {
                    "asset_name": asset_name,
                    "collection": collection.name,
                    "object": obj.name,
                    "variant": suffix,
                    "output_path": output_path,
                    "freestyle_output_path": _freestyle_pass_path(output_path),
                    "freestyle_overlay_path": _freestyle_overlay_path(output_path),
                },
            )

    return queue, len(collection_names)


def _load_queue(settings):
    try:
        queue = json.loads(settings.queue_data or "[]")
    except Exception:
        queue = []
    return queue if isinstance(queue, list) else []


def _store_queue(settings, queue, collection_count=None):
    settings.queue_data = json.dumps(queue)
    settings.total_count = len(queue)
    settings.collection_count = len({item.get("collection", "") for item in queue}) if collection_count is None else collection_count
    _sync_progress(settings)


def _sync_progress(settings):
    settings.rendered_count = min(settings.queue_index, settings.total_count)
    settings.remaining_count = max(settings.total_count - settings.rendered_count, 0)


def _scene_collection_matches(collection, settings):
    prefix = _base_name(settings.scene_collection_prefix.strip() or "Scene").upper()
    name = _base_name(collection.name).upper()
    return name == prefix or name.startswith(f"{prefix}_") or name.startswith(f"{prefix}.")


def _queue_objects(queue):
    objects = []
    seen = set()
    for job in queue:
        obj = bpy.data.objects.get(job.get("object", ""))
        if obj is None or obj.type != "MESH" or obj.name in seen:
            continue
        seen.add(obj.name)
        objects.append(obj)
    return objects


def _add_freestyle_candidate(objects, seen, obj):
    if obj is None or obj.type != "MESH" or obj.name in seen:
        return
    if not _render_suffix_from_name(obj.name):
        return
    seen.add(obj.name)
    objects.append(obj)


def _asset_mesh_objects(settings=None):
    objects = []
    seen = set()

    if settings is not None:
        for obj in _queue_objects(_load_queue(settings)):
            _add_freestyle_candidate(objects, seen, obj)

    for collection in bpy.data.collections:
        if not _asset_name_from_collection(collection):
            continue
        for obj in _collection_objects_recursive(collection):
            _add_freestyle_candidate(objects, seen, obj)

    for obj in bpy.data.objects:
        _add_freestyle_candidate(objects, seen, obj)

    return objects


def _set_edge_freestyle_mark(edge, enabled):
    if hasattr(edge, "use_freestyle_mark"):
        edge.use_freestyle_mark = enabled
        return True
    return False


def _freestyle_edge_attribute(mesh):
    attributes = getattr(mesh, "attributes", None)
    if attributes is None:
        return None

    attribute = attributes.get("freestyle_edge")
    if attribute is not None:
        return attribute

    try:
        return attributes.new("freestyle_edge", "BOOLEAN", "EDGE")
    except Exception:
        return None


def _mark_freestyle_edges(objects, enabled=True):
    marked = 0
    changed_objects = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        attribute = _freestyle_edge_attribute(obj.data)
        object_marked = 0
        if attribute is not None:
            for item in attribute.data:
                item.value = enabled
                object_marked += 1
        else:
            for edge in obj.data.edges:
                if _set_edge_freestyle_mark(edge, enabled):
                    object_marked += 1
        if object_marked:
            obj.data.update()
            changed_objects += 1
            marked += object_marked
    return marked, changed_objects


def _apply_render_engine(scene, settings, freestyle=False):
    if settings.render_engine == "CYCLES" and not freestyle:
        scene.render.engine = "CYCLES"
        if hasattr(scene, "cycles"):
            scene.cycles.samples = settings.max_samples
        return

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"

    eevee = getattr(scene, "eevee", None)
    if eevee is not None and hasattr(eevee, "taa_render_samples"):
        eevee.taa_render_samples = settings.max_samples


def _snapshot_visibility():
    return {
        "render": {
            "film_transparent": bpy.context.scene.render.film_transparent,
            "engine": bpy.context.scene.render.engine,
            "use_freestyle": bpy.context.scene.render.use_freestyle,
            "line_thickness_mode": bpy.context.scene.render.line_thickness_mode,
            "line_thickness": bpy.context.scene.render.line_thickness,
            "filepath": bpy.context.scene.render.filepath,
            "use_overwrite": bpy.context.scene.render.use_overwrite,
            "file_format": bpy.context.scene.render.image_settings.file_format,
            "color_mode": bpy.context.scene.render.image_settings.color_mode,
            "use_compositing": getattr(bpy.context.scene.render, "use_compositing", None),
        },
        "freestyle": _snapshot_freestyle_settings(bpy.context.view_layer),
        "collections": {
            collection.name: (collection.hide_render, collection.hide_viewport)
            for collection in bpy.data.collections
        },
        "layer_collections": {
            layer_collection.collection.name: (layer_collection.exclude, layer_collection.hide_viewport)
            for layer_collection in _layer_collections_recursive(bpy.context.view_layer.layer_collection)
        },
        "objects": {
            obj.name: (obj.hide_render, obj.hide_viewport)
            for obj in bpy.data.objects
        },
    }


def _restore_visibility(snapshot):
    render_settings = snapshot.get("render", {})
    if "film_transparent" in render_settings:
        bpy.context.scene.render.film_transparent = render_settings["film_transparent"]
    if "engine" in render_settings:
        bpy.context.scene.render.engine = render_settings["engine"]
    if "use_freestyle" in render_settings:
        bpy.context.scene.render.use_freestyle = render_settings["use_freestyle"]
    if "line_thickness_mode" in render_settings:
        bpy.context.scene.render.line_thickness_mode = render_settings["line_thickness_mode"]
    if "line_thickness" in render_settings:
        bpy.context.scene.render.line_thickness = render_settings["line_thickness"]
    if "filepath" in render_settings:
        bpy.context.scene.render.filepath = render_settings["filepath"]
    if "use_overwrite" in render_settings:
        bpy.context.scene.render.use_overwrite = render_settings["use_overwrite"]
    if "file_format" in render_settings:
        bpy.context.scene.render.image_settings.file_format = render_settings["file_format"]
    if "color_mode" in render_settings:
        bpy.context.scene.render.image_settings.color_mode = render_settings["color_mode"]
    if render_settings.get("use_compositing") is not None and hasattr(bpy.context.scene.render, "use_compositing"):
        bpy.context.scene.render.use_compositing = render_settings["use_compositing"]

    _restore_freestyle_settings(bpy.context.view_layer, snapshot.get("freestyle", {}))

    for name, values in snapshot.get("collections", {}).items():
        collection = bpy.data.collections.get(name)
        if collection is None:
            continue
        collection.hide_render, collection.hide_viewport = values

    layer_collections = {
        layer_collection.collection.name: layer_collection
        for layer_collection in _layer_collections_recursive(bpy.context.view_layer.layer_collection)
    }
    for name, values in snapshot.get("layer_collections", {}).items():
        layer_collection = layer_collections.get(name)
        if layer_collection is None:
            continue
        layer_collection.exclude, layer_collection.hide_viewport = values

    for name, values in snapshot.get("objects", {}).items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.hide_render, obj.hide_viewport = values


def _layer_collections_recursive(layer_collection):
    items = [layer_collection]
    for child in layer_collection.children:
        items.extend(_layer_collections_recursive(child))
    return items


def _active_lineset(view_layer, create=False):
    freestyle = getattr(view_layer, "freestyle_settings", None)
    if freestyle is None:
        return None
    linesets = getattr(freestyle, "linesets", None)
    if linesets is None:
        return None
    lineset = getattr(linesets, "active", None)
    if lineset is None and create:
        try:
            bpy.ops.scene.freestyle_lineset_add()
            lineset = getattr(linesets, "active", None)
        except Exception:
            lineset = None
    return lineset


def _snapshot_freestyle_settings(view_layer):
    freestyle = getattr(view_layer, "freestyle_settings", None)
    lineset = _active_lineset(view_layer)
    linestyle = getattr(lineset, "linestyle", None) if lineset is not None else None
    return {
        "use_freestyle": getattr(view_layer, "use_freestyle", False),
        "mode": getattr(freestyle, "mode", None),
        "as_render_pass": getattr(freestyle, "as_render_pass", None),
        "use_view_map_cache": getattr(freestyle, "use_view_map_cache", None),
        "crease_angle": getattr(freestyle, "crease_angle", None),
        "use_culling": getattr(freestyle, "use_culling", None),
        "use_smoothness": getattr(freestyle, "use_smoothness", None),
        "sphere_radius": getattr(freestyle, "sphere_radius", None),
        "kr_derivative_epsilon": getattr(freestyle, "kr_derivative_epsilon", None),
        "lineset": _snapshot_lineset(lineset),
        "linestyle": _snapshot_linestyle(linestyle),
    }


def _restore_freestyle_settings(view_layer, snapshot):
    if not snapshot:
        return

    freestyle = getattr(view_layer, "freestyle_settings", None)
    if hasattr(view_layer, "use_freestyle"):
        view_layer.use_freestyle = snapshot.get("use_freestyle", view_layer.use_freestyle)
    if freestyle is not None:
        for name in (
            "mode",
            "as_render_pass",
            "use_view_map_cache",
            "crease_angle",
            "use_culling",
            "use_smoothness",
            "sphere_radius",
            "kr_derivative_epsilon",
        ):
            value = snapshot.get(name, None)
            if value is not None and hasattr(freestyle, name):
                setattr(freestyle, name, value)

    lineset = _active_lineset(view_layer, bool(snapshot.get("lineset")))
    _restore_lineset(lineset, snapshot.get("lineset", {}))
    linestyle = getattr(lineset, "linestyle", None) if lineset is not None else None
    _restore_linestyle(linestyle, snapshot.get("linestyle", {}))


def _snapshot_lineset(lineset):
    if lineset is None:
        return {}
    names = (
        "select_by_visibility",
        "visibility",
        "select_by_edge_types",
        "edge_type_negation",
        "edge_type_combination",
        "select_silhouette",
        "select_crease",
        "select_border",
        "select_edge_mark",
        "select_contour",
        "select_external_contour",
        "select_material_boundary",
        "select_suggestive_contour",
        "select_ridge_valley",
        "exclude_silhouette",
        "exclude_crease",
        "exclude_border",
        "exclude_edge_mark",
        "exclude_contour",
        "exclude_external_contour",
        "exclude_material_boundary",
        "exclude_suggestive_contour",
        "exclude_ridge_valley",
        "select_by_image_border",
        "select_by_face_marks",
        "select_by_collection",
    )
    return {
        name: getattr(lineset, name)
        for name in names
        if hasattr(lineset, name)
    }


def _restore_lineset(lineset, snapshot):
    if lineset is None:
        return
    for name, value in snapshot.items():
        if hasattr(lineset, name):
            setattr(lineset, name, value)


def _snapshot_linestyle(linestyle):
    if linestyle is None:
        return {}
    snapshot = {}
    for name in ("color", "alpha", "thickness"):
        if hasattr(linestyle, name):
            value = getattr(linestyle, name)
            snapshot[name] = tuple(value) if name == "color" else value
    return snapshot


def _restore_linestyle(linestyle, snapshot):
    if linestyle is None:
        return
    for name, value in snapshot.items():
        if hasattr(linestyle, name):
            setattr(linestyle, name, value)


def _set_if_present(data, name, value):
    if hasattr(data, name):
        setattr(data, name, value)


def _configure_freestyle(context, settings, as_render_pass):
    scene = context.scene
    view_layer = context.view_layer
    scene.render.use_freestyle = bool(settings.freestyle_edges)
    if not settings.freestyle_edges:
        return

    if hasattr(view_layer, "use_freestyle"):
        view_layer.use_freestyle = True

    scene.render.line_thickness_mode = "ABSOLUTE"
    scene.render.line_thickness = settings.freestyle_line_thickness

    freestyle = getattr(view_layer, "freestyle_settings", None)
    if freestyle is not None:
        _set_if_present(freestyle, "mode", "EDITOR")
        _set_if_present(freestyle, "as_render_pass", as_render_pass)
        _set_if_present(freestyle, "use_view_map_cache", False)
        _set_if_present(freestyle, "crease_angle", radians(134.0))
        _set_if_present(freestyle, "use_culling", False)
        _set_if_present(freestyle, "use_smoothness", False)
        _set_if_present(freestyle, "sphere_radius", 0.1)
        _set_if_present(freestyle, "kr_derivative_epsilon", 0.0)

    lineset = _active_lineset(view_layer, True)
    if lineset is None:
        return

    _set_if_present(lineset, "select_by_visibility", True)
    _set_if_present(lineset, "visibility", "VISIBLE")
    _set_if_present(lineset, "select_by_edge_types", True)
    _set_if_present(lineset, "edge_type_negation", "INCLUSIVE")
    _set_if_present(lineset, "edge_type_combination", "OR")
    _set_if_present(lineset, "select_by_image_border", False)
    _set_if_present(lineset, "select_by_face_marks", False)
    _set_if_present(lineset, "select_by_collection", False)

    for edge_type in (
        "silhouette",
        "crease",
        "border",
        "contour",
        "external_contour",
        "material_boundary",
        "suggestive_contour",
        "ridge_valley",
    ):
        _set_if_present(lineset, f"select_{edge_type}", False)
        _set_if_present(lineset, f"exclude_{edge_type}", False)

    _set_if_present(lineset, "select_edge_mark", True)
    _set_if_present(lineset, "exclude_edge_mark", False)

    linestyle = getattr(lineset, "linestyle", None)
    if linestyle is not None:
        color = settings.freestyle_line_color
        _set_if_present(linestyle, "color", color[:3])
        _set_if_present(linestyle, "alpha", color[3])
        _set_if_present(linestyle, "thickness", settings.freestyle_line_thickness)


def _disable_freestyle(context):
    context.scene.render.use_freestyle = False
    if hasattr(context.view_layer, "use_freestyle"):
        context.view_layer.use_freestyle = False


def _freestyle_pass_material():
    material = bpy.data.materials.get(TEMP_FREESTYLE_PASS_MATERIAL)
    if material is None:
        material = bpy.data.materials.new(TEMP_FREESTYLE_PASS_MATERIAL)
    material.diffuse_color = (0.0, 0.0, 0.0, 0.0)
    _set_if_present(material, "blend_method", "BLEND")
    _set_if_present(material, "surface_render_method", "BLENDED")
    _set_if_present(material, "show_transparent_back", True)
    _set_if_present(material, "use_transparent_shadow", False)

    try:
        material.use_nodes = True
        tree = material.node_tree
        tree.nodes.clear()
        output = tree.nodes.new("ShaderNodeOutputMaterial")
        transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
        tree.links.new(transparent.outputs["BSDF"], output.inputs["Surface"])
    except Exception:
        pass

    return material


def _render_freestyle_pass_image(context, settings, job):
    scene = context.scene
    view_layer = context.view_layer
    material_override = getattr(view_layer, "material_override", None)
    film_transparent = scene.render.film_transparent
    use_compositing = getattr(scene.render, "use_compositing", None)

    try:
        _configure_freestyle(context, settings, False)
        if hasattr(view_layer, "material_override"):
            view_layer.material_override = _freestyle_pass_material()
        scene.render.film_transparent = True
        if hasattr(scene.render, "use_compositing"):
            scene.render.use_compositing = False
        _configure_render(
            scene,
            settings,
            job,
            job.get("freestyle_output_path") or _freestyle_pass_path(job["output_path"]),
            "PNG",
            True,
        )
        bpy.ops.render.render(write_still=True)
    finally:
        if hasattr(view_layer, "material_override"):
            view_layer.material_override = material_override
        scene.render.film_transparent = film_transparent
        if use_compositing is not None and hasattr(scene.render, "use_compositing"):
            scene.render.use_compositing = use_compositing


def _render_freestyle_overlay_image(context, settings, job):
    scene = context.scene
    use_compositing = getattr(scene.render, "use_compositing", None)
    try:
        _configure_freestyle(context, settings, False)
        if hasattr(scene.render, "use_compositing"):
            scene.render.use_compositing = False
        _configure_render(
            scene,
            settings,
            job,
            job.get("freestyle_overlay_path") or _freestyle_overlay_path(job["output_path"]),
            "PNG",
            True,
        )
        bpy.ops.render.render(write_still=True)
    finally:
        if use_compositing is not None and hasattr(scene.render, "use_compositing"):
            scene.render.use_compositing = use_compositing


def _compositor_link_snapshot(tree, socket):
    links = []
    for link in list(socket.links):
        links.append(
            {
                "from_node": link.from_node.name,
                "from_socket": link.from_socket.name,
                "to_node": link.to_node.name,
                "to_socket": link.to_socket.name,
            },
        )
    return links


def _restore_compositor_links(tree, links):
    for item in links:
        from_node = tree.nodes.get(item["from_node"])
        to_node = tree.nodes.get(item["to_node"])
        if from_node is None or to_node is None:
            continue
        from_socket = from_node.outputs.get(item["from_socket"])
        to_socket = to_node.inputs.get(item["to_socket"])
        if from_socket is not None and to_socket is not None:
            tree.links.new(from_socket, to_socket)


def _compositor_output_node(tree):
    for node in tree.nodes:
        if node.bl_idname == "CompositorNodeComposite":
            return node, False

    node = tree.nodes.new("CompositorNodeComposite")
    node.name = TEMP_FREESTYLE_COMPOSITE_NODE
    node.label = "PolyGroups Freestyle Composite"
    return node, True


def _scene_compositor_tree(scene):
    tree = getattr(scene, "compositor_node_tree", None)
    if tree is not None:
        return tree
    return getattr(scene, "node_tree", None)


def _setup_freestyle_pass_compositor(scene):
    use_nodes = getattr(scene, "use_nodes", False)
    use_compositing = getattr(scene.render, "use_compositing", None)
    if hasattr(scene, "use_nodes"):
        scene.use_nodes = True
    if hasattr(scene.render, "use_compositing"):
        scene.render.use_compositing = True
    tree = _scene_compositor_tree(scene)
    if tree is None:
        if hasattr(scene, "use_nodes"):
            scene.use_nodes = use_nodes
        if use_compositing is not None and hasattr(scene.render, "use_compositing"):
            scene.render.use_compositing = use_compositing
        return None

    render_layers = tree.nodes.new("CompositorNodeRLayers")
    render_layers.name = TEMP_FREESTYLE_RENDER_LAYERS_NODE
    render_layers.label = "PolyGroups Freestyle Pass"
    composite, created_composite = _compositor_output_node(tree)
    image_socket = composite.inputs.get("Image")
    freestyle_socket = render_layers.outputs.get("Freestyle")
    if image_socket is None or freestyle_socket is None:
        tree.nodes.remove(render_layers)
        if created_composite:
            tree.nodes.remove(composite)
        if hasattr(scene, "use_nodes"):
            scene.use_nodes = use_nodes
        if use_compositing is not None and hasattr(scene.render, "use_compositing"):
            scene.render.use_compositing = use_compositing
        return None

    snapshot = {
        "use_nodes": use_nodes,
        "use_compositing": use_compositing,
        "composite_node": composite.name,
        "created_composite": created_composite,
        "render_layers_node": render_layers.name,
        "image_links": _compositor_link_snapshot(tree, image_socket),
    }
    for link in list(image_socket.links):
        tree.links.remove(link)
    tree.links.new(freestyle_socket, image_socket)
    return snapshot


def _restore_freestyle_pass_compositor(scene, snapshot):
    if snapshot is None:
        return

    tree = _scene_compositor_tree(scene)
    if tree is not None:
        composite = tree.nodes.get(snapshot.get("composite_node", ""))
        if composite is not None:
            image_socket = composite.inputs.get("Image")
            if image_socket is not None:
                for link in list(image_socket.links):
                    tree.links.remove(link)
                _restore_compositor_links(tree, snapshot.get("image_links", []))

        render_layers = tree.nodes.get(snapshot.get("render_layers_node", ""))
        if render_layers is not None:
            tree.nodes.remove(render_layers)
        if snapshot.get("created_composite") and composite is not None:
            tree.nodes.remove(composite)

    if hasattr(scene, "use_nodes"):
        scene.use_nodes = snapshot.get("use_nodes", scene.use_nodes)
    use_compositing = snapshot.get("use_compositing")
    if use_compositing is not None and hasattr(scene.render, "use_compositing"):
        scene.render.use_compositing = use_compositing


def _set_asset_collection_enabled(collection, enabled):
    collection.hide_render = not enabled
    collection.hide_viewport = not enabled

    for layer_collection in _layer_collections_recursive(bpy.context.view_layer.layer_collection):
        if layer_collection.collection != collection:
            continue
        layer_collection.exclude = not enabled
        layer_collection.hide_viewport = not enabled


def _set_collection_enabled(collection, enabled):
    collection.hide_render = not enabled
    collection.hide_viewport = not enabled

    for layer_collection in _layer_collections_recursive(bpy.context.view_layer.layer_collection):
        if layer_collection.collection != collection:
            continue
        layer_collection.exclude = not enabled
        layer_collection.hide_viewport = not enabled


def _prepare_transparent_background(settings):
    if not settings.transparent_background:
        return

    bpy.context.scene.render.film_transparent = True
    for collection in bpy.data.collections:
        if _scene_collection_matches(collection, settings):
            _set_collection_enabled(collection, False)


def _multiview_collection(parent_collection, asset_name):
    collection_name = f"{_clean_name(asset_name)}{MULTIVIEW_COLLECTION_SUFFIX}"
    collection = parent_collection.children.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            collection = bpy.data.collections.new(collection_name)
        if parent_collection.children.get(collection.name) is None:
            parent_collection.children.link(collection)
    return collection


def _create_multiview_duplicate(source, collection, name, x_offset, z_rotation_degrees):
    duplicate = source.copy()
    duplicate.name = name
    duplicate.data = source.data
    duplicate.animation_data_clear()
    duplicate.location.x += x_offset
    duplicate.rotation_euler.rotate_axis("Z", radians(z_rotation_degrees))
    duplicate.hide_render = False
    duplicate.hide_viewport = False
    duplicate[MULTIVIEW_PROP] = True
    collection.objects.link(duplicate)
    return duplicate


def _create_multiview_setup(job):
    source = bpy.data.objects.get(job.get("object", ""))
    parent_collection = bpy.data.collections.get(job.get("collection", ""))
    if source is None or parent_collection is None:
        return []

    settings = bpy.context.scene.polygroups_render_settings
    asset_name = job.get("asset_name", "") or _asset_name_from_collection(parent_collection)
    collection = _multiview_collection(parent_collection, asset_name)
    offset = settings.multiview_offset
    base_name = _clean_name(_base_name(source.name))
    duplicates = [
        _create_multiview_duplicate(
            source,
            collection,
            f"{base_name}_MV_Back",
            -offset,
            180.0,
        ),
        _create_multiview_duplicate(
            source,
            collection,
            f"{base_name}_MV_Side",
            offset,
            90.0,
        ),
    ]

    _set_collection_enabled(collection, True)
    return duplicates


def _remove_multiview_objects(objects):
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)


def _clear_multiview_setups():
    removed_objects = 0
    for obj in list(bpy.data.objects):
        if not obj.get(MULTIVIEW_PROP):
            continue
        bpy.data.objects.remove(obj, do_unlink=True)
        removed_objects += 1

    removed_collections = 0
    for collection in list(bpy.data.collections):
        if (
            not _base_name(collection.name).endswith(MULTIVIEW_COLLECTION_SUFFIX)
            or collection.objects
            or collection.children
        ):
            continue
        bpy.data.collections.remove(collection)
        removed_collections += 1

    return removed_objects, removed_collections


def _prepare_scene_for_job(job):
    queue_collections = [
        collection
        for collection in bpy.data.collections
        if _asset_name_from_collection(collection)
    ]
    current_collection = bpy.data.collections.get(job["collection"])
    current_object = bpy.data.objects.get(job["object"])
    if current_collection is None or current_object is None:
        return False

    for collection in queue_collections:
        is_current = collection == current_collection
        _set_asset_collection_enabled(collection, is_current)

    for obj in _collection_objects_recursive(current_collection):
        is_current = obj == current_object
        obj.hide_render = not is_current
        obj.hide_viewport = not is_current

    _prepare_transparent_background(bpy.context.scene.polygroups_render_settings)
    return True


def _finish_render_job(job, multiview_objects=None):
    _remove_multiview_objects(multiview_objects or [])
    _clear_multiview_setups()
    collection = bpy.data.collections.get(job.get("collection", ""))
    if collection is not None:
        _set_asset_collection_enabled(collection, False)


def _configure_render(scene, settings, job, filepath=None, file_format="PNG", freestyle=False):
    _apply_render_engine(scene, settings, freestyle)
    scene.render.resolution_x = settings.resolution_x
    scene.render.resolution_y = settings.resolution_y
    scene.render.use_file_extension = True
    scene.render.image_settings.file_format = file_format
    if file_format == "PNG" and (settings.transparent_background or freestyle):
        scene.render.image_settings.color_mode = "RGBA"
    scene.render.use_overwrite = settings.overwrite_existing
    output_path = filepath or job["output_path"]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    scene.render.filepath = output_path


def _render_current_job(context, settings, job):
    if settings.freestyle_edges and settings.freestyle_as_render_pass:
        _disable_freestyle(context)
        _configure_render(context.scene, settings, job, job["output_path"], "PNG")
        bpy.ops.render.render(write_still=True)

        _configure_freestyle(context, settings, True)
        compositor_snapshot = _setup_freestyle_pass_compositor(context.scene)
        if compositor_snapshot is None:
            _render_freestyle_pass_image(context, settings, job)
            _render_freestyle_overlay_image(context, settings, job)
            return
        try:
            freestyle_output_path = job.get("freestyle_output_path") or _freestyle_pass_path(job["output_path"])
            _configure_render(
                context.scene,
                settings,
                job,
                freestyle_output_path,
                "PNG",
                True,
            )
            bpy.ops.render.render(write_still=True)
        finally:
            _restore_freestyle_pass_compositor(context.scene, compositor_snapshot)
        _render_freestyle_overlay_image(context, settings, job)
        return

    _configure_freestyle(context, settings, False)
    _configure_render(
        context.scene,
        settings,
        job,
        job["output_path"],
        "PNG",
        settings.freestyle_edges,
    )
    bpy.ops.render.render(write_still=True)


class OBJECT_OT_polygroups_scan_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_scan_render_queue"
    bl_label = "Scan Render Queue"
    bl_description = "Scan *_Collection asset collections and prepare LOW/MID render jobs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        _normalize_render_output_setting(settings)
        queue, collection_count = _scan_render_queue(settings)
        settings.queue_index = 0
        settings.current_collection = ""
        settings.current_object = ""
        settings.last_output_path = ""
        settings.stop_requested = False
        _store_queue(settings, queue, collection_count)
        settings.status = f"Queued {settings.total_count} render job(s) from {collection_count} collection(s)"
        return {"FINISHED"}


class OBJECT_OT_polygroups_start_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_start_render_queue"
    bl_label = "Start Render Queue"
    bl_description = "Render queued LOW/MID asset previews one job at a time"
    bl_options = {"REGISTER", "UNDO"}

    continue_from_current: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    _timer = None
    _visibility_snapshot = None

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_render_settings
        return not settings.is_running

    def invoke(self, context, event):
        del event
        settings = context.scene.polygroups_render_settings
        _normalize_render_output_setting(settings)
        if not self.continue_from_current:
            queue, collection_count = _scan_render_queue(settings)
            settings.queue_index = 0
            _store_queue(settings, queue, collection_count)
        else:
            queue = _load_queue(settings)
            if not queue or settings.queue_index >= len(queue):
                queue, collection_count = _scan_render_queue(settings)
                settings.queue_index = 0
                _store_queue(settings, queue, collection_count)

        if settings.total_count == 0:
            settings.status = "Render queue is empty"
            return {"CANCELLED"}

        if settings.freestyle_edges:
            marked_edges, marked_objects = _mark_freestyle_edges(_queue_objects(_load_queue(settings)), True)
            settings.status = f"Marked {marked_edges} Freestyle edge(s) on {marked_objects} object(s)"

        settings.is_running = True
        settings.stop_requested = False
        if not settings.freestyle_edges:
            settings.status = "Render queue running"
        self._visibility_snapshot = _snapshot_visibility()
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def modal(self, context, event):
        settings = context.scene.polygroups_render_settings
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if settings.stop_requested:
            self._finish(context, "Render queue stopped")
            return {"CANCELLED"}

        queue = _load_queue(settings)
        if settings.queue_index >= len(queue):
            self._finish(context, "Render queue complete")
            return {"FINISHED"}

        job = queue[settings.queue_index]
        if settings.skip_existing and not settings.overwrite_existing and os.path.exists(job.get("output_path", "")):
            settings.queue_index += 1
            _sync_progress(settings)
            return {"RUNNING_MODAL"}

        if not _prepare_scene_for_job(job):
            settings.queue_index += 1
            _sync_progress(settings)
            settings.status = f"Skipped missing render job {settings.queue_index}"
            return {"RUNNING_MODAL"}

        settings.current_collection = job.get("collection", "")
        settings.current_object = job.get("object", "")
        settings.last_output_path = job.get("output_path", "")
        settings.status = f"Rendering {settings.current_object}"
        multiview_objects = _create_multiview_setup(job) if settings.multiview_render else []
        try:
            _render_current_job(context, settings, job)
        except Exception as error:
            _finish_render_job(job, multiview_objects)
            self._finish(context, f"Render failed: {error}")
            self.report({"ERROR"}, f"Render failed: {error}")
            return {"CANCELLED"}
        finally:
            if settings.is_running:
                _finish_render_job(job, multiview_objects)

        settings.queue_index += 1
        _sync_progress(settings)
        settings.status = f"Rendered {settings.rendered_count} of {settings.total_count}"
        return {"RUNNING_MODAL"}

    def _finish(self, context, status):
        settings = context.scene.polygroups_render_settings
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        if self._visibility_snapshot is not None:
            _restore_visibility(self._visibility_snapshot)
            self._visibility_snapshot = None
        settings.is_running = False
        settings.stop_requested = False
        _sync_progress(settings)
        settings.status = status


class OBJECT_OT_polygroups_stop_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_stop_render_queue"
    bl_label = "Stop Render Queue"
    bl_description = "Stop the render queue after the current render finishes"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        settings.stop_requested = True
        settings.status = "Stop requested"
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_multiview_render(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_multiview_render"
    bl_label = "Clear Multi View"
    bl_description = "Remove temporary multi view render duplicates and empty multi view collections"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        del context
        removed_objects, removed_collections = _clear_multiview_setups()
        self.report(
            {"INFO"},
            f"Cleared {removed_objects} multi view object(s) and {removed_collections} collection(s)",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_mark_freestyle_edges(bpy.types.Operator):
    bl_idname = "object.polygroups_mark_freestyle_edges"
    bl_label = "Mark Freestyle Edges"
    bl_description = "Mark all LOW/MID asset mesh edges for Freestyle rendering"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        marked_edges, marked_objects = _mark_freestyle_edges(_asset_mesh_objects(settings), True)
        self.report(
            {"INFO"},
            f"Marked {marked_edges} Freestyle edge(s) on {marked_objects} object(s)",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_freestyle_edges(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_freestyle_edges"
    bl_label = "Clear Freestyle"
    bl_description = "Clear Freestyle edge marks from LOW/MID asset meshes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        cleared_edges, cleared_objects = _mark_freestyle_edges(_asset_mesh_objects(settings), False)
        self.report(
            {"INFO"},
            f"Cleared {cleared_edges} Freestyle edge mark(s) on {cleared_objects} object(s)",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_continue_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_continue_render_queue"
    bl_label = "Continue Render Queue"
    bl_description = "Continue the render queue from the current saved job"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return bpy.ops.object.polygroups_start_render_queue("INVOKE_DEFAULT", continue_from_current=True)
