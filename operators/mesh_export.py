import os
import re
import uuid

import bpy

from ..sound import play_operation_done_sound


INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'
FAB_VARIANT_SUFFIXES = ("LOW", "MID", "HIGH")
ASSET_COLLECTION_SUFFIX = "_Collection"
BLENDER_NUMERIC_SUFFIX_RE = re.compile(r"\.\d{3}$")
TEMP_BLEND_EXPORT_PREFIX = "__POLYGROUPS_BLEND_EXPORT__"


def _selected_mesh_objects(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def _safe_path_token(value, fallback="Mesh"):
    value = re.sub(INVALID_FILENAME_CHARS, "_", value or "").strip(" ._")
    value = re.sub(r"_+", "_", value)
    return value or fallback


def _base_name(value):
    return BLENDER_NUMERIC_SUFFIX_RE.sub("", value or "")


def _collection_asset_name(collection):
    name = _base_name(collection.name)
    if not name.upper().endswith(ASSET_COLLECTION_SUFFIX.upper()):
        return ""
    return name[: -len(ASSET_COLLECTION_SUFFIX)]


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


def _asset_collections():
    items = []
    for collection in bpy.data.collections:
        asset_name = _collection_asset_name(collection)
        if not asset_name:
            continue
        if collection.name.startswith(TEMP_BLEND_EXPORT_PREFIX):
            continue
        items.append((asset_name, collection))
    return sorted(items, key=lambda item: item[0].lower())


def _objects_with_suffix(collections, suffix):
    suffix = f"_{suffix.upper()}"
    objects = []
    seen = set()
    for _asset_name, collection in collections:
        for obj in _collection_objects_recursive(collection):
            if obj.name in seen or obj.type != "MESH":
                continue
            if _base_name(obj.name).upper().endswith(suffix):
                seen.add(obj.name)
                objects.append(obj)
    return sorted(objects, key=lambda obj: obj.name.lower())


def _blend_export_root_directory(settings):
    if (settings.blend_export_directory or "").startswith("//") and not bpy.data.filepath:
        return None
    path = bpy.path.abspath(settings.blend_export_directory or "//Blend")
    return os.path.normpath(path)


def _static_collection_names(settings):
    names = []
    seen = set()
    for item in (settings.blend_export_static_collections or "").split(","):
        name = item.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
    return names


def _static_collections(settings):
    collections = []
    missing = []
    for name in _static_collection_names(settings):
        collection = bpy.data.collections.get(name)
        if collection is None:
            collection = next((item for item in bpy.data.collections if _base_name(item.name) == name), None)
        if collection is None:
            missing.append(name)
        elif not collection.name.startswith(TEMP_BLEND_EXPORT_PREFIX):
            collections.append(collection)
    return collections, missing


def _blend_filepath(root_dir, name):
    return os.path.join(root_dir, f"{_safe_path_token(name, 'Asset')}.blend")


def _asset_folder_token(obj):
    name = obj.name
    match = re.match(r"^SM_(.+)_(LOW|MID|HIGH)$", name, re.IGNORECASE)
    if match is not None:
        return _safe_path_token(match.group(1))

    for suffix in FAB_VARIANT_SUFFIXES:
        marker = f"_{suffix}"
        if name.upper().endswith(marker):
            return _safe_path_token(name[:-len(marker)])

    return _safe_path_token(name)


def _export_root_directory(settings):
    blend_filepath = bpy.data.filepath
    if not blend_filepath:
        return None

    blend_dir = os.path.dirname(blend_filepath)
    folder_name = "FBX" if settings.mesh_export_format == "FBX" else "GLTF"
    return os.path.join(blend_dir, folder_name)


def _export_filepath(root_dir, obj, export_format):
    object_token = _safe_path_token(obj.name)
    asset_token = _asset_folder_token(obj)
    extension = {
        "FBX": ".fbx",
        "GLB": ".glb",
        "GLTF": ".gltf",
    }[export_format]
    return os.path.join(root_dir, asset_token, f"{object_token}{extension}")


def _export_selected_object(filepath, export_format):
    if export_format == "FBX":
        return bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
        )

    gltf_format = "GLB" if export_format == "GLB" else "GLTF_EMBEDDED"
    return bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format=gltf_format,
        use_selection=True,
    )


