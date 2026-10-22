import json
import os
import re
from datetime import datetime
from math import radians

import bpy

from .render_textures import PLANE_TAG, texture_planes
from ..sound import play_operation_done_sound
from ..core.remesh_cursor import RemeshCursor, update_remesh_cursor


def is_render_support_collection(scene, collection):
    """Recognize studio collections without matching the Scene Collection root."""
    if collection == scene.collection:
        return False
    if collection.get('polygroups_studio_role') in {'scene', 'camera', 'light'}:
        return True
    return re.match(r'^(scene|camera|light)(?:$|[_ .-])', collection.name, re.IGNORECASE) is not None


def ensure_render_support_visible(context):
    """Enable studio collections and their parent layer paths before rendering."""
    scene = context.scene
    needed = set()
    objects = set()
    def visit(collection, parents=(), inside=False):
        named = is_render_support_collection(scene, collection)
        inside = inside or named
        support = {obj for obj in collection.objects
                   if obj.type in {'CAMERA', 'LIGHT'} or obj.get('polygroups_studio_role')}
        if inside or support:
            needed.update((*parents, collection))
            # Ancestors and mixed camera/light collections only need their
            # collection paths enabled; their unrelated meshes stay hidden.
            objects.update(collection.objects if inside else support)
        for child in collection.children:
            visit(child, (*parents, collection), inside)
    visit(scene.collection)
    for col in needed:
        col.hide_viewport = col.hide_render = col.hide_select = False
    layers = []
    def remember(layer):
        layers.append((layer, layer.exclude, layer.hide_viewport))
        for child in layer.children:
            remember(child)
    for view_layer in scene.view_layers:
        remember(view_layer.layer_collection)
    # Setting exclude on an ancestor can propagate to its descendants in
    # Blender. Restore unrelated layer states after enabling each parent.
    for layer, excluded, hidden in layers:
        desired = False if layer.collection in needed else excluded
        if layer.exclude != desired:
            layer.exclude = desired
        layer.hide_viewport = False if layer.collection in needed else hidden
    context.view_layer.update()
    for obj in objects:
        obj.hide_viewport = obj.hide_render = obj.hide_select = False
        for view_layer in scene.view_layers:
            if obj.name in view_layer.objects:
                obj.hide_set(False, view_layer=view_layer)


class RenderQueueCursor(RemeshCursor):
    def __init__(self, context):
        super().__init__(context)
        self.primary_in_corner = True
        self.status_line = "Render"

    def draw(self):
        settings = bpy.context.scene.polygroups_render_settings
        if not settings.is_running:
            return
        total = settings.total_count
        completed = min(settings.queue_index, total)
        self.label = f"Готово {completed} из {total} —"
        self.percent = 100 * completed / total if total else 0
        super().draw()


ASSET_COLLECTION_SUFFIX = "_Collection"
ASSET_RENDER_SUFFIXES = ("LOW", "MID", "HIGH", "LOD0", "LOD1", "LOD2", "LOD3", "LOD4", "LOD5")
BLENDER_NUMERIC_SUFFIX_RE = re.compile(r"\.\d{3}$")
MULTIVIEW_PROP = "polygroups_render_multiview"
MULTIVIEW_SOURCE_PROP = "polygroups_multiview_source"
MULTIVIEW_PREPARED_PROP = "polygroups_multiview_prepared"
MULTIVIEW_SOURCE_RENDER_PROP = "polygroups_multiview_source_hide_render"
MULTIVIEW_SOURCE_VIEWPORT_PROP = "polygroups_multiview_source_hide_viewport"
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
    directory = (settings.output_directory or "//!Renders").strip() or "//!Renders"
    if directory.startswith("//"):
        return bpy.path.abspath(directory)
    if os.path.isabs(directory):
        return bpy.path.abspath(directory)
    return os.path.join(bpy.path.abspath("//"), directory)


def _normalize_render_output_setting(settings):
    directory = (settings.output_directory or "").strip()
    if directory != settings.output_directory:
        settings.output_directory = directory


def _freestyle_pass_path(output_path):
    root, _ = os.path.splitext(output_path)
    return f"{root}_freestyle_pass.png"


def _freestyle_overlay_path(output_path):
    root, _ = os.path.splitext(output_path)
    return f"{root}_freestyle_overlay.png"


