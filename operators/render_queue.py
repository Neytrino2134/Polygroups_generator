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
    base_directory = bpy.path.abspath(settings.output_directory or "//Renders")
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


def _apply_render_engine(scene, settings):
    if settings.render_engine == "CYCLES":
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
        },
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


def _configure_render(scene, settings, job):
    _apply_render_engine(scene, settings)
    scene.render.resolution_x = settings.resolution_x
    scene.render.resolution_y = settings.resolution_y
    scene.render.use_file_extension = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_overwrite = settings.overwrite_existing
    os.makedirs(os.path.dirname(job["output_path"]), exist_ok=True)
    scene.render.filepath = job["output_path"]


class OBJECT_OT_polygroups_scan_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_scan_render_queue"
    bl_label = "Scan Render Queue"
    bl_description = "Scan *_Collection asset collections and prepare LOW/MID render jobs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
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

        settings.is_running = True
        settings.stop_requested = False
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
        _configure_render(context.scene, settings, job)
        multiview_objects = _create_multiview_setup(job) if settings.multiview_render else []
        try:
            bpy.ops.render.render(write_still=True)
        finally:
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


class OBJECT_OT_polygroups_continue_render_queue(bpy.types.Operator):
    bl_idname = "object.polygroups_continue_render_queue"
    bl_label = "Continue Render Queue"
    bl_description = "Continue the render queue from the current saved job"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return bpy.ops.object.polygroups_start_render_queue("INVOKE_DEFAULT", continue_from_current=True)