def _copy_render_settings(source, target):
    target.frame_set(source.frame_current)
    target.camera = source.camera
    target.unit_settings.system = source.unit_settings.system
    target.unit_settings.scale_length = source.unit_settings.scale_length
    target.unit_settings.length_unit = source.unit_settings.length_unit
    target.world = source.world

    for attr in (
        "engine",
        "resolution_x",
        "resolution_y",
        "resolution_percentage",
        "fps",
        "film_transparent",
        "use_freestyle",
    ):
        if hasattr(source.render, attr) and hasattr(target.render, attr):
            try:
                setattr(target.render, attr, getattr(source.render, attr))
            except Exception:
                pass

    for attr in ("view_transform", "look", "exposure", "gamma", "view_settings"):
        if attr == "view_settings":
            continue
        if hasattr(source.view_settings, attr) and hasattr(target.view_settings, attr):
            try:
                setattr(target.view_settings, attr, getattr(source.view_settings, attr))
            except Exception:
                pass

    if hasattr(source, "cycles") and hasattr(target, "cycles"):
        for attr in ("samples", "preview_samples", "use_denoising", "max_bounces"):
            if hasattr(source.cycles, attr) and hasattr(target.cycles, attr):
                try:
                    setattr(target.cycles, attr, getattr(source.cycles, attr))
                except Exception:
                    pass

    if hasattr(source, "eevee") and hasattr(target, "eevee"):
        for attr in ("taa_render_samples", "taa_samples"):
            if hasattr(source.eevee, attr) and hasattr(target.eevee, attr):
                try:
                    setattr(target.eevee, attr, getattr(source.eevee, attr))
                except Exception:
                    pass


def _link_collection_once(parent, collection):
    if parent.children.get(collection.name) is None:
        parent.children.link(collection)


def _link_object_once(collection, obj):
    if collection.objects.get(obj.name) is None:
        collection.objects.link(obj)


def _create_temp_export_scene(context, name, collections, objects, include_render_settings):
    token = uuid.uuid4().hex[:8]
    scene = bpy.data.scenes.new(f"{TEMP_BLEND_EXPORT_PREFIX}{name}_{token}")
    temp_collections = []

    if include_render_settings:
        _copy_render_settings(context.scene, scene)
        if context.scene.camera is not None and not any(
            context.scene.camera.name in {obj.name for obj in _collection_objects_recursive(collection)}
            for collection in collections
        ):
            camera_collection = bpy.data.collections.new(f"{TEMP_BLEND_EXPORT_PREFIX}Camera_{token}")
            scene.collection.children.link(camera_collection)
            camera_collection.objects.link(context.scene.camera)
            temp_collections.append(camera_collection)

    for collection in collections:
        _link_collection_once(scene.collection, collection)

    if objects:
        object_collection = bpy.data.collections.new(f"{TEMP_BLEND_EXPORT_PREFIX}{name}_Objects_{token}")
        scene.collection.children.link(object_collection)
        for obj in objects:
            _link_object_once(object_collection, obj)
        temp_collections.append(object_collection)

    return scene, temp_collections


def _remove_temp_scene(scene, temp_collections):
    for collection in temp_collections:
        if bpy.data.collections.get(collection.name) is collection:
            bpy.data.collections.remove(collection, do_unlink=True)
    if bpy.data.scenes.get(scene.name) is scene:
        bpy.data.scenes.remove(scene, do_unlink=True)


def _write_blend_file(context, filepath, name, collections, objects, include_render_settings):
    scene, temp_collections = _create_temp_export_scene(
        context,
        name,
        collections,
        objects,
        include_render_settings,
    )
    try:
        bpy.data.libraries.write(
            filepath,
            {scene},
            fake_user=False,
            path_remap="RELATIVE_ALL",
            compress=False,
        )
    finally:
        _remove_temp_scene(scene, temp_collections)


def _blend_export_scan(settings):
    collections = _asset_collections()
    low_objects = _objects_with_suffix(collections, "LOW")
    mid_objects = _objects_with_suffix(collections, "MID")
    file_count = 0
    if settings.blend_export_individual_assets:
        file_count += len(collections)
    if settings.blend_export_all_low and low_objects:
        file_count += 1
    if settings.blend_export_all_mid and mid_objects:
        file_count += 1

    settings.blend_export_collection_count = len(collections)
    settings.blend_export_low_count = len(low_objects)
    settings.blend_export_mid_count = len(mid_objects)
    settings.blend_export_file_count = file_count
    settings.blend_export_status = (
        f"Found {len(collections)} collection(s), {len(low_objects)} LOW, {len(mid_objects)} MID"
    )
    return collections, low_objects, mid_objects


class OBJECT_OT_polygroups_export_selected_meshes(bpy.types.Operator):
    bl_idname = "object.polygroups_export_selected_meshes"
    bl_label = "Export Selected Meshes"
    bl_description = "Export each selected mesh to FBX, GLB, or GLTF in a per-object folder"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        mesh_objects = sorted(
            _selected_mesh_objects(context),
            key=lambda obj: (_asset_folder_token(obj).lower(), obj.name.lower()),
        )
        root_dir = _export_root_directory(settings)
        if root_dir is None:
            self.report({"ERROR"}, "Save the blend file before exporting meshes")
            return {"CANCELLED"}

        original_active = context.view_layer.objects.active
        original_selection = tuple(context.selected_objects)
        original_mode = original_active.mode if original_active else "OBJECT"

        if original_active and original_active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        exported_count = 0
        try:
            for obj in mesh_objects:
                filepath = _export_filepath(root_dir, obj, settings.mesh_export_format)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)

                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj

                result = _export_selected_object(filepath, settings.mesh_export_format)
                if "FINISHED" in result:
                    exported_count += 1
        finally:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in original_selection:
                if obj.name in context.view_layer.objects:
                    obj.select_set(True)
            if original_active and original_active.name in context.view_layer.objects:
                context.view_layer.objects.active = original_active
                if original_mode != "OBJECT":
                    try:
                        bpy.ops.object.mode_set(mode=original_mode)
                    except RuntimeError:
                        bpy.ops.object.mode_set(mode="OBJECT")

        self.report(
            {"INFO"},
            f"Exported {exported_count} mesh object(s) to {root_dir}",
        )
        return {"FINISHED"} if exported_count else {"CANCELLED"}