def _transparent_output_path(output_path):
    root, extension = os.path.splitext(output_path)
    if extension.lower() in {'.jpg', '.jpeg'}:
        extension = '.png'
    return f"{root}_transparent{extension}"


def image_extension(file_format):
    return {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}[file_format]


def _current_state_render_path():
    base_directory = os.path.join(bpy.path.abspath("//"), "!Renders")
    os.makedirs(base_directory, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    extension = image_extension(bpy.context.scene.polygroups_render_settings.image_format)
    base_path = os.path.join(base_directory, f"Render_Image_{timestamp}{extension}")
    if not os.path.exists(base_path):
        return base_path

    root, extension = os.path.splitext(base_path)
    index = 1
    while True:
        output_path = f"{root}_{index:03d}{extension}"
        if not os.path.exists(output_path):
            return output_path
        index += 1


def _render_suffix_from_name(name):
    upper_name = _base_name(name).upper()
    for suffix in ASSET_RENDER_SUFFIXES:
        if upper_name.endswith(f"_{suffix}"):
            return suffix
    return ""


def _find_asset_objects(collection, asset_name, settings):
    include_suffixes = set()
    if settings.render_low and not settings.render_lod_enabled:
        include_suffixes.add("LOW")
    if settings.render_mid:
        include_suffixes.add("MID")
    if settings.render_high:
        include_suffixes.add("HIGH")
    if settings.render_lod_enabled:
        include_suffixes.add(settings.render_lod_level)

    objects_by_suffix = {}
    for obj in _collection_objects_recursive(collection):
        if obj.type != "MESH" or obj.get(PLANE_TAG):
            continue
        if obj.get(MULTIVIEW_PROP):
            continue
        suffix = _render_object_suffix(obj)
        if suffix not in include_suffixes:
            continue
        objects_by_suffix.setdefault(suffix, obj)

    return [objects_by_suffix[suffix] for suffix in ASSET_RENDER_SUFFIXES if suffix in objects_by_suffix]


def _render_object_suffix(obj):
    suffix = _render_suffix_from_name(obj.name)
    if not suffix and obj.get('unreal_lod_asset') and obj.get('unreal_lod_index') == -1:
        return 'HIGH'  # User-editable High suffix from Unreal LOD Rename.
    return suffix


def _scan_render_queue(settings):
    base_directory = _render_output_base_directory(settings)
    queue = []
    collection_names = set()
    collection_index = 0

    for collection in bpy.data.collections:
        asset_name = _asset_name_from_collection(collection)
        if not asset_name:
            continue

        collection_names.add(collection.name)
        objects = _find_asset_objects(collection, asset_name, settings)
        planes = texture_planes(collection)
        if not objects and not planes:
            continue

        # Number only collections with render jobs. LOW and MID of the same
        # asset share an index, independent of the enabled render variants.
        collection_index += 1
        asset_directory = os.path.join(base_directory, f"Collection_{collection_index:02d}")
        for obj in objects:
            suffix = _render_object_suffix(obj)
            output_suffix = 'LOW' if suffix.startswith('LOD') else suffix
            use_multiview = settings.multiview_render or bool(_prepared_multiview_views(obj))
            modes = ["Multiview"] if use_multiview else [""]
            if use_multiview and settings.multiview_render_hero:
                modes.append("Hero")
            for mode in modes:
                prefix = f"Image_{mode}" if mode else "Image"
                output_path = os.path.join(asset_directory, f"{prefix}_{collection_index:02d}_{output_suffix}{image_extension(settings.image_format)}")
                queue.append(
                    {
                        "asset_name": asset_name,
                        "collection": collection.name,
                        "object": obj.name,
                        "variant": suffix,
                        "output_variant": output_suffix,
                        "view_mode": mode,
                        "output_path": output_path,
                        "transparent_output_path": _transparent_output_path(output_path),
                        "freestyle_output_path": _freestyle_pass_path(output_path),
                        "freestyle_overlay_path": _freestyle_overlay_path(output_path),
                    },
                )

        if settings.texture_render_mode in {"SEPARATE", "BOTH"}:
            for plane in sorted(planes, key=lambda obj: obj.get(PLANE_TAG)):
                kind = plane[PLANE_TAG]
                queue.append({
                    "asset_name": asset_name, "collection": collection.name,
                    "object": plane.name, "variant": kind, "texture_kind": kind,
                    "output_path": os.path.join(asset_directory, f"Image_Texture_{collection_index:02d}_{kind}.png"),
                })
        if settings.texture_render_mode in {"COMBINED", "BOTH"}:
            pair = {plane[PLANE_TAG]: plane for plane in planes}
            if "BaseColor" in pair and "Normal" in pair:
                queue.append({
                    "asset_name": asset_name, "collection": collection.name,
                    "object": pair["BaseColor"].name,
                    "texture_objects": [pair["BaseColor"].name, pair["Normal"].name],
                    "variant": "BaseColor_Normal", "texture_kind": "Combined",
                    "output_path": os.path.join(asset_directory, f"Image_Texture_{collection_index:02d}_BaseColor_Normal.png"),
                })

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


def _ensure_render_job_directories(queue):
    for directory in {os.path.dirname(job["output_path"]) for job in queue}:
        os.makedirs(directory, exist_ok=True)


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
        if job.get("texture_kind"):
            continue
        obj = bpy.data.objects.get(job.get("object", ""))
        if obj is None or obj.type != "MESH" or obj.name in seen:
            continue
        seen.add(obj.name)
        objects.append(obj)
    return objects


def _add_freestyle_candidate(objects, seen, obj):
    if obj is None or obj.type != "MESH" or obj.name in seen:
        return
    if not _render_object_suffix(obj):
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
            "resolution_percentage": bpy.context.scene.render.resolution_percentage,
            "filepath": bpy.context.scene.render.filepath,
            "use_overwrite": bpy.context.scene.render.use_overwrite,
            "file_format": bpy.context.scene.render.image_settings.file_format,
            "media_type": bpy.context.scene.render.image_settings.media_type,
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
    if "resolution_percentage" in render_settings:
        bpy.context.scene.render.resolution_percentage = render_settings["resolution_percentage"]
    if "filepath" in render_settings:
        bpy.context.scene.render.filepath = render_settings["filepath"]
    if "use_overwrite" in render_settings:
        bpy.context.scene.render.use_overwrite = render_settings["use_overwrite"]
    if "file_format" in render_settings:
        bpy.context.scene.render.image_settings.media_type = render_settings.get('media_type', 'IMAGE')
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


def _create_multiview_duplicate(source, collection, name, x_offset, z_rotation_degrees,
                                prepared=False):
    duplicate = source.copy()
    duplicate.name = name
    duplicate.data = source.data
    duplicate.animation_data_clear()
    duplicate.location.x += x_offset
    duplicate.rotation_euler.rotate_axis("Z", radians(z_rotation_degrees))
    duplicate.hide_render = False
    duplicate.hide_viewport = False
    duplicate[MULTIVIEW_PROP] = True
    duplicate[MULTIVIEW_SOURCE_PROP] = source.name
    duplicate[MULTIVIEW_PREPARED_PROP] = prepared
    collection.objects.link(duplicate)
    return duplicate


def _multiview_views(source, parent_collection, asset_name, settings, prepared=False):
    collection = _multiview_collection(parent_collection, asset_name)
    offset = settings.multiview_offset
    angle = float(settings.multiview_angle)
    base_name = _clean_name(_base_name(source.name))
    views = [
        _create_multiview_duplicate(source, collection, f"{base_name}_MV_Front",
                                    0.0, angle, prepared),
        _create_multiview_duplicate(source, collection, f"{base_name}_MV_Back",
                                    -offset, 180.0 + angle, prepared),
        _create_multiview_duplicate(source, collection, f"{base_name}_MV_Side",
                                    offset, 90.0 + angle, prepared),
    ]
    source.hide_render = True
    source.hide_viewport = True
    _set_collection_enabled(collection, True)
    return views


def _prepared_multiview_views(source):
    views = [obj for obj in bpy.data.objects
             if obj.get(MULTIVIEW_PROP) and obj.get(MULTIVIEW_PREPARED_PROP)
             and obj.get(MULTIVIEW_SOURCE_PROP) == source.name]
    return views if len(views) == 3 else []


def _create_multiview_setup(job):
    source = bpy.data.objects.get(job.get("object", ""))
    parent_collection = bpy.data.collections.get(job.get("collection", ""))
    if source is None or parent_collection is None:
        return []

    settings = bpy.context.scene.polygroups_render_settings
    asset_name = job.get("asset_name", "") or _asset_name_from_collection(parent_collection)
    prepared = _prepared_multiview_views(source)
    if prepared:
        source.hide_render = True
        source.hide_viewport = True
        for obj in prepared:
            obj.hide_render = False
            obj.hide_viewport = False
            for collection in obj.users_collection:
                _set_collection_enabled(collection, True)
        return []
    return _multiview_views(source, parent_collection, asset_name, settings)


def _isolate_hero_view(source, temporary_views):
    """Keep the centered front view with the configured +/-30 degree angle."""
    views = temporary_views or _prepared_multiview_views(source)
    for obj in views:
        is_front = _base_name(obj.name).endswith("_MV_Front")
        obj.hide_render = not is_front
        obj.hide_viewport = not is_front


def _remove_multiview_objects(objects):
    for obj in objects:
        if obj.name in bpy.data.objects:
            source = bpy.data.objects.get(obj.get(MULTIVIEW_SOURCE_PROP, ""))
            bpy.data.objects.remove(obj, do_unlink=True)
            if source is not None:
                source.hide_render = False
                source.hide_viewport = False
    for collection in list(bpy.data.collections):
        if (_base_name(collection.name).endswith(MULTIVIEW_COLLECTION_SUFFIX)
                and not collection.objects and not collection.children):
            bpy.data.collections.remove(collection)


def _clear_multiview_setups():
    for source in bpy.data.objects:
        if MULTIVIEW_SOURCE_RENDER_PROP in source:
            source.hide_render = bool(source[MULTIVIEW_SOURCE_RENDER_PROP])
            source.hide_viewport = bool(source.get(MULTIVIEW_SOURCE_VIEWPORT_PROP, False))
            del source[MULTIVIEW_SOURCE_RENDER_PROP]
            if MULTIVIEW_SOURCE_VIEWPORT_PROP in source:
                del source[MULTIVIEW_SOURCE_VIEWPORT_PROP]
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
    # Texture previews must never leak into mesh, Hero or Multiview renders.
    for plane in texture_planes():
        plane.hide_render = True
        plane.hide_viewport = True
    queue_collections = [
        collection
        for collection in bpy.data.collections
        if _asset_name_from_collection(collection)
    ]
    current_collection = bpy.data.collections.get(job["collection"])
    current_object = bpy.data.objects.get(job["object"])
    if current_collection is None or current_object is None:
        return False

    ensure_render_support_visible(bpy.context)
    for collection in queue_collections:
        is_current = collection == current_collection
        _set_asset_collection_enabled(collection, is_current)

    for obj in _collection_objects_recursive(current_collection):
        is_current = obj == current_object or obj.name in job.get("texture_objects", [])
        obj.hide_render = not is_current
        obj.hide_viewport = not is_current

    # Also isolate unrelated meshes outside the scanned asset collections.
    support = set()
    def collect_support(collection, inside=False):
        inside = inside or is_render_support_collection(bpy.context.scene, collection)
        if inside:
            support.update(collection.objects)
        for child in collection.children:
            collect_support(child, inside)
    collect_support(bpy.context.scene.collection)
    visible = {current_object.name, *job.get('texture_objects', [])}
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj not in support:
            obj.hide_render = obj.hide_viewport = obj.name not in visible
    bpy.context.view_layer.update()
    return True


def _finish_render_job(job, multiview_objects=None):
    _remove_multiview_objects(multiview_objects or [])
    collection = bpy.data.collections.get(job.get("collection", ""))
    if collection is not None:
        _set_asset_collection_enabled(collection, False)


def _configure_render(scene, settings, job, filepath=None, file_format=None, freestyle=False):
    file_format = file_format or settings.image_format
    _apply_render_engine(scene, settings, freestyle)
    scene.render.resolution_x = settings.resolution_x
    scene.render.resolution_y = settings.resolution_y
    scene.render.resolution_percentage = settings.resolution_scale
    scene.render.use_file_extension = True
    scene.render.image_settings.media_type = 'IMAGE'
    scene.render.image_settings.file_format = file_format
    if file_format in {"PNG", "WEBP"}:
        scene.render.image_settings.color_mode = "RGBA" if scene.render.film_transparent or freestyle else "RGB"
    else:
        scene.render.image_settings.color_mode = "RGB"
    scene.render.use_overwrite = settings.overwrite_existing
    output_path = filepath or job["output_path"]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    scene.render.filepath = output_path


class OBJECT_OT_polygroups_render_current_state(bpy.types.Operator):
    bl_idname = "object.polygroups_render_current_state"
    bl_label = "Render Current State"
    bl_description = "Render the current visible scene state once and save it directly into the render output folder"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        scene = context.scene
        output_path = _current_state_render_path()
        job = {
            "output_path": output_path,
            "transparent_output_path": _transparent_output_path(output_path),
            "freestyle_output_path": _freestyle_pass_path(output_path),
            "freestyle_overlay_path": _freestyle_overlay_path(output_path),
        }
        render = scene.render
        visibility_snapshot = _snapshot_visibility()
        previous_settings = {
            "use_file_extension": render.use_file_extension,
            "resolution_x": render.resolution_x,
            "resolution_y": render.resolution_y,
        }

        light_root, light_matrix = None, None
        try:
            from .render_selected import selected_bounds
            from .render_studio import position_lights
            objects = [obj for obj in scene.objects if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}
                       and not obj.hide_render and not obj.hide_get()
                       and not any(_scene_collection_matches(c, settings) for c in obj.users_collection)]
            if objects:
                _, center, _ = selected_bounds(context, objects)
                light_root, light_matrix = position_lights(context, center)
            settings.status = "Rendering current state"
            _render_current_job(context, settings, job)
        except Exception as error:
            settings.status = f"Current state render failed: {error}"
            self.report({"ERROR"}, settings.status)
            return {"CANCELLED"}
        finally:
            if light_root:
                light_root.matrix_world = light_matrix
                context.view_layer.update()
            _restore_visibility(visibility_snapshot)
            render.use_file_extension = previous_settings["use_file_extension"]
            render.resolution_x = previous_settings["resolution_x"]
            render.resolution_y = previous_settings["resolution_y"]

        settings.last_output_path = output_path
        extra_output = f", {job['transparent_output_path']}" if settings.transparent_background else ""
        if settings.freestyle_edges and settings.freestyle_as_render_pass:
            settings.status = "Rendered current state with Freestyle pass"
            self.report(
                {"INFO"},
                f"Rendered current state: {output_path}{extra_output}, {job['freestyle_overlay_path']}, {job['freestyle_output_path']}",
            )
            return {"FINISHED"}

        settings.status = "Rendered current state"
        self.report({"INFO"}, f"Rendered current state: {output_path}{extra_output}")
        return {"FINISHED"}


