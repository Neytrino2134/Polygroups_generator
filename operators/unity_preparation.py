"""Unity naming and self-contained per-mesh FBX exports."""
import os
import re
from array import array

import bpy

from .fab_preparation import _texture_suffix, _ungroup_source_texture_nodes
from .mesh_export import _safe_path_token


def unity_name(settings, lod):
    base = "_".join(filter(None, (
        _safe_path_token(settings.unity_asset_name, "Asset"),
        _safe_path_token(settings.unity_asset_index, ""),
    )))
    return base if lod in {"", "LOD0"} else f"{base}.{lod}"


def texture_nodes(tree, seen=None):
    seen = set() if seen is None else seen
    if tree is None or tree in seen:
        return
    seen.add(tree)
    for node in tree.nodes:
        if node.type == "TEX_IMAGE" and node.image:
            yield node
        elif node.type == "GROUP":
            yield from texture_nodes(node.node_tree, seen)


def isolate_groups(tree):
    for node in tree.nodes:
        if node.type == "GROUP" and node.node_tree:
            node.node_tree = node.node_tree.copy()
            isolate_groups(node.node_tree)


def save_textures(obj, directory):
    os.makedirs(directory, exist_ok=True)
    seen = set()
    for material in obj.data.materials:
        if not material:
            continue
        for node in texture_nodes(material.node_tree):
            image = node.image
            if image in seen:
                continue
            seen.add(image)
            if image.source not in {"FILE", "GENERATED"}:
                raise ValueError(f"Unsupported texture source: {image.name} ({image.source})")
            if not image.has_data:
                raise ValueError(f"Texture has no loaded pixels: {image.name}")
            path = os.path.join(directory, _safe_path_token(image.name) + ".png")
            image.file_format = "PNG"
            image.save(filepath=path)
            image.filepath_raw = path


def prepare_unity(obj, name, asset_name=None):
    asset_name = asset_name or re.sub(r"[._]LOD\d+$", "", name)
    other = bpy.data.objects.get(name)
    if other is not None and other != obj:
        raise ValueError(f"An object named {name} already exists; choose another index")
    # Isolate shared data so preparing one LOD cannot rename another asset's textures.
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    obj.name = name
    obj.data.name = name
    shared = next((mat for mat in bpy.data.materials
                   if mat.get("unity_asset_name") == asset_name), None)
    if shared is not None:
        obj.data.materials.clear()
        obj.data.materials.append(shared)
        for polygon in obj.data.polygons:
            polygon.material_index = 0
        obj["unity_prepared"] = True
        return
    source = obj.active_material
    obj.data.materials.clear()
    if source:
        # Keep the original material intact for unselected objects.
        obj.data.materials.append(source.copy())
    if not obj.data.materials:
        material = bpy.data.materials.new(asset_name)
        material.use_nodes = True
        obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
    image_copies = {}
    used_names = {}
    for index, source in enumerate(tuple(obj.data.materials)):
        if source is None:
            continue
        material = source.copy() if source.users > 1 else source
        obj.data.materials[index] = material
        material.name = asset_name
        material["unity_asset_name"] = asset_name
        if material.node_tree is None:
            continue
        isolate_groups(material.node_tree)
        _ungroup_source_texture_nodes(material)
        for node in texture_nodes(material.node_tree):
            source_image = node.image
            if source_image not in image_copies:
                suffix = _texture_suffix(source_image, node)
                # Connected socket names take precedence over arbitrary source filenames.
                for link in node.outputs.get("Color").links:
                    if link.to_node.type == "NORMAL_MAP":
                        suffix = "Normal"
                    elif link.to_socket.name in {"Base Color", "Metallic", "Roughness"}:
                        suffix = link.to_socket.name.replace(" ", "")
                base = asset_name if suffix == "BaseColor" else f"{asset_name}_{suffix.lower()}"
                used_names[base] = used_names.get(base, 0) + 1
                target = base if used_names[base] == 1 else f"{base}_{used_names[base]}"
                # Image.copy does not copy the in-memory buffer (generated/painted images).
                pixels = array("f", [0.0]) * len(source_image.pixels)
                source_image.pixels.foreach_get(pixels)
                image = source_image if source_image.users == 1 else source_image.copy()
                if pixels:
                    image.pixels.foreach_set(pixels)
                    image.update()
                image.name = target
                image_copies[source_image] = image
            node.image = image_copies[source_image]
    obj["unity_prepared"] = True


def move_to_lod_collection(context, obj, lod):
    base = re.sub(r"\.LOD\d+$", "", obj.name)
    name = f"{base}_{lod}_Collection"
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if collection.name not in context.scene.collection.children:
        context.scene.collection.children.link(collection)
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    for old in tuple(obj.users_collection):
        if old != collection:
            old.objects.unlink(obj)


