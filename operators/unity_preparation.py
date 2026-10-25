"""Unity naming and self-contained per-mesh FBX exports."""
import os
import shutil
import re
from contextlib import ExitStack
from array import array

import bpy
from ..core.asset_names import asset_name

from .fab_preparation import _texture_suffix, _ungroup_source_texture_nodes
from .mesh_export import (
    _detach_export_alpha_maps,
    _restore_export_alpha_maps,
    _evaluated_mesh_counts,
    _export_at_world_origin,
    _safe_path_token,
    _write_export_mesh_info,
    _export_gltf_asset,
    _export_selected_object,
)


def unity_name(settings, lod):
    base = "_".join(filter(None, (
        _safe_path_token(asset_name(settings.unity_asset_name), "Asset"),
        settings.unity_name_index.zfill(2),
        _safe_path_token(settings.unity_asset_index, ""),
        _safe_path_token(settings.unity_asset_suffix.strip(), ""),
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


def normalize_unity_texture_names(meshes):
    images = {node.image for obj in meshes for mat in obj.data.materials if mat
              for node in texture_nodes(mat.node_tree)}
    for image in sorted(images, key=lambda item: item.name):
        clean = re.sub(r'(?:\.\d{3})+$', '', image.name)
        if clean == image.name:
            continue
        other = bpy.data.images.get(clean)
        if other is not None and other != image:
            other.name = clean + '__Duplicate'
        image.name = clean


def validate_unity_arp_selection(context):
    settings = context.scene.polygroups_mesh_finalization_settings
    if not settings.unity_use_auto_rig_pro:
        return None
    rigs = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
    if len(rigs) != 1 or rigs[0].data.bones.get('c_traj') is None:
        return 'Select one Auto-Rig Pro rig (with c_traj) together with the Unity mesh before exporting'
    return None


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
            if _texture_suffix(image, node) in {"AlphaMap", "MergeMask", "ArtifactMask"}:
                continue
            if image in seen:
                continue
            seen.add(image)
            if image.source not in {"FILE", "GENERATED"}:
                raise ValueError(f"Unsupported texture source: {image.name} ({image.source})")
            if not image.has_data and not len(image.pixels):
                raise ValueError(f"Texture has no loaded pixels: {image.name}")
            path = os.path.join(directory, _safe_path_token(image.name) + ".png")
            image.file_format = "PNG"
            image.save(filepath=path)
            # Persist against the blend, not the original workstation folder.
            image.filepath_raw = bpy.path.relpath(path)
            # Prepared pixel copies must reopen from the newly written file,
            # rather than regenerating a blank image after reloading the blend.
            if image.source == 'GENERATED':
                image.source = 'FILE'


def prepare_unity(obj, name, asset_name=None, shared_material=None):
    asset_name = asset_name or re.sub(r"[._]LOD\d+$", "", name)
    other = bpy.data.objects.get(name)
    if other is not None and other != obj:
        raise ValueError(f"An object named {name} already exists; choose another index")
    # Isolate shared data so preparing one LOD cannot rename another asset's textures.
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    obj.name = name
    obj.data.name = name
    # Only share the material prepared in THIS invocation, never a stale asset
    # material left in the blend from an earlier export with the same name.
    shared = shared_material
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
            if _texture_suffix(source_image, node) in {"AlphaMap", "MergeMask", "ArtifactMask"}:
                continue
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
                image = bpy.data.images.new(target, width=source_image.size[0],
                    height=source_image.size[1], alpha=source_image.channels == 4,
                    float_buffer=source_image.is_float)
                image.colorspace_settings.name = source_image.colorspace_settings.name
                image.alpha_mode = source_image.alpha_mode
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
    collection.color_tag = context.scene.polygroups_mesh_finalization_settings.unity_collection_color_tag
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


class OBJECT_OT_polygroups_unity_random_color_tag(bpy.types.Operator):
    bl_idname = 'object.polygroups_unity_random_color_tag'
    bl_label = 'Random Collection Color Tag'
    bl_description = 'Choose a random color for the collections created by Unity Prepare'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from random import choice
        settings = context.scene.polygroups_mesh_finalization_settings
        settings.unity_collection_color_tag = choice([
            f'COLOR_{index:02d}' for index in range(1, 9)
            if f'COLOR_{index:02d}' != settings.unity_collection_color_tag])
        return {'FINISHED'}


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
            if self.auto_lods and settings.unity_random_collection_color:
                bpy.ops.object.polygroups_unity_random_color_tag()
            for item in meshes:
                if item.data.users > 1:
                    item.data = item.data.copy()
                item.name = "__Unity_Prepare__"
            shared_material = None
            for item, name, lod in zip(meshes, names, lods):
                prepare_unity(item, name, unity_name(settings, ""), shared_material)
                if self.auto_lods:
                    shared_material = item.active_material
                move_to_lod_collection(context, item, lod)
            normalize_unity_texture_names(meshes)
            if settings.unity_copy_textures:
                asset_folder = _safe_path_token(unity_name(settings, ""))
                texture_dir = os.path.join(os.path.dirname(bpy.data.filepath), "Textures", asset_folder)
                save_textures(meshes[0], texture_dir)
        except (RuntimeError, ValueError, OSError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if settings.unity_generate_text_labels:
            for item, lod in zip(meshes, lods):
                ensure_unity_label(context, item, int(lod[3:]))
        if settings.unity_auto_increment_index:
            match = re.fullmatch(r"(.*?)(\d+)", settings.unity_asset_index)
            if match:
                prefix, digits = match.groups()
                settings.unity_asset_index = f"{prefix}{int(digits) + 1:0{len(digits)}d}"
        self.report({"INFO"}, f"Prepared {len(meshes)} mesh(es): " + ", ".join(item.name for item in meshes))
        return {"FINISHED"}


class OBJECT_OT_polygroups_rename_unity_meshes(bpy.types.Operator):
    bl_idname = "object.polygroups_rename_unity_meshes"
    bl_label = "Rename Meshes"
    bl_description = "Rename selected meshes preserving their LOD numbers and material slots; copy renamed textures"
    bl_options = {'REGISTER', 'UNDO'}

    assign_missing_lods: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'},
        description='Assign missing LOD numbers by decreasing polygon count')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not bpy.data.filepath:
            self.report({'ERROR'}, 'Save the blend file before copying renamed textures')
            return {'CANCELLED'}
        base = unity_name(settings, '')
        plans = []
        # Legacy Smart LODs used one-based .LOD.1; canonical .LODN is zero-based.
        smart_set = all(obj.get('polygroups_lod_source') and not obj.get('unity_prepared')
                        and re.search(r'\.LOD\.\d+$', obj.name) for obj in meshes)
        resolved = {}
        for obj in meshes:
            match = re.search(r'[._ -]LOD[._ -]?(\d+)(?:\.\d{3})*$', obj.name, re.IGNORECASE)
            resolved[obj] = int(match.group(1)) - int(smart_set) if match else None
        if self.assign_missing_lods:
            used = {lod for lod in resolved.values() if lod is not None}
            depsgraph = context.evaluated_depsgraph_get()
            missing = sorted((obj for obj in meshes if resolved[obj] is None),
                             key=lambda obj: (-polygon_count(obj, depsgraph), obj.name))
            for obj in missing:
                lod = 0
                while lod in used:
                    lod += 1
                resolved[obj] = lod
                used.add(lod)
        for obj in meshes:
            lod = resolved[obj] if resolved[obj] is not None else 0
            plans.append((obj, unity_name(settings, f'LOD{lod}'), lod))
        names = [name for _, name, _ in plans]
        if len(set(names)) != len(names) or any(bpy.data.objects.get(name) not in [None, *meshes] for name in names):
            self.report({'ERROR'}, 'Conflicting mesh names: select one asset with distinct LOD numbers or choose another index')
            return {'CANCELLED'}
        try:
            materials = {mat for obj in meshes for mat in obj.data.materials if mat}
            images = {}
            used = set()
            for material in sorted(materials, key=lambda mat: mat.name):
                for node in texture_nodes(material.node_tree):
                    if node.image in images or _texture_suffix(node.image, node) in {'AlphaMap', 'MergeMask', 'ArtifactMask'}:
                        continue
                    suffix = _texture_suffix(node.image, node)
                    color = node.outputs.get('Color')
                    for link in color.links if color else []:
                        if link.to_node.type == 'NORMAL_MAP':
                            suffix = 'Normal'
                        elif link.to_socket.name in {'Base Color', 'Metallic', 'Roughness'}:
                            suffix = link.to_socket.name.replace(' ', '')
                    target = base if suffix == 'BaseColor' else f'{base}_{suffix.lower()}'
                    candidate, index = target, 2
                    while candidate in used:
                        candidate = f'{target}_{index}'
                        index += 1
                    used.add(candidate)
                    images[node.image] = candidate
                    if node.image.source not in {'FILE', 'GENERATED'} or not node.image.has_data:
                        raise ValueError(f'Texture has no supported loaded pixels: {node.image.name}')
            for obj, _, _ in plans:
                obj.name = '__Unity_Rename__'
            for obj, name, lod in plans:
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                obj.name = obj.data.name = name
                obj['unity_prepared'] = True
                for collection in obj.users_collection:
                    if len(collection.objects) == 1 and collection.name.endswith('_Collection'):
                        collection.name = f'{base}_LOD{lod}_Collection'
                if any(child.get(UNITY_LABEL) for child in obj.children):
                    ensure_unity_label(context, obj, lod)
            for index, material in enumerate(sorted(materials, key=lambda mat: mat.name)):
                material.name = base if index == 0 else f'{base}_Material_{index + 1}'
                material['unity_asset_name'] = base
            for image, name in images.items():
                other = bpy.data.images.get(name)
                if other is not None and other != image:
                    other.name = name + '__Duplicate'
                image.name = name
            normalize_unity_texture_names(meshes)
            directory = os.path.join(os.path.dirname(bpy.data.filepath), 'Textures', base)
            for obj in meshes:
                save_textures(obj, directory)
        except (RuntimeError, ValueError, OSError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Renamed {len(meshes)} meshes; copied {len(images)} textures to {directory}')
        return {'FINISHED'}


class OBJECT_OT_polygroups_fix_unity_textures(bpy.types.Operator):
    bl_idname = "object.polygroups_fix_unity_textures"
    bl_label = "Fix Textures"
    bl_description = "Fix selected assets' texture names and copy textures into their asset folders without renaming meshes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, 'Save the blend file before copying textures')
            return {'CANCELLED'}
        groups = {}
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                clean = re.sub(r'(?:\.\d{3})+$', '', obj.name)
                base = re.sub(r'[._]LOD\d+$', '', clean)
                groups.setdefault(base, []).append(obj)
        # Validate all textures before changing data or writing files.
        try:
            for meshes in groups.values():
                for obj in meshes:
                    for mat in obj.data.materials:
                        if not mat:
                            continue
                        for node in texture_nodes(mat.node_tree):
                            image = node.image
                            if _texture_suffix(image, node) not in {'AlphaMap', 'MergeMask', 'ArtifactMask'} and (
                                    image.source not in {'FILE', 'GENERATED'} or not image.has_data):
                                raise ValueError(f'Texture has no supported loaded pixels: {image.name}')
            fixed = 0
            for base, meshes in groups.items():
                base = _safe_path_token(base)
                # Isolate materials shared with other assets, retaining all slots and links.
                materials = {mat for obj in meshes for mat in obj.data.materials if mat}
                copies = {}
                for mat in materials:
                    external = any(obj.type == 'MESH' and obj not in meshes and mat in tuple(obj.data.materials)
                                   for obj in bpy.data.objects)
                    if external:
                        copies[mat] = mat.copy()
                        isolate_groups(copies[mat].node_tree)
                for obj in meshes:
                    if obj.data.users > 1:
                        obj.data = obj.data.copy()
                    for index, mat in enumerate(tuple(obj.data.materials)):
                        if mat in copies:
                            obj.data.materials[index] = copies[mat]
                images, used = {}, set()
                for obj in meshes:
                    for mat in obj.data.materials:
                        if not mat:
                            continue
                        for node in texture_nodes(mat.node_tree):
                            source = node.image
                            if source in images.values():
                                continue
                            suffix = _texture_suffix(source, node)
                            if suffix in {'AlphaMap', 'MergeMask', 'ArtifactMask'}:
                                continue
                            if source not in images:
                                color = node.outputs.get('Color')
                                for link in color.links if color else []:
                                    if link.to_node.type == 'NORMAL_MAP':
                                        suffix = 'Normal'
                                    elif link.to_socket.name in {'Base Color', 'Metallic', 'Roughness'}:
                                        suffix = link.to_socket.name.replace(' ', '')
                                target = base if suffix == 'BaseColor' else f'{base}_{suffix.lower()}'
                                name, index = target, 2
                                while name in used:
                                    name = f'{target}_{index}'
                                    index += 1
                                used.add(name)
                                # Keep other assets' textures intact when sharing images.
                                external = any(other not in meshes and other.type == 'MESH' and
                                    any(n.image == source for m in other.data.materials if m
                                        for n in texture_nodes(m.node_tree)) for other in bpy.data.objects)
                                image = source
                                if external:
                                    pixels = array('f', [0.0]) * len(source.pixels)
                                    source.pixels.foreach_get(pixels)
                                    image = source.copy()
                                    image.pixels.foreach_set(pixels)
                                    image.update()
                                other = bpy.data.images.get(name)
                                if other is not None and other != image:
                                    other.name = name + '__Duplicate'
                                image.name = name
                                images[source] = image
                                fixed += 1
                            node.image = images[source]
                normalize_unity_texture_names(meshes)
                directory = os.path.join(os.path.dirname(bpy.data.filepath), 'Textures', base)
                for obj in meshes:
                    save_textures(obj, directory)
        except (RuntimeError, ValueError, OSError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Fixed and copied {fixed} textures for {len(groups)} assets')
        return {'FINISHED'}


class OBJECT_OT_polygroups_unity_collection_step(bpy.types.Operator):
    bl_idname = "object.polygroups_unity_collection_step"
    bl_label = "Switch Unity Collections"
    bl_description = "Show all LOD collections of the previous or next asset index and disable the other indices in viewports"
    bl_options = {'REGISTER', 'UNDO'}
    delta: bpy.props.IntProperty(default=1, min=-1, max=1)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        asset = _safe_path_token(asset_name(settings.unity_asset_name), 'Asset')
        suffix = _safe_path_token(settings.unity_asset_suffix.strip(), '')
        pattern = re.compile(r'^' + re.escape(asset) + '(?:_' + re.escape(settings.unity_name_index.zfill(2)) + ')?' + r'_(\d+)'  +
                             (r'_' + re.escape(suffix) if suffix else '') + r'_LOD(\d+)_Collection$')
        groups = {}
        for collection in context.scene.collection.children_recursive:
            match = pattern.fullmatch(collection.name)
            if match:
                groups.setdefault(int(match.group(1)), []).append((collection, match.group(1), int(match.group(2))))
        if not groups:
            self.report({'ERROR'}, f'No LOD collections matching {asset}_Index_LODN_Collection')
            return {'CANCELLED'}
        indices = sorted(groups)
        visible = [index for index in indices if any(not col.hide_viewport for col, _, _ in groups[index])]
        try:
            configured = int(settings.unity_asset_index)
        except ValueError:
            configured = None
        # The visible group is authoritative after navigation; initially use the configured index.
        current = visible[0] if len(visible) == 1 else configured
        if current not in groups and context.active_object:
            current = next((index for index in indices if any(context.active_object in col.all_objects[:]
                            for col, _, _ in groups[index])), None)
        if current in groups:
            position = max(0, min(len(indices) - 1, indices.index(current) + self.delta))
        else:
            position = 0 if self.delta >= 0 else len(indices) - 1
        target = indices[position]
        for index, collections in groups.items():
            for collection, _, _ in collections:
                collection.hide_viewport = index != target
        settings.unity_asset_index = groups[target][0][1]
        context.view_layer.update()
        meshes = [(lod, obj) for col, _, lod in groups[target] for obj in col.all_objects if obj.type == 'MESH']
        if meshes:
            for obj in context.selected_objects:
                obj.select_set(False)
            obj = min(meshes, key=lambda entry: (entry[0], entry[1].name))[1]
            obj.select_set(True)
            context.view_layer.objects.active = obj
        self.report({'INFO'}, f'Visible asset: {asset}_{settings.unity_asset_index}')
        return {'FINISHED'}


class UnityRenderProgressMixin:
    def execute(self, context):
        steps = self._steps(context)
        try:
            next(steps)
        except StopIteration as finished:
            return finished.value
        finally:
            steps.close()

    def invoke(self, context, event):
        from . import turnaround_animation as ta
        if bpy.app.background:
            return self.execute(context)
        if ta._ACTIVE_RENDER_TASK is not None:
            return {'CANCELLED'}
        self._scene = context.scene
        self._settings = self._scene.polygroups_render_settings
        self._window_manager = context.window_manager
        self._area = context.area
        self._cursor_status = 'Export' if self.bl_idname == 'object.polygroups_export_unity' else 'Render'
        self._region = next((r for r in self._area.regions if r.type == 'WINDOW'), None)
        self._mouse_x = event.mouse_x - self._region.x if self._region else 32
        self._mouse_y = event.mouse_y - self._region.y if self._region else 32
        self._frames_done = 0
        self._total_frames = self._progress_total(context)
        self._finished = False
        self._render_completed = False
        self._render_cancelled = False
        self._timer = self._draw_handle = None
        self._render_display_type = context.preferences.view.render_display_type
        self._steps_iterator = self._steps(context, interactive=True)
        self._context = {'window': context.window, 'area': self._area, 'region': self._region,
                         'scene': self._scene, 'view_layer': context.view_layer}
        self._handlers_registered = False
        self._progress_started = False
        try:
            context.preferences.view.render_display_type = 'NONE'
            self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                ta._draw_animation_cursor, (), 'WINDOW', 'POST_PIXEL')
            for handlers, callback in self._handlers():
                handlers.append(callback)
            self._handlers_registered = True
            ta._ACTIVE_RENDER_TASK = self
            self._settings.animation_progress = 0
            self._window_manager.progress_begin(0, 100)
            self._progress_started = True
            self._timer = self._window_manager.event_timer_add(.1, window=context.window)
            self._window_manager.modal_handler_add(self)
            self._start_next()
            if self._finished:
                return self._result
            bpy.app.timers.register(self._watchdog, first_interval=.1)
            return {'RUNNING_MODAL'}
        except Exception as error:
            return self._finish(error=error)

    def _handlers(self):
        return ((bpy.app.handlers.render_post, self._on_render_post),
                (bpy.app.handlers.render_complete, self._on_render_complete),
                (bpy.app.handlers.render_cancel, self._on_render_cancel))

    def _start_next(self):
        self._render_completed = self._render_cancelled = False
        with bpy.context.temp_override(**self._context):
            try:
                job = next(self._steps_iterator)
            except StopIteration as finished:
                self._finish(completed=finished.value == {'FINISHED'})
                return
            self._settings.is_running = True
            self._job_animation = bool(job.get('animation'))
            self._job_start_frames = self._frames_done
            self._job_status = self._settings.animation_status
            self._refresh_progress()
            result = bpy.ops.render.render('INVOKE_DEFAULT', **job)
            if 'RUNNING_MODAL' not in result:
                self._render_completed = 'FINISHED' in result
                self._render_cancelled = not self._render_completed

    def _on_render_post(self, scene, *args):
        if scene == self._scene:
            self._frames_done = min(self._total_frames, self._frames_done + 1)

    def _on_render_complete(self, scene, *args):
        if scene == self._scene:
            self._render_completed = True

    def _on_render_cancel(self, scene, *args):
        if scene == self._scene:
            self._render_cancelled = True

    def _refresh_progress(self):
        from .turnaround_animation import _redraw_animation_ui
        self._settings.animation_progress = 100 * self._frames_done / self._total_frames
        if getattr(self, '_job_animation', False) and not self._render_completed:
            count = self._frames_done - self._job_start_frames
            self._settings.animation_status = f'{self._job_status} {count}/{max(2, int(self._settings.animation_frame_count))}'
        if self._progress_started:
            self._window_manager.progress_update(self._settings.animation_progress)
        _redraw_animation_ui(self._window_manager)

    def _watchdog(self):
        if self._finished:
            return None
        try:
            self._refresh_progress()
            if not bpy.app.is_job_running('RENDER'):
                if self._render_cancelled:
                    self._finish()
                elif self._render_completed:
                    self._start_next()
        except Exception as error:
            self._finish(error=error)
        return None if self._finished else .1

    def _finish(self, completed=False, error=None):
        from . import turnaround_animation as ta
        if self._finished:
            return self._result
        self._finished = True
        self._result = {'FINISHED'} if completed else {'CANCELLED'}
        try:
            with bpy.context.temp_override(**self._context):
                self._steps_iterator.close()
        finally:
            if self._handlers_registered:
                for handlers, callback in self._handlers():
                    if callback in handlers:
                        handlers.remove(callback)
            if self._timer is not None:
                self._window_manager.event_timer_remove(self._timer)
            if self._draw_handle is not None:
                bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, 'WINDOW')
            if self._progress_started:
                self._window_manager.progress_end()
            bpy.context.preferences.view.render_display_type = self._render_display_type
            if ta._ACTIVE_RENDER_TASK is self:
                ta._ACTIVE_RENDER_TASK = None
            self._settings.is_running = False
            if completed:
                self._frames_done = self._total_frames
                self._settings.animation_progress = 100
                self._settings.animation_status = getattr(self, '_completion_status', 'Unity: export/render completed')
            else:
                self._settings.animation_status = f'Unity: render failed: {error}' if error else 'Unity: render cancelled'
            ta._redraw_animation_ui(self._window_manager)
        if error:
            self.report({'ERROR'}, self._settings.animation_status)
        return {'FINISHED'} if completed else {'CANCELLED'}

    def modal(self, context, event):
        if self._finished:
            return self._result
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} and context.area == self._area and self._region:
            self._mouse_x = event.mouse_x - self._region.x
            self._mouse_y = event.mouse_y - self._region.y
            self._area.tag_redraw()
        return {'PASS_THROUGH'}


class OBJECT_OT_polygroups_export_unity(UnityRenderProgressMixin, bpy.types.Operator):
    bl_idname = "object.polygroups_export_unity"
    bl_label = "Export Unity Assets"
    bl_description = "Export prepared Unity meshes as FBX with textures and/or embedded GLTF"
    batch_prepared: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    batch_sort: bpy.props.EnumProperty(items=(('LODS', 'LODs', ''), ('LODS_FORMAT', 'LODs / Format', '')), default='LODS_FORMAT', options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return not context.scene.polygroups_render_settings.is_running and any(obj.type == "MESH" for obj in context.selected_objects)

    def invoke(self, context, event):
        error = validate_unity_arp_selection(context)
        if error:
            context.scene.polygroups_mesh_finalization_settings.unity_export_status = error
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        if not context.scene.polygroups_mesh_finalization_settings.unity_export_all_renders:
            return self.execute(context)
        return UnityRenderProgressMixin.invoke(self, context, event)

    def _progress_total(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        assets = {re.sub(r'\.LOD\d+$', '', obj.name, flags=re.IGNORECASE) for obj in meshes}
        render_meshes = [obj for obj in context.scene.objects if obj.type == 'MESH' and obj.get('unity_prepared') and
                         re.sub(r'\.LOD\d+$', '', obj.name, flags=re.IGNORECASE) in assets]
        rs = context.scene.polygroups_render_settings
        return max(1, len(render_meshes) * (2 if rs.transparent_background else 1) +
                   len(assets) * (4 + max(2, int(rs.animation_frame_count))))

    def _steps(self, context, interactive=False):
        settings = context.scene.polygroups_mesh_finalization_settings
        if getattr(self, 'batch_prepared', False):
            from types import SimpleNamespace
            from .unreal_lod_export import export_lods
            meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
            if settings.unity_use_auto_rig_pro:
                self.report({'ERROR'}, 'Use section 12 Unity Export for rigged Auto-Rig Pro assets')
                return {'CANCELLED'}
            if not settings.unity_export_directory.strip():
                self.report({'ERROR'}, 'Choose a Unity export directory')
                return {'CANCELLED'}
            if settings.unity_export_autosave and 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath):
                return {'CANCELLED'}
            normalize_unity_texture_names(meshes)
            options = SimpleNamespace(mesh_export_fbx=settings.unity_export_fbx,
                mesh_export_glb=settings.unity_export_glb, mesh_export_gltf=settings.unity_export_gltf,
                mesh_export_sort=self.batch_sort, mesh_export_info_format=settings.unity_export_info_format,
                unreal_glb_mode=settings.unity_glb_mode, unreal_gltf_mode=settings.unity_gltf_mode,
                is_property_set=lambda name: True)
            result = export_lods(context, options, self.report, engine='Unity',
                output_root=bpy.path.abspath(settings.unity_export_directory),
                overwrite=settings.unity_export_overwrite or settings.unity_export_clear_asset_folder)
            settings.unity_export_status = 'Prepared model batch exported' if 'FINISHED' in result else 'Prepared model batch export failed'
            return result
        error = validate_unity_arp_selection(context)
        if error:
            settings.unity_export_status = error
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        if settings.unity_export_all_renders and context.scene.camera is None:
            self.report({'ERROR'}, "Set a scene camera before exporting renders")
            return {'CANCELLED'}
        directory = settings.unity_export_directory
        formats = [name for name, enabled in (('FBX', settings.unity_export_fbx), ('GLTF', settings.unity_export_gltf), ('GLB', settings.unity_export_glb)) if enabled]
        if not formats:
            self.report({'ERROR'}, "Enable FBX, GLB or GLTF export")
            return {'CANCELLED'}
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
        if settings.unity_use_auto_rig_pro and settings.unity_export_fbx:
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
        normalize_unity_texture_names(meshes)
        paths = {node.image: node.image.filepath_raw for obj in meshes
                 for mat in obj.data.materials if mat for node in texture_nodes(mat.node_tree)}
        alpha_nodes = {
            node: node.image
            for obj in meshes for mat in obj.data.materials if mat
            for node in texture_nodes(mat.node_tree)
            if _texture_suffix(node.image, node) in {"AlphaMap", "MergeMask", "ArtifactMask"}
        }
        texture_count = len(set(paths) - set(alpha_nodes.values()))
        render_count = video_count = 0
        try:
            if mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            groups = {}
            for obj in meshes:
                asset_name = re.sub(r"\.LOD\d+$", "", obj.name, flags=re.IGNORECASE)
                groups.setdefault(asset_name, []).append(obj)
            for asset_name in groups:
                folder = os.path.join(root, _safe_path_token(asset_name))
                if os.path.exists(folder) and not (settings.unity_export_overwrite or settings.unity_export_clear_asset_folder):
                    raise ValueError(f"Folder already exists: {folder}. Enable Overwrite to replace files")
            if settings.unity_export_clear_asset_folder:
                # Validate every exact asset destination before removing any contents.
                resolved_root = os.path.realpath(root)
                for asset_name in groups:
                    folder = os.path.join(root, _safe_path_token(asset_name))
                    resolved = os.path.realpath(folder)
                    if os.path.dirname(resolved) != resolved_root or os.path.islink(folder):
                        raise ValueError(f'Unsafe asset folder: {folder}')
                    if bpy.data.filepath and os.path.commonpath((resolved, os.path.realpath(bpy.data.filepath))) == resolved:
                        raise ValueError('The asset folder contains the current blend file; choose another export directory')
            if settings.unity_export_autosave:
                if not bpy.data.filepath:
                    raise ValueError('Save the blend file before enabling Autosave Before Start')
                if 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath):
                    raise RuntimeError('Autosave failed; export was not started')
            if settings.unity_export_clear_asset_folder:
                from .unity_reexport import refresh_asset_textures
                for asset_name, lods in groups.items():
                    refresh_asset_textures(lods, asset_name, root)
                # Restore the refreshed source paths after temporary FBX writes.
                paths = {node.image: node.image.filepath_raw for obj in meshes
                         for mat in obj.data.materials if mat for node in texture_nodes(mat.node_tree)}
                if settings.unity_export_autosave:
                    if 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath):
                        raise RuntimeError('Could not save refreshed texture paths')
            alpha_nodes = _detach_export_alpha_maps(meshes)
            for asset_name, lods in groups.items():
                asset_folder = os.path.join(root, _safe_path_token(asset_name))
                for export_format in formats:
                    folder = os.path.join(asset_folder, export_format)
                    os.makedirs(folder, exist_ok=True)
                    # Unity Prepare assigns one common material and texture set to all LODs.
                    if export_format == "FBX":
                        save_textures(lods[0], folder)
                    combined = ((export_format == 'GLTF' and settings.unity_gltf_mode == 'COMBINED') or
                                (export_format == 'GLB' and settings.unity_glb_mode == 'COMBINED'))
                    combined_path = os.path.join(folder, _safe_path_token(asset_name) + '.' + export_format.lower())
                    if combined:
                        bpy.ops.object.select_all(action='DESELECT')
                        for obj in lods:
                            obj.select_set(True)
                        context.view_layer.objects.active = lods[0]
                        with ExitStack() as stack:
                            for obj in lods:
                                stack.enter_context(_export_at_world_origin(obj, context.view_layer))
                            result = (_export_selected_object(combined_path, 'GLB') if export_format == 'GLB'
                                      else _export_gltf_asset(combined_path, True))
                        if 'FINISHED' not in result:
                            raise RuntimeError(f'GLTF export failed: {asset_name}')
                    mesh_info = []
                    for obj in lods:
                        bpy.ops.object.select_all(action="DESELECT")
                        obj.select_set(True)
                        filepath = combined_path if combined else os.path.join(folder, _safe_path_token(obj.name) + '.' + export_format.lower())
                        use_rig = rig is not None and obj.name == asset_name
                        with _export_at_world_origin(obj, context.view_layer, rig if use_rig else None):
                            if combined:
                                result = {'FINISHED'}
                            elif export_format == 'GLB':
                                context.view_layer.objects.active = obj
                                result = _export_selected_object(filepath, 'GLB')
                            elif export_format == "GLTF":
                                context.view_layer.objects.active = obj
                                result = _export_gltf_asset(filepath, False)
                            elif use_rig:
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
                            raise RuntimeError(f"{export_format} export failed: {obj.name}")
                        if settings.unity_export_info_format != "NONE":
                            vertices, triangles = _evaluated_mesh_counts(obj, context.evaluated_depsgraph_get())
                            lod_match = re.search(r"LOD\d+$", obj.name, flags=re.IGNORECASE)
                            mesh_info.append({
                                "lod": lod_match.group(0).upper() if lod_match else "LOD0",
                                "name": obj.name,
                                "file": os.path.basename(filepath),
                                "vertices": vertices,
                                "triangles": triangles,
                            })
                    mesh_info.sort(key=lambda entry: int(entry["lod"][3:]))
                    _write_export_mesh_info(folder, settings.unity_export_info_format, mesh_info, engine='Unity')
                if settings.unity_export_all_renders:
                    rs = context.scene.polygroups_render_settings
                    render_lods = [obj for obj in context.scene.objects if obj.type == 'MESH' and obj.get('unity_prepared') and
                                   re.sub(r'\.LOD\d+$', '', obj.name, flags=re.IGNORECASE) == asset_name]
                    rs.animation_status = f'Unity: rendering LODs - {asset_name}'
                    result = yield from OBJECT_OT_polygroups_render_unity_assets._steps(
                        self, context, interactive=interactive, targets_override=render_lods, force_separate=True,
                        output_directory=os.path.join(asset_folder, f'{_safe_path_token(asset_name)}_LODS'))
                    if result != {'FINISHED'}:
                        return {'CANCELLED'}
                    render_count += len(render_lods) * (2 if rs.transparent_background else 1)
                    source = min(render_lods, key=lambda obj: int(re.search(r'\.LOD(\d+)$', obj.name).group(1))
                                 if re.search(r'\.LOD(\d+)$', obj.name) else 0)
                    bpy.ops.object.select_all(action='DESELECT')
                    source.select_set(True)
                    context.view_layer.objects.active = source
                    rs.animation_status = f'Unity: turnaround - {asset_name}'
                    result = yield from OBJECT_OT_polygroups_render_unity_turnaround._steps(
                        self, context, interactive=interactive, output_directory=asset_folder,
                        video_container=rs.animation_container, asset_name=asset_name)
                    if result != {'FINISHED'}:
                        return {'CANCELLED'}
                    render_count += 4
                    video_count += 1
        except (RuntimeError, ValueError, OSError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        finally:
            _restore_export_alpha_maps(alpha_nodes)
            for image, path in paths.items():
                image.filepath_raw = path
            bpy.ops.object.select_all(action="DESELECT")
            for obj in selected:
                obj.select_set(True)
            context.view_layer.objects.active = active
            if active and mode != "OBJECT":
                bpy.ops.object.mode_set(mode=mode)
        counts = []
        if settings.unity_export_fbx:
            counts.append(f'{len(meshes)} FBX')
        if settings.unity_export_gltf:
            counts.append(f'{len(groups) if settings.unity_gltf_mode == "COMBINED" else len(meshes)} GLTF')
        if settings.unity_export_glb:
            counts.append(f'{len(groups) if settings.unity_glb_mode == "COMBINED" else len(meshes)} GLB')
        self._completion_status = (f'{len(groups)} meshes exported ({len(meshes)} LODs)\n' + ' / '.join(counts) +
            f'\n{texture_count} textures\n{render_count} renders\n{video_count} videos x ' +
            f'{max(2, int(context.scene.polygroups_render_settings.animation_frame_count)) if video_count else 0} frames')
        settings.unity_export_status = self._completion_status
        context.scene.polygroups_render_settings.animation_status = self._completion_status
        self.report({'INFO'}, self._completion_status)
        if not bpy.app.background:
            from ..sound import play_operation_done_sound
            play_operation_done_sound(context)
        return {"FINISHED"}


UNITY_LABEL = "polygroups_unity_label"


def ensure_unity_label(context, obj, index=None):
    from .smart_lods import ensure_lod_label
    match = re.search(r"\.LOD(\d+)$", obj.name)
    index = int(match.group(1)) if index is None and match else (index or 0)
    base = re.sub(r"\.LOD\d+$", "", obj.name)
    return ensure_lod_label(context, obj, base, index, label_tag=UNITY_LABEL,
                            text_size=context.scene.polygroups_mesh_finalization_settings.unity_label_size)


class OBJECT_OT_polygroups_unity_index_step(bpy.types.Operator):
    bl_idname = "object.polygroups_unity_index_step"
    bl_label = "Change Unity Index"
    bl_description = "Change the Unity index by one, preserving its prefix and leading zeros"
    bl_options = {'UNDO', 'INTERNAL'}
    delta: bpy.props.IntProperty(default=1, min=-1, max=1)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        match = re.fullmatch(r"(.*?)(\d+)", settings.unity_asset_index)
        if not match:
            self.report({'WARNING'}, "Index must end with a number")
            return {'CANCELLED'}
        prefix, digits = match.groups()
        settings.unity_asset_index = f"{prefix}{max(0, int(digits) + self.delta):0{len(digits)}d}"
        return {'FINISHED'}


class OBJECT_OT_polygroups_render_unity_assets(bpy.types.Operator):
    bl_idname = "object.polygroups_render_unity_assets"
    bl_label = "Render Unity Assets"
    bl_description = "Auto-frame and render Unity meshes with labels and Freestyle, then restore settings"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.camera and context.active_object and not context.scene.polygroups_render_settings.is_running)

    def execute(self, context):
        steps = self._steps(context)
        try:
            next(steps)
        except StopIteration as finished:
            return finished.value
        finally:
            steps.close()

    def _steps(self, context, interactive=False, output_directory=None, targets_override=None, force_separate=False):
        from .render_queue import _current_state_render_path, image_extension
        settings = context.scene.polygroups_mesh_finalization_settings
        rs = context.scene.polygroups_render_settings
        active = context.active_object
        selected = list(context.selected_objects)
        mode = active.mode
        base = re.sub(r"\.LOD\d+$", "", active.name)
        targets = [o for o in (selected if settings.unity_render_mode == 'SELECTED' else context.scene.objects)
                   if o.type == 'MESH' and o.get('unity_prepared') and
                   (settings.unity_render_mode == 'SELECTED' or re.sub(r"\.LOD\d+$", "", o.name) == base)]
        if targets_override is not None:
            targets = list(targets_override)
        targets.sort(key=lambda o: (int(re.search(r"\.LOD(\d+)$", o.name).group(1)) if re.search(r"\.LOD(\d+)$", o.name) else 0, o.name))
        if not targets:
            self.report({'ERROR'}, "Select a prepared Unity mesh")
            return {'CANCELLED'}
        original = (rs.resolution_x, rs.resolution_y, rs.resolution_scale, rs.freestyle_edges, rs.freestyle_as_render_pass)
        original_format = rs.image_format
        visibility = [(o, o.hide_viewport, o.hide_render, o.hide_get()) for o in targets]
        try:
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            rs.image_format = settings.unity_render_image_format
            separate = force_separate or settings.unity_render_separate or settings.unity_render_mode == 'INDIVIDUAL'
            if separate or settings.unity_render_mode == 'ALL':
                rs.resolution_x = rs.resolution_y = 2048 if separate else 4096
                rs.resolution_scale = 100
            if settings.unity_render_freestyle:
                rs.freestyle_edges = True
            rs.freestyle_as_render_pass = False
            seed = _current_state_render_path()
            directory = output_directory or os.path.join(os.path.dirname(seed), 'Render Unity Assets')
            os.makedirs(directory, exist_ok=True)
            separate = force_separate or settings.unity_render_separate or settings.unity_render_mode == 'INDIVIDUAL'
            batches = [[o] for o in targets] if separate else [targets]
            resolutions = {}
            camera_frames = {}
            mesh_info = []
            for batch in batches:
                for o in context.selected_objects:
                    o.select_set(False)
                for obj in batch:
                    obj.hide_viewport = False
                    obj.hide_set(False)
                    obj.select_set(True)
                    if settings.unity_render_text:
                        ensure_unity_label(context, obj).select_set(True)
                context.view_layer.objects.active = batch[0]
                if separate:
                    asset_base = re.sub(r"\.LOD\d+$", "", batch[0].name)
                    if asset_base not in resolutions:
                        from .render_selected import selected_bounds, fit_render_aspect
                        reference = next((o for o in context.scene.objects if o.type == 'MESH' and
                                          o.get('unity_prepared') and o.name in {asset_base, asset_base + '.LOD0'}), batch[0])
                        reference_objects = [reference]
                        if settings.unity_render_text:
                            reference_objects.append(ensure_unity_label(context, reference))
                        context.view_layer.update()
                        camera = context.scene.camera
                        data, matrix = camera.data, camera.matrix_world.copy()
                        constraints = [(c, c.mute) for c in camera.constraints]
                        render = context.scene.render
                        previous = (render.resolution_x, render.resolution_y, render.pixel_aspect_x, render.pixel_aspect_y)
                        temporary = data.copy()
                        try:
                            camera.data = temporary
                            for constraint, mute in constraints:
                                constraint.mute = True
                            render.pixel_aspect_x = render.pixel_aspect_y = 1
                            rs.resolution_x = rs.resolution_y = 2048
                            reference_bounds = selected_bounds(context, reference_objects)
                            fit_render_aspect(context, camera, *reference_bounds, rs)
                            resolutions[asset_base] = (rs.resolution_x, rs.resolution_y)
                            camera_frames[asset_base] = (camera.matrix_world.copy(), {
                                name: getattr(camera.data, name) for name in
                                ('lens', 'ortho_scale', 'shift_x', 'shift_y', 'clip_start', 'clip_end')}, reference_bounds[1].x)
                        finally:
                            camera.data = data
                            camera.matrix_world = matrix
                            for constraint, mute in constraints:
                                constraint.mute = mute
                            bpy.data.cameras.remove(temporary)
                            render.resolution_x, render.resolution_y, render.pixel_aspect_x, render.pixel_aspect_y = previous
                            context.view_layer.update()
                    rs.resolution_x, rs.resolution_y = resolutions[asset_base]
                name = batch[0].name if separate else base + '_All'
                if separate and not re.search(r"\.LOD\d+$", name):
                    name += '.LOD0'
                camera = context.scene.camera
                camera_data, camera_matrix = camera.data, camera.matrix_world.copy()
                camera_constraints = [(c, c.mute) for c in camera.constraints]
                frame_data = None
                try:
                    if separate:
                        for constraint, mute in camera_constraints:
                            constraint.mute = True
                        frame_data = camera_data.copy()
                        camera.data = frame_data
                        fitted_matrix, fitted_properties, reference_x = camera_frames[asset_base]
                        moved_matrix = fitted_matrix.copy()
                        moved_matrix.translation.x += selected_bounds(context)[1].x - reference_x
                        camera.matrix_world = moved_matrix
                        for attribute, value in fitted_properties.items():
                            setattr(frame_data, attribute, value)
                        context.view_layer.update()
                    path = os.path.join(directory, f"{_safe_path_token(name)}{image_extension(rs.image_format)}")
                    if interactive:
                        from .render_selected import OBJECT_OT_render_selected_auto
                        rs.animation_status = f'Unity LOD: {name}'
                        result = yield from OBJECT_OT_render_selected_auto._steps(
                            self, context, interactive=True, output_path=path,
                            fixed_resolution=separate, fixed_camera=separate)
                    else:
                        result = bpy.ops.object.polygroups_render_selected_auto(
                            output_path=path, fixed_resolution=separate, fixed_camera=separate)
                finally:
                    camera.data = camera_data
                    camera.matrix_world = camera_matrix
                    for constraint, mute in camera_constraints:
                        constraint.mute = mute
                    if frame_data:
                        bpy.data.cameras.remove(frame_data)
                    context.view_layer.update()
                if 'FINISHED' not in result:
                    return {'CANCELLED'}
                if settings.unity_render_mesh_info:
                    for obj in batch:
                        vertices, triangles = _evaluated_mesh_counts(obj, context.evaluated_depsgraph_get())
                        lod_match = re.search(r"LOD\d+$", obj.name, flags=re.IGNORECASE)
                        mesh_info.append({
                            'lod': lod_match.group(0).upper() if lod_match else 'LOD0',
                            'name': obj.name,
                            'file': f'{_safe_path_token(name)}{image_extension(rs.image_format)}',
                            'vertices': vertices,
                            'triangles': triangles,
                        })
            if settings.unity_render_mesh_info:
                _write_export_mesh_info(directory, 'JSON', mesh_info, engine='Unity')
            return {'FINISHED'}
        except (RuntimeError, ValueError, OSError) as error:
            self.report({'ERROR'}, f'Unity render failed: {error}')
            return {'CANCELLED'}
        finally:
            rs.resolution_x, rs.resolution_y, rs.resolution_scale, rs.freestyle_edges, rs.freestyle_as_render_pass = original
            rs.image_format = original_format
            for o, viewport, render, hidden in visibility:
                o.hide_viewport, o.hide_render = viewport, render
                o.hide_set(hidden)
            for o in context.selected_objects:
                o.select_set(False)
            for o in selected:
                o.select_set(True)
            context.view_layer.objects.active = active
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=mode)