def _render_single_job(context, settings, job):
    for options in _render_single_job_steps(context, settings, job):
        bpy.ops.render.render(**options)


def _render_single_job_steps(context, settings, job):
    if settings.freestyle_edges and settings.freestyle_as_render_pass:
        _disable_freestyle(context)
        _configure_render(context.scene, settings, job, job["output_path"],
                          'PNG' if context.scene.render.film_transparent and settings.image_format == 'JPEG' else settings.image_format)
        yield {'write_still': True}

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
            yield {'write_still': True}
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
        'PNG' if context.scene.render.film_transparent and settings.image_format == 'JPEG' else settings.image_format,
        settings.freestyle_edges,
    )
    yield {'write_still': True}


def _render_texture_job(context, settings, job):
    snapshot = _snapshot_visibility()
    scene = context.scene
    view = scene.view_settings
    transform = (view.view_transform, view.look, view.exposure, view.gamma)
    visible_names = set(job.get("texture_objects", [job["object"]]))
    image_overrides = []
    try:
        if job.get("texture_kind") == "Combined":
            # Standard display is needed for Base Color. Decode a private copy
            # of Normal as sRGB so the same display transform preserves its RGB
            # data values, without changing the source image's color space.
            for name in visible_names:
                plane = bpy.data.objects.get(name)
                if plane is None or plane.get(PLANE_TAG) != "Normal":
                    continue
                for material in plane.data.materials:
                    for node in material.node_tree.nodes:
                        if node.type == "TEX_IMAGE" and node.image:
                            original = node.image
                            copy = original.copy()
                            image_overrides.append((node, original, copy))
                            copy.colorspace_settings.name = "sRGB"
                            node.image = copy
        for other in scene.objects:
            if other.type not in {"CAMERA", "LIGHT"}:
                other.hide_render = other.name not in visible_names
        scene.render.film_transparent = True
        _disable_freestyle(context)
        scene.render.use_compositing = False
        # Normal maps are data, so do not apply an sRGB display transform.
        view.view_transform = "Raw" if job.get("texture_kind") == "Normal" else "Standard"
        view.look = "None"
        view.exposure = 0
        view.gamma = 1
        _configure_render(scene, settings, job, file_format='PNG')
        bpy.ops.render.render(write_still=True)
    finally:
        for node, original, copy in image_overrides:
            node.image = original
            bpy.data.images.remove(copy)
        view.view_transform, view.look, view.exposure, view.gamma = transform
        _restore_visibility(snapshot)