class OBJECT_OT_polygroups_scan_blend_assets(bpy.types.Operator):
    bl_idname = "object.polygroups_scan_blend_assets"
    bl_label = "Scan Blend Assets"
    bl_description = "Scan *_Collection asset collections for blend export"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        _blend_export_scan(settings)
        self.report({"INFO"}, settings.blend_export_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_add_blend_static_collection(bpy.types.Operator):
    bl_idname = "object.polygroups_add_blend_static_collection"
    bl_label = "Add Static Collection"
    bl_description = "Add the picked collection to the blend asset static collection list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        collection = settings.blend_export_static_collection_picker
        if collection is None:
            self.report({"WARNING"}, "Pick a static collection first")
            return {"CANCELLED"}

        names = _static_collection_names(settings)
        if collection.name not in names:
            names.append(collection.name)
        settings.blend_export_static_collections = ", ".join(names)
        self.report({"INFO"}, f"Added static collection {collection.name}")
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_blend_static_collections(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_blend_static_collections"
    bl_label = "Clear Static Collections"
    bl_description = "Clear the blend asset static collection list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        settings.blend_export_static_collections = ""
        settings.blend_export_static_collection_picker = None
        self.report({"INFO"}, "Cleared static collections")
        return {"FINISHED"}


class OBJECT_OT_polygroups_export_blend_assets(bpy.types.Operator):
    bl_idname = "object.polygroups_export_blend_assets"
    bl_label = "Export Blend Assets"
    bl_description = "Export *_Collection assets and combined LOW/MID blend files"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        root_dir = _blend_export_root_directory(settings)
        if root_dir is None:
            self.report({"ERROR"}, "Save the blend file before exporting to a // relative Blend folder")
            return {"CANCELLED"}
        collections, low_objects, mid_objects = _blend_export_scan(settings)
        static_collections, missing_static = _static_collections(settings)

        if not collections and not low_objects and not mid_objects:
            settings.blend_export_status = "No *_Collection assets found"
            self.report({"WARNING"}, settings.blend_export_status)
            return {"CANCELLED"}

        os.makedirs(root_dir, exist_ok=True)
        exported_count = 0
        skipped_count = 0

        def export_item(filepath, name, item_collections, item_objects):
            nonlocal exported_count
            nonlocal skipped_count
            if os.path.exists(filepath) and not settings.blend_export_overwrite_existing:
                skipped_count += 1
                return
            _write_blend_file(
                context,
                filepath,
                name,
                item_collections,
                item_objects,
                settings.blend_export_include_render_settings,
            )
            exported_count += 1

        try:
            if settings.blend_export_individual_assets:
                used_names = set()
                for asset_name, collection in collections:
                    file_name = _safe_path_token(asset_name, "Asset")
                    original_name = file_name
                    index = 1
                    while file_name.lower() in used_names:
                        index += 1
                        file_name = f"{original_name}_{index:03d}"
                    used_names.add(file_name.lower())
                    export_item(
                        _blend_filepath(root_dir, file_name),
                        file_name,
                        [collection] + static_collections,
                        [],
                    )

            if settings.blend_export_all_low and low_objects:
                export_item(
                    _blend_filepath(root_dir, "All_LOW"),
                    "All_LOW",
                    static_collections,
                    low_objects,
                )

            if settings.blend_export_all_mid and mid_objects:
                export_item(
                    _blend_filepath(root_dir, "All_MID"),
                    "All_MID",
                    static_collections,
                    mid_objects,
                )
        except Exception as error:
            settings.blend_export_status = f"Blend export failed: {error}"
            self.report({"ERROR"}, settings.blend_export_status)
            return {"CANCELLED"}

        status_parts = [f"Exported {exported_count} blend file(s)"]
        if skipped_count:
            status_parts.append(f"skipped {skipped_count}")
        if missing_static:
            status_parts.append(f"missing static: {', '.join(missing_static)}")
        settings.blend_export_status = "; ".join(status_parts)
        self.report({"INFO"}, settings.blend_export_status)
        if exported_count:
            play_operation_done_sound(context)
        return {"FINISHED"} if exported_count else {"CANCELLED"}
