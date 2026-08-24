import os
import re

import bpy


INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'
FAB_VARIANT_SUFFIXES = ("LOW", "MID", "HIGH")


def _selected_mesh_objects(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def _safe_path_token(value, fallback="Mesh"):
    value = re.sub(INVALID_FILENAME_CHARS, "_", value or "").strip(" ._")
    value = re.sub(r"_+", "_", value)
    return value or fallback


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