def _render_current_job(context, settings, job):
    for options in _render_current_job_steps(context, settings, job):
        bpy.ops.render.render(**options)


def _render_current_job_steps(context, settings, job):
    """Render the scene image, then an isolated transparent companion image."""
    if job.get("texture_kind"):
        _render_texture_job(context, settings, job)
        return
    context.scene.render.film_transparent = False
    yield from _render_single_job_steps(context, settings, job)
    if not settings.transparent_background:
        return

    snapshot = _snapshot_visibility()
    transparent_path = job.get("transparent_output_path") or _transparent_output_path(job["output_path"])
    transparent_job = {
        **job,
        "output_path": transparent_path,
        "freestyle_output_path": _freestyle_pass_path(transparent_path),
        "freestyle_overlay_path": _freestyle_overlay_path(transparent_path),
    }
    try:
        _prepare_transparent_background(settings)
        yield from _render_single_job_steps(context, settings, transparent_job)
    finally:
        _restore_visibility(snapshot)


class OBJECT_OT_polygroups_render_rename_suffix(bpy.types.Operator):
    bl_idname = 'object.polygroups_render_rename_suffix'
    bl_label = 'Rename Suffix'
    bl_description = 'Replace HIGH, MID or LOW suffix on selected meshes'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (not context.scene.polygroups_render_settings.is_running
                and any(obj.type == 'MESH' for obj in context.selected_objects))

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        plans = {}
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            target = re.sub(r'_(HIGH|MID|LOW)(\.\d{3})?$',
                            lambda m: '_' + settings.render_rename_suffix + (m.group(2) or ''),
                            obj.name, flags=re.IGNORECASE)
            if target != obj.name:
                plans[obj] = (obj.name, target)
        targets = [target for _, target in plans.values()]
        if len(targets) != len(set(targets)) or any(
                bpy.data.objects.get(target) not in (None, obj) and bpy.data.objects.get(target) not in plans
                for obj, (_, target) in plans.items()):
            self.report({'WARNING'}, 'Conflicting target mesh names; no objects renamed')
            return {'CANCELLED'}
        for obj in plans:
            obj.name = '__RenderSuffix__'
        source_names = {old: target for old, target in plans.values()}
        for obj, (_, target) in plans.items():
            obj.name = target
        for obj in bpy.data.objects:
            source = obj.get(MULTIVIEW_SOURCE_PROP)
            if source in source_names:
                obj[MULTIVIEW_SOURCE_PROP] = source_names[source]
        settings.queue_scanned = False
        self.report({'INFO'}, f'Renamed {len(plans)} mesh suffix(es)')
        return {'FINISHED'}