def polygon_count(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return len(mesh.polygons)
    finally:
        evaluated.to_mesh_clear()


class OBJECT_OT_polygroups_prepare_unity(bpy.types.Operator):
    bl_idname = "object.polygroups_prepare_unity"
    bl_label = "Unity Prepare"
    bl_description = "Name the active mesh, materials and textures for Unity (does not simplify geometry)"
    bl_options = {"REGISTER", "UNDO"}

    lod: bpy.props.EnumProperty(items=[(f"LOD{i}", f"LOD{i}", "") for i in range(6)])
    auto_lods: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        if settings.unity_copy_textures and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the blend file before copying textures")
            return {"CANCELLED"}
        obj = context.active_object
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            meshes = [obj]
            if self.auto_lods:
                meshes = [item for item in context.selected_objects if item.type == "MESH"]
                if not 1 <= len(meshes) <= 6:
                    raise ValueError("Select 1–6 meshes for LOD0–LOD5")
                depsgraph = context.evaluated_depsgraph_get()
                meshes.sort(key=lambda item: (-polygon_count(item, depsgraph), item.name))
            lods = [f"LOD{i}" if self.auto_lods else self.lod
                     for i in range(len(meshes))]
            names = [unity_name(settings, lod) for lod in lods]
            # Check the complete set before renaming; allow LODs to swap names on a rerun.
            for name in names:
                existing = bpy.data.objects.get(name)
                if existing is not None and existing not in meshes:
                    raise ValueError(f"An object named {name} already exists; choose another index")
            for item in meshes:
                if item.data.users > 1:
                    item.data = item.data.copy()
                item.name = "__Unity_Prepare__"
            for item, name, lod in zip(meshes, names, lods):
                prepare_unity(item, name, unity_name(settings, ""))
                move_to_lod_collection(context, item, lod)
            if settings.unity_copy_textures:
                save_textures(meshes[0], os.path.join(os.path.dirname(bpy.data.filepath), "Textures"))
        except (RuntimeError, ValueError, OSError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if settings.unity_auto_increment_index:
            match = re.fullmatch(r"(.*?)(\d+)", settings.unity_asset_index)
            if match:
                prefix, digits = match.groups()
                settings.unity_asset_index = f"{prefix}{int(digits) + 1:0{len(digits)}d}"
        self.report({"INFO"}, f"Prepared {len(meshes)} mesh(es): " + ", ".join(item.name for item in meshes))
        return {"FINISHED"}


class OBJECT_OT_polygroups_export_unity(bpy.types.Operator):
    bl_idname = "object.polygroups_export_unity"
    bl_label = "Export Unity FBX"
    bl_description = "Export selected prepared Unity meshes, each with its textures in its own folder"

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        directory = settings.unity_export_directory
        if directory.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the blend file or choose an absolute export directory")
            return {"CANCELLED"}
        root = bpy.path.abspath(directory)
        selected = tuple(context.selected_objects)
        meshes = [obj for obj in selected if obj.type == "MESH"]
        if any(not obj.get("unity_prepared") for obj in meshes):
            self.report({"ERROR"}, "Use Unity Prepare on each selected mesh first")
            return {"CANCELLED"}
        active = context.view_layer.objects.active
        mode = active.mode if active else "OBJECT"
        rig = None
        if settings.unity_use_auto_rig_pro:
            rigs = [obj for obj in selected if obj.type == "ARMATURE"]
            if len(rigs) != 1:
                self.report({"ERROR"}, "Select exactly one rig for Auto-Rig Pro export")
                return {"CANCELLED"}
            rig = rigs[0]
            if len({re.sub(r"\.LOD\d+$", "", obj.name, flags=re.IGNORECASE) for obj in meshes}) != 1:
                self.report({"ERROR"}, "Auto-Rig Pro export supports one selected Unity asset at a time")
                return {"CANCELLED"}
            if not hasattr(getattr(bpy.ops, "arp", None), "arp_export_fbx_panel"):
                self.report({"ERROR"}, "Auto-Rig Pro export operator is unavailable; enable Auto-Rig Pro")
                return {"CANCELLED"}
        paths = {node.image: node.image.filepath_raw for obj in meshes
                 for mat in obj.data.materials if mat for node in texture_nodes(mat.node_tree)}
        try:
            if mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            groups = {}
            for obj in meshes:
                asset_name = re.sub(r"\.LOD\d+$", "", obj.name, flags=re.IGNORECASE)
                groups.setdefault(asset_name, []).append(obj)
            for asset_name in groups:
                folder = os.path.join(root, _safe_path_token(asset_name))
                if os.path.exists(folder) and not settings.unity_export_overwrite:
                    raise ValueError(f"Folder already exists: {folder}. Enable Overwrite to replace files")
            for asset_name, lods in groups.items():
                folder = os.path.join(root, _safe_path_token(asset_name))
                # Unity Prepare assigns one common material and texture set to all LODs.
                save_textures(lods[0], folder)
                for obj in lods:
                    bpy.ops.object.select_all(action="DESELECT")
                    obj.select_set(True)
                    filepath = os.path.join(folder, _safe_path_token(obj.name) + ".fbx")
                    if rig is not None and obj.name == asset_name:
                        rig.select_set(True)
                        context.view_layer.objects.active = rig
                        result = bpy.ops.arp.arp_export_fbx_panel("EXEC_DEFAULT", filepath=filepath)
                    else:
                        context.view_layer.objects.active = obj
                        result = bpy.ops.export_scene.fbx(
                            filepath=filepath, use_selection=True, object_types={"MESH"},
                            path_mode="RELATIVE", use_mesh_modifiers=True, bake_anim=False,
                        )
                    if "FINISHED" not in result:
                        raise RuntimeError(f"FBX export failed: {obj.name}")
        except (RuntimeError, ValueError, OSError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        finally:
            for image, path in paths.items():
                image.filepath_raw = path
            bpy.ops.object.select_all(action="DESELECT")
            for obj in selected:
                obj.select_set(True)
            context.view_layer.objects.active = active
            if active and mode != "OBJECT":
                bpy.ops.object.mode_set(mode=mode)
        self.report({"INFO"}, f"Exported {len(meshes)} Unity asset(s) to {root}")
        return {"FINISHED"}