class OBJECT_OT_polygroups_render_unity_turnaround(UnityRenderProgressMixin, bpy.types.Operator):
    bl_idname = "object.polygroups_render_unity_turnaround"
    bl_label = "Unity Turnaround: 4 Views + MP4"
    bl_description = "Prepare the active Unity mesh, frame its complete rotation, render four views and an MP4 animation"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and context.active_object.type == 'MESH' and
                    context.active_object.get('unity_prepared') and context.scene.camera and
                    not context.scene.polygroups_render_settings.is_running)

    def execute(self, context):
        steps = self._steps(context)
        try:
            next(steps)
        except StopIteration as finished:
            return finished.value
        finally:
            steps.close()

    def _progress_total(self, context):
        return 4 + max(2, int(context.scene.polygroups_render_settings.animation_frame_count))

    def _steps(self, context, interactive=False, output_directory=None, video_container=None, asset_name=None):
        from math import hypot
        from mathutils import Vector
        from . import render_queue as rq
        from .render_selected import fit_camera
        from .render_studio import position_lights
        scene = context.scene
        rs = scene.polygroups_render_settings
        source = context.active_object
        selected = list(context.selected_objects)
        mode = source.mode
        camera = scene.camera
        matrix, data = camera.matrix_world.copy(), camera.data
        constraints = [(c, c.mute) for c in camera.constraints]
        rq.ensure_render_support_visible(context)
        snapshot = rq._snapshot_visibility()
        frames = (scene.frame_start, scene.frame_end, scene.frame_current)
        properties = ('resolution_x', 'resolution_y', 'resolution_scale', 'animation_media_type',
                      'animation_container', 'output_directory', 'freestyle_edges', 'freestyle_as_render_pass')
        values = {name: getattr(rs, name) for name in properties}
        resolution = (scene.render.resolution_x, scene.render.resolution_y, scene.render.pixel_aspect_x, scene.render.pixel_aspect_y)
        temporary = data.copy()
        saved_freestyle = scene.render.use_freestyle
        light_root, light_matrix = None, None
        collection_name = None
        try:
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            if 'FINISHED' not in bpy.ops.object.polygroups_prepare_turnaround_animation():
                return {'CANCELLED'}
            duplicate = bpy.data.objects.get(rs.animation_object_name)
            if asset_name:
                from .turnaround_animation import TURNAROUND_SOURCE_PROP
                duplicate[TURNAROUND_SOURCE_PROP] = asset_name
            collection_name = rs.animation_collection_name
            context.view_layer.update()
            corners = [duplicate.matrix_world @ Vector(c) for c in duplicate.bound_box]
            radius = max(hypot(p.x, p.y) for p in corners)
            low, high = min(p.z for p in corners), max(p.z for p in corners)
            points = [Vector((x, y, z)) for x in (-radius, radius) for y in (-radius, radius) for z in (low, high)]
            center = Vector((0, 0, (low + high) / 2))
            size = Vector((2 * radius, 2 * radius, high - low))
            camera.data = temporary
            for c, mute in constraints:
                c.mute = True
            light_root, light_matrix = position_lights(context, center)
            rs.resolution_x = rs.resolution_y = 2048
            rs.resolution_scale = 100
            scene.render.resolution_x = scene.render.resolution_y = 2048
            scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
            fit_camera(context, camera, points, center, size)
            rs.output_directory = output_directory or os.path.join(os.path.dirname(rq._current_state_render_path()), 'Render Unity Assets')
            rs.animation_media_type = 'VIDEO'
            rs.animation_container = video_container or 'MPEG4'
            rs.freestyle_edges = False
            rs.freestyle_as_render_pass = False
            scene.render.use_freestyle = False
            if interactive:
                from .turnaround_animation import unity_turnaround_render_steps
                yield from unity_turnaround_render_steps(context)
                return {'FINISHED'}
            if 'FINISHED' not in bpy.ops.object.polygroups_render_turnaround_views():
                return {'CANCELLED'}
            rs.resolution_x = rs.resolution_y = 1024
            scene.render.resolution_x = scene.render.resolution_y = 1024
            return bpy.ops.object.polygroups_render_turnaround_animation('EXEC_DEFAULT')
        except Exception as error:
            self.report({'ERROR'}, f'Unity turnaround failed: {error}')
            return {'CANCELLED'}
        finally:
            camera.data = data
            scene.render.use_freestyle = saved_freestyle
            camera.matrix_world = matrix
            for c, mute in constraints:
                c.mute = mute
            bpy.data.cameras.remove(temporary)
            if light_root:
                light_root.matrix_world = light_matrix
            rq._restore_visibility(snapshot)
            if collection_name:
                from .turnaround_animation import remove_turnaround_collection
                remove_turnaround_collection(context, collection_name)
            for name, value in values.items():
                setattr(rs, name, value)
            scene.render.resolution_x, scene.render.resolution_y, scene.render.pixel_aspect_x, scene.render.pixel_aspect_y = resolution
            scene.frame_start, scene.frame_end = frames[:2]
            scene.frame_set(frames[2])
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in selected:
                obj.select_set(True)
            context.view_layer.objects.active = source
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=mode)
            context.view_layer.update()