def _lod_low_conflicts(queue):
    """Warn when a LOD uses the LOW output slot beside a separate LOW mesh."""
    conflicts = []
    checked = set()
    for job in queue:
        if not job.get('variant', '').startswith('LOD'):
            continue
        name = job.get('collection')
        if name in checked:
            continue
        checked.add(name)
        collection = bpy.data.collections.get(name)
        if collection is None:
            continue
        low = [obj.name for obj in _collection_objects_recursive(collection)
               if obj.type == 'MESH' and not obj.get(MULTIVIEW_PROP) and not obj.get(PLANE_TAG)
               and _render_object_suffix(obj) == 'LOW']
        if low:
            conflicts.append(f"{name}: {job['variant']} renders as LOW; separate LOW mesh(es) excluded: {', '.join(low)}. LOW image filenames are shared.")
    return conflicts


class OBJECT_OT_polygroups_scan_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_scan_render_queue"
    bl_label = "Scan Render Queue"
    bl_description = "Scan *_Collection asset collections and prepare selected LOW/MID/HIGH/LOD render jobs"
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
        settings.queue_scanned = True
        settings.status = f"Queued {settings.total_count} render job(s) from {collection_count} collection(s)"
        for warning in _lod_low_conflicts(queue):
            self.report({'WARNING'}, warning)
        return {"FINISHED"}


_ACTIVE_QUEUE_TASK = None


class OBJECT_OT_polygroups_reset_render_state(bpy.types.Operator):
    bl_idname = "object.polygroups_reset_render_state"
    bl_label = "Reset Render State"
    bl_description = "Clean up stale render tasks and unlock animation and render queue controls"
    bl_options = {"REGISTER"}

    def execute(self, context):
        global _ACTIVE_QUEUE_TASK
        from . import turnaround_animation

        if bpy.app.is_job_running("RENDER"):
            self.report({"WARNING"}, "Wait for the active render to finish or cancel it before resetting")
            return {"CANCELLED"}
        warnings = []
        task = turnaround_animation._ACTIVE_RENDER_TASK
        if task is not None:
            try:
                task._finish(completed=False)
            except Exception as error:
                warnings.append(str(error))
            finally:
                task._finished = True
                turnaround_animation._ACTIVE_RENDER_TASK = None
        task = _ACTIVE_QUEUE_TASK
        if task is not None:
            try:
                task._finish(context, "Render state reset")
            except Exception as error:
                warnings.append(str(error))
            finally:
                task._reset = True
                _ACTIVE_QUEUE_TASK = None
        settings = context.scene.polygroups_render_settings
        settings.is_running = False
        settings.stop_requested = False
        settings.queue_scanned = False
        settings.status = "Render state reset"
        settings.animation_status = "Render state reset"
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        self.report({"WARNING"} if warnings else {"INFO"},
                    "Render state reset" + (": " + "; ".join(warnings) if warnings else ""))
        return {"FINISHED"}


class OBJECT_OT_polygroups_start_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_start_render_queue"
    bl_label = "Start Render Queue"
    bl_description = "Render queued LOW/MID/HIGH/LOD asset previews one job at a time"
    bl_options = {"REGISTER", "UNDO"}

    continue_from_current: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    _timer = None
    _visibility_snapshot = None
    _cursor = None

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_render_settings
        return not settings.is_running

    def invoke(self, context, event):
        global _ACTIVE_QUEUE_TASK
        if event is not None:
            update_remesh_cursor(context, event)
        settings = context.scene.polygroups_render_settings
        _normalize_render_output_setting(settings)
        if settings.output_directory.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the blend file before rendering to a // relative folder")
            return {"CANCELLED"}
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

        destinations = [job.get('output_path') for job in queue]
        if len(destinations) != len(set(destinations)):
            self.report({'ERROR'}, 'Conflicting render output filenames. Scan Queue again before rendering.')
            return {'CANCELLED'}
        for warning in _lod_low_conflicts(queue):
            self.report({'WARNING'}, warning)

        if settings.total_count == 0:
            settings.status = "Render queue is empty: no selected LOW/MID/HIGH/LOD meshes in *_Collection assets"
            self.report({"WARNING"}, settings.status)
            return {"CANCELLED"}

        try:
            _ensure_render_job_directories(queue)
        except OSError as error:
            settings.status = f"Cannot create render output folder: {error}"
            self.report({"ERROR"}, settings.status)
            return {"CANCELLED"}

        if settings.freestyle_edges:
            marked_edges, marked_objects = _mark_freestyle_edges(_queue_objects(_load_queue(settings)), True)
            settings.status = f"Marked {marked_edges} Freestyle edge(s) on {marked_objects} object(s)"

        settings.is_running = True
        settings.stop_requested = False
        if not settings.freestyle_edges:
            settings.status = f"Render queue running: {_render_output_base_directory(settings)}"
        self._visibility_snapshot = _snapshot_visibility()
        self._cursor = RenderQueueCursor(context)
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._reset = False
        _ACTIVE_QUEUE_TASK = self
        self.report({"INFO"}, f"Started {settings.total_count} render job(s): {_render_output_base_directory(settings)}")
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def modal(self, context, event):
        update_remesh_cursor(context, event)
        if getattr(self, "_reset", False):
            return {"CANCELLED"}
        settings = context.scene.polygroups_render_settings
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if settings.stop_requested:
            self._finish(context, "Render queue stopped")
            return {"CANCELLED"}

        queue = _load_queue(settings)
        if settings.queue_index >= len(queue):
            self._finish(context, "Render queue complete")
            play_operation_done_sound(context)
            return {"FINISHED"}

        job = queue[settings.queue_index]
        output_exists = os.path.exists(job.get("output_path", ""))
        transparent_exists = bool(job.get("texture_kind")) or not settings.transparent_background or os.path.exists(
            job.get("transparent_output_path") or _transparent_output_path(job.get("output_path", ""))
        )
        if settings.skip_existing and not settings.overwrite_existing and output_exists and transparent_exists:
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
        source = bpy.data.objects.get(job.get("object", ""))
        use_multiview = not job.get("texture_kind") and (settings.multiview_render or (source is not None and
                                                     bool(_prepared_multiview_views(source))))
        multiview_objects = _create_multiview_setup(job) if use_multiview else []
        studio_snapshot = []
        try:
            if not job.get('texture_kind') and source is not None:
                from .render_studio import position_studio_at_origin
                views = multiview_objects or _prepared_multiview_views(source)
                central = next((obj for obj in views if _base_name(obj.name).endswith('_MV_Front')), source)
                context.view_layer.update()
                studio_snapshot = position_studio_at_origin(context, central.matrix_world.translation.copy())
            if job.get("view_mode") == "Hero":
                _isolate_hero_view(source, multiview_objects)
            # The actual render is synchronous; paint the queue status before
            # it blocks the modal event loop for the next image.
            if not bpy.app.background:
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            _render_current_job(context, settings, job)
        except Exception as error:
            _finish_render_job(job, multiview_objects)
            self._finish(context, f"Render failed: {error}")
            self.report({"ERROR"}, f"Render failed: {error}")
            return {"CANCELLED"}
        finally:
            for root, matrix in studio_snapshot:
                root.matrix_world = matrix
            context.view_layer.update()
            if settings.is_running:
                _finish_render_job(job, multiview_objects)

        settings.queue_index += 1
        _sync_progress(settings)
        settings.status = f"Rendered {settings.rendered_count} of {settings.total_count}"
        return {"RUNNING_MODAL"}

    def _finish(self, context, status):
        global _ACTIVE_QUEUE_TASK
        if self._cursor is not None:
            self._cursor.close()
            self._cursor = None
        self._reset = True
        if _ACTIVE_QUEUE_TASK is self:
            _ACTIVE_QUEUE_TASK = None
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

    def cancel(self, context):
        self._finish(context, "Render queue stopped")


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


class OBJECT_OT_polygroups_prepare_selected_multiview(bpy.types.Operator):
    bl_idname = "object.polygroups_prepare_selected_multiview"
    bl_label = "Prepare Selected Multi View"
    bl_description = "Create three persistent preview views for each selected mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (not context.scene.polygroups_render_settings.is_running
                and any(obj.type == "MESH" for obj in context.selected_objects))

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        sources = [obj for obj in context.selected_objects
                   if obj.type == "MESH" and not obj.get(MULTIVIEW_PROP)]
        prepared_count = 0
        for source in sources:
            parent = next((collection for collection in source.users_collection
                           if _asset_name_from_collection(collection)), None)
            if parent is None:
                parent = source.users_collection[0] if source.users_collection else None
            if parent is None:
                continue
            if MULTIVIEW_SOURCE_RENDER_PROP not in source:
                source[MULTIVIEW_SOURCE_RENDER_PROP] = bool(source.hide_render)
                source[MULTIVIEW_SOURCE_VIEWPORT_PROP] = bool(source.hide_viewport)
            for obj in list(bpy.data.objects):
                if obj.get(MULTIVIEW_PROP) and obj.get(MULTIVIEW_SOURCE_PROP) == source.name:
                    bpy.data.objects.remove(obj, do_unlink=True)
            asset_name = _asset_name_from_collection(parent) or source.name
            _multiview_views(source, parent, asset_name, settings, prepared=True)
            prepared_count += 1
        self.report({"INFO"}, f"Prepared three views for {prepared_count} selected mesh(es)")
        return {"FINISHED"} if prepared_count else {"CANCELLED"}


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
    bl_description = "Mark all selected mesh edges for Freestyle rendering"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        marked_edges, marked_objects = _mark_freestyle_edges([obj for obj in context.selected_objects if obj.type == "MESH"], True)
        self.report(
            {"INFO"},
            f"Marked {marked_edges} Freestyle edge(s) on {marked_objects} object(s)",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_freestyle_edges(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_freestyle_edges"
    bl_label = "Clear Freestyle"
    bl_description = "Clear Freestyle edge marks from LOW/MID/HIGH/LOD asset meshes"
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
