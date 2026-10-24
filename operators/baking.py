import os
import re
from array import array

import bpy
import blf
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core.generated_index import bake_output_name, fix_object_generated_index
from ..localization import t
from ..core.bake_projection import ProjectionSession, invalidate as _invalidate_artifact_mask, current_mask, save_mask_png, seal_mask


from .bake_constants import (
    AUTO_CAGE_INTERSECTION_EPSILON,
    BAKE_ALPHA_IMAGE_PROP,
    BAKE_ALPHA_NODE,
    BAKE_ARTIFACT_IMAGE_PROP,
    BAKE_BASE_COLOR_IMAGE_PROP,
    BAKE_BASE_COLOR_NODE,
    BAKE_MATERIAL_NAME,
    BAKE_MERGED_ALPHA_IMAGE_PROP,
    BAKE_MERGED_BASE_COLOR_IMAGE_PROP,
    BAKE_MERGED_MATERIAL_PROP,
    BAKE_MERGED_NORMAL_IMAGE_PROP,
    BAKE_NORMAL_IMAGE_PROP,
    BAKE_NORMAL_NODE,
    BAKE_PACK_NAME_PROP,
    BAKE_PACK_OBJECTS_PROP,
    BAKE_PACK_TYPE_MERGED,
    BAKE_PACK_TYPE_PROP,
    BAKE_SOURCE_ALPHA_IMAGE_PROP,
    BAKE_SOURCE_BASE_COLOR_IMAGE_PROP,
    BAKE_SOURCE_NORMAL_IMAGE_PROP,
    BAKE_TARGET_MATERIAL_PROP,
    BAKE_TEMP_IMAGE_PREFIX,
)
from .bake_cage import (
    _apply_auto_cage_if_enabled,
    _evaluated_mesh,
    _highpoly_sample_points,
    _lowpoly_bvh,
    _mesh_world_diagonal,
    _percentile,
    _world_vertices,
    calculate_auto_cage,
)
from .bake_images import (
    _alpha_map_pixels,
    _apply_bake_background,
    _bake_data_name,
    _bake_pack_data_name,
    _connected_texture_nodes,
    _coverage_from_image,
    _coverage_from_pixels,
    _ensure_bake_material,
    _ensure_output_image,
    _ensure_target_bake_material,
    _ensure_target_image,
    _extend_background_rgb,
    _fill_normal_background,
    _finalize_bake_images,
    _find_bake_image,
    _find_current_bake_image,
    _find_material_bake_image,
    _find_object_bake_image,
    _find_object_source_bake_image,
    _image_from_object_prop,
    _image_is_readable,
    _image_matches_resolution,
    _image_resolution,
    _is_merged_image,
    _is_merged_material,
    _make_image,
    _principled_bsdf,
    _read_image_pixels,
    _safe_path_name,
    _save_image_as_png,
    _selected_bake_targets,
    _set_polygroup_material_texture_only,
    _target_bake_material,
    _write_pixels,
)
from .bake_geometry import (
    _fill_cage_area_inside_mesh,
    _generate_legacy_geometric_artifact_mask,
    _inside_closed_mesh,
    _inside_open_mesh_estimate,
    _paint_intersection,
    _segment_triangle_hit,
    _triangle_intersection_points,
)
from .bake_merge import (
    _assign_material_to_object,
    _bake_temp_images,
    _collect_bake_texture_packs,
    _count_unreadable_pack_images,
    _ensure_merged_material,
    _merge_base_color_pixels,
    _merge_normal_pixels,
    _merge_pack_coverage,
    _merged_pack_name,
    _normal_to_vector,
    _normalized_to_color,
    _pack_coverage,
    _pack_resolution,
    _tag_merged_image,
    _validate_pack_resolutions,
)


_BAKE_CURSOR_HANDLE = None
_BAKE_CURSOR_POSITION = (32, 32)


def _redraw_bake_ui(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _draw_bake_cursor_status():
    context = bpy.context
    scene = getattr(context, "scene", None)
    settings = getattr(scene, "polygroups_baking_settings", None) if scene else None
    if settings is None or not settings.bake_task_is_running:
        return
    x, y = _BAKE_CURSOR_POSITION
    font_id = 0
    blf.position(font_id, x + 18, y + 18, 0)
    blf.size(font_id, 16)
    blf.color(font_id, 1.0, 0.85, 0.25, 1.0)
    blf.draw(font_id, f"Bake {settings.bake_task_progress:.0f}%")


def _active_mesh(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    return obj


def _source_meshes(context, target):
    return [
        obj
        for obj in context.selected_objects
        if obj != target and obj.type == "MESH" and not obj.get("polygroups_smart_cage")
    ]


def _auto_pack_target_uvs(context, target, settings, report, force=False):
    if not force and not settings.auto_pack_uv_before_bake:
        return True
    if not hasattr(context.scene, "uvpm4_props"):
        report({"ERROR"}, "Auto Pack UV requires UVPackmaster 4")
        return False
    pack_operator = getattr(getattr(bpy.ops, "uvpackmaster4", None), "pack", None)
    if pack_operator is None:
        report({"ERROR"}, "UVPackmaster 4 is not enabled")
        return False

    selected_before = list(context.selected_objects)
    active_before = context.view_layer.objects.active
    if target.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    context.view_layer.objects.active = target
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
    bpy.ops.mesh.reveal()
    bpy.ops.mesh.select_all(action="SELECT")

    main_props = context.scene.uvpm4_props.default_main_props
    if hasattr(main_props, "heuristic_max_wait_time") and main_props.heuristic_max_wait_time <= 0:
        main_props.heuristic_max_wait_time = 3
    try:
        result = pack_operator("EXEC_DEFAULT", mode_id="__active__", pack_op_type="0")
    except Exception as error:
        report({"ERROR"}, f"UVPackmaster packing failed: {error}")
        return False
    finally:
        if target.mode == "EDIT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        for obj in selected_before:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if active_before is not None and active_before.name in bpy.data.objects:
            context.view_layer.objects.active = active_before
    if "FINISHED" not in result:
        report({"ERROR"}, "UVPackmaster packing was not completed")
        return False
    return True


def _generate_bake_artifact_mask(context, target, sources, settings, session=None):
    """Synchronous executor of the same diagnostic stages used by BakeTask."""
    if not settings.bake_artifact_mask:
        return None
    try:
        if session is None:
            _configure_bake_settings(context, settings, 'NORMAL')
            normal = bpy.data.images.get(target.get(BAKE_NORMAL_IMAGE_PROP, ''))
            session = ProjectionSession(context, target, sources, settings, normal)
        for kind in session.passes():
            bake_type = session.prepare(kind)
            if bpy.ops.object.bake(type=bake_type) != {'FINISHED'}:
                raise RuntimeError(kind + ' diagnostic bake cancelled')
            session.complete()
        return session.result()
    except Exception:
        _invalidate_artifact_mask(target)
        raise
    finally:
        if session is not None:
            session.close()


def _run_normal_and_artifact(context, target, sources, settings, normal_node):
    session = None
    try:
        if settings.bake_artifact_mask:
            _configure_bake_settings(context, settings, 'NORMAL')
            session = ProjectionSession(context, target, sources, settings, normal_node.image, read_normal=False)
        if settings.bake_normal:
            if session:
                session.watch()
            _bake_to_node(context, target, normal_node, 'NORMAL', settings)
            if session:
                session.capture_normal()
        if session:
            _generate_bake_artifact_mask(context, target, sources, settings, session=session)
            return session.repair
    except Exception:
        _invalidate_artifact_mask(target)
        raise
    finally:
        if session:
            session.close()


def _finalize_with_artifact_autofill(target, settings, repair, report):
    try:
        _finalize_bake_images(target, settings)
        if repair is not None:
            repair.apply(report)
        seal_mask(target)
    except Exception:
        _invalidate_artifact_mask(target)
        raise


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


def _disable_highpoly_sources_after_bake(settings, sources):
    """Optionally disable completed bake sources in viewports only."""
    if not settings.disable_highpoly_after_bake:
        return
    for obj in sources:
        obj.hide_viewport = True


def _auto_fix_selected_generated_indices(context, settings):
    if not settings.auto_fix_generated_index:
        return 0
    return sum(
        1
        for obj in context.selected_objects
        if obj.type == "MESH" and fix_object_generated_index(obj)
    )


def _isolate_bake_render_objects(target, sources):
    """Temporarily allow only the bake target and sources to render."""
    keep = {target, *sources}
    snapshot = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        snapshot[obj] = obj.hide_render
        obj.hide_render = obj not in keep
    return snapshot


def _restore_bake_render_objects(snapshot):
    for obj, hidden in snapshot.items():
        try:
            if obj.name in bpy.data.objects:
                obj.hide_render = hidden
        except ReferenceError:
            pass


def _configure_bake_settings(context, settings, bake_type):
    scene = context.scene
    scene.render.engine = "CYCLES"
    if hasattr(scene, "cycles"):
        scene.cycles.bake_type = bake_type

    bake = scene.render.bake
    bake.use_selected_to_active = settings.use_selected_to_active
    bake.cage_extrusion = settings.cage_extrusion
    smart = getattr(settings, "autogenerate_smart_cage", False)
    bake.use_cage = bool(smart and settings.use_selected_to_active)
    bake.cage_object = settings.smart_cage_object if bake.use_cage else None
    bake.max_ray_distance = settings.ray_distance
    bake.margin = settings.bake_margin
    if hasattr(bake, "margin_type"):
        bake.margin_type = "EXTEND"
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
    if not settings.use_selected_to_active:
        _select_sources_and_target(context, [], target)
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


class OBJECT_OT_polygroups_calculate_auto_cage(bpy.types.Operator):
    bl_idname = "object.polygroups_calculate_auto_cage"
    bl_label = "Calculate AutoCage"
    bl_description = "Calculate cage extrusion from selected highpoly meshes and the active lowpoly mesh"
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

        try:
            result = calculate_auto_cage(context, target, sources, settings)
        except ValueError as error:
            settings.auto_cage_status = f"AutoCage failed: {error}"
            self.report({"WARNING"}, settings.auto_cage_status)
            return {"CANCELLED"}

        settings.cage_extrusion = result["cage"]
        settings.auto_cage_status = (
            f"Cage {result['cage']:.5f} m | Coverage {result['coverage']:.1f}% | "
            f"Safe {result['safe_zone']:.1f}% | Outliers {result['outliers']} | "
            f"Intersections {result['intersections']}"
        )
        self.report({"INFO"}, settings.auto_cage_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_save_blend_file(bpy.types.Operator):
    bl_idname = "object.polygroups_save_blend_file"
    bl_label = "Save Blend File"
    bl_description = "Save the current blend file; opens Save As if it has not been saved yet"
    bl_options = {"REGISTER"}

    def execute(self, context):
        del context
        if bpy.data.filepath:
            result = bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
            if "FINISHED" in result:
                self.report({"INFO"}, "Saved blend file")
            return result

        return bpy.ops.wm.save_as_mainfile("INVOKE_DEFAULT")


class OBJECT_OT_polygroups_save_blend_file_as(bpy.types.Operator):
    bl_idname = "object.polygroups_save_blend_file_as"
    bl_label = "Save Blend File As"
    bl_description = "Choose where to save the current blend file before saving baked textures"
    bl_options = {"REGISTER"}

    def execute(self, context):
        del context
        return bpy.ops.wm.save_as_mainfile("INVOKE_DEFAULT")


class OBJECT_OT_polygroups_save_bake_textures(bpy.types.Operator):
    bl_idname = "object.polygroups_save_bake_textures"
    bl_label = "Save Textures"
    bl_description = "Save baked Base Color, Normal, and Alpha images next to the blend file"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        settings = context.scene.polygroups_baking_settings
        target = _active_mesh(context)
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the blend file first")
            return {"CANCELLED"}

        active_material = target.active_material
        is_merged = _is_merged_material(active_material)
        if is_merged:
            pack_name = active_material.get(BAKE_PACK_NAME_PROP, f"{target.name} Merged")
            output_name = _safe_path_name(pack_name)
            base_image = _find_material_bake_image(active_material, BAKE_BASE_COLOR_NODE)
            normal_image = _find_material_bake_image(active_material, BAKE_NORMAL_NODE)
            alpha_image = _find_material_bake_image(active_material, BAKE_ALPHA_NODE)
        else:
            output_name = _safe_path_name(bake_output_name(target))
            base_image = _find_current_bake_image(
                target,
                BAKE_BASE_COLOR_NODE,
                BAKE_BASE_COLOR_IMAGE_PROP,
            )
            normal_image = _find_current_bake_image(
                target,
                BAKE_NORMAL_NODE,
                BAKE_NORMAL_IMAGE_PROP,
            )
            alpha_image = _find_current_bake_image(
                target,
                BAKE_ALPHA_NODE,
                BAKE_ALPHA_IMAGE_PROP,
            )

        artifact_image = None
        if is_merged:
            if settings.bake_artifact_mask:
                self.report({'WARNING'}, 'Projection masks for merged atlases are unsupported; save each original mesh mask')
        else:
            try:
                artifact_image = current_mask(target, normal_image) if settings.bake_artifact_mask else None
            except ValueError as error:
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}
            if settings.bake_artifact_mask and artifact_image is None and target.get('polygroups_projection_run'):
                self.report({'ERROR'}, 'No current projection mask; bake again or disable Artifact Mask before saving')
                return {'CANCELLED'}

        if base_image is None and normal_image is None and alpha_image is None and artifact_image is None:
            self.report({"WARNING"}, "No bake images found on the active mesh")
            return {"CANCELLED"}

        blend_dir = os.path.dirname(bpy.data.filepath)
        output_dir = os.path.join(blend_dir, "Bakes", output_name)
        os.makedirs(output_dir, exist_ok=True)

        saved_paths = []
        if base_image is not None:
            filepath = os.path.join(output_dir, f"{output_name}_Bake_BaseColor.png")
            _save_image_as_png(base_image, filepath)
            saved_paths.append(filepath)

        if normal_image is not None:
            filepath = os.path.join(output_dir, f"{output_name}_Bake_Normal.png")
            _save_image_as_png(normal_image, filepath)
            saved_paths.append(filepath)

        if alpha_image is not None:
            filepath = os.path.join(output_dir, f"{output_name}_Bake_MergeMask.png")
            _save_image_as_png(alpha_image, filepath)
            saved_paths.append(filepath)

        if artifact_image is not None:
            filepath = os.path.join(output_dir, f"{output_name}_Bake_ArtifactMask.png")
            try:
                save_mask_png(artifact_image, filepath)
            except Exception as error:
                self.report({'ERROR'}, f'Artifact PNG verification/save failed: {error}')
                return {'CANCELLED'}
            saved_paths.append(filepath)

        self.report({"INFO"}, f"Saved {len(saved_paths)} texture(s) to {output_dir}")
        return {"FINISHED"}


class OBJECT_OT_polygroups_restore_textures(bpy.types.Operator):
    bl_idname = "object.polygroups_restore_textures"
    bl_label = "Restore Textures"
    bl_description = "Save connected material textures of selected objects to Bakes, overwrite files and reconnect saved images"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_baking_settings
        return bool(context.selected_objects) and not settings.bake_task_is_running

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the blend file first")
            return {"CANCELLED"}
        materials = {slot.material for obj in context.selected_objects
                     for slot in obj.material_slots if slot.material is not None}
        images = {}
        for material in materials:
            for node in _connected_texture_nodes(material.node_tree):
                images.setdefault(node.image, set()).add(node)
        if not images:
            self.report({"WARNING"}, "No connected material textures found on selected objects")
            return {"CANCELLED"}
        output_dir = os.path.join(os.path.dirname(bpy.data.filepath), "Bakes")
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        saved = 0
        failures = []
        used_names = set()
        for image, nodes in sorted(images.items(), key=lambda item: item[0].name):
            stem = _safe_path_name(os.path.splitext(image.name)[0])
            filename = stem + ".png"
            suffix = 2
            while filename.casefold() in used_names:
                filename = f"{stem}_{suffix}.png"
                suffix += 1
            used_names.add(filename.casefold())
            filepath = os.path.join(output_dir, filename)
            old_path, old_format = image.filepath_raw, image.file_format
            try:
                if image.source not in {"FILE", "GENERATED"} or not image.has_data:
                    raise ValueError("Image has no available pixels or is not a single texture")
                _save_image_as_png(image, filepath)
                if image.packed_file is not None:
                    image.unpack(method="REMOVE")
                image.source = "FILE"
                for node in nodes:
                    node.image = image
                saved += 1
            except Exception as error:
                image.filepath_raw, image.file_format = old_path, old_format
                failures.append(f"{image.name}: {error}")
        if failures:
            self.report({"WARNING"}, "; ".join(failures))
        self.report({"INFO"}, f"Restored {saved} texture(s) to {output_dir}")
        return {"FINISHED"} if saved else {"CANCELLED"}


class OBJECT_OT_polygroups_merge_bake_textures(bpy.types.Operator):
    bl_idname = "object.polygroups_merge_bake_textures"
    bl_label = "Merge Materials/Textures"
    bl_description = "Merge baked Base Color and Normal maps using their separate baked Alpha maps"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = _active_mesh(context)
        return target is not None and len(_selected_bake_targets(context)) >= 2

    def execute(self, context):
        target = _active_mesh(context)
        settings = context.scene.polygroups_baking_settings
        objects = _selected_bake_targets(context)
        if any(obj.get(BAKE_ARTIFACT_IMAGE_PROP) for obj in objects):
            self.report({'WARNING'}, 'Merged projection masks are unsupported; save masks from each original mesh')
        packs = _collect_bake_texture_packs(objects, settings)
        if len(packs) < 2:
            self.report({"WARNING"}, "Select at least two objects with baked textures and Alpha maps")
            return {"CANCELLED"}

        resolution = _validate_pack_resolutions(packs)
        if resolution is None:
            self.report({"ERROR"}, "Selected bake textures must be loaded and have the same resolution")
            return {"CANCELLED"}

        base_pixels = _merge_base_color_pixels(packs, resolution)
        normal_pixels = _merge_normal_pixels(packs, resolution)
        merged_coverage = _merge_pack_coverage(packs, resolution)
        base_pixels = _apply_bake_background(
            base_pixels, merged_coverage, resolution, settings.bake_background_mode,
        )
        normal_pixels = _fill_normal_background(normal_pixels, merged_coverage)

        pack_objects = [pack["object"] for pack in packs]
        pack_name = _merged_pack_name(pack_objects)

        base_image = _ensure_output_image(
            _bake_pack_data_name(settings, pack_name, "Merged_BaseColor"),
            resolution,
            "sRGB",
            (0.0, 0.0, 0.0, 0.0),
        )
        normal_image = _ensure_output_image(
            _bake_pack_data_name(settings, pack_name, "Merged_Normal"),
            resolution,
            "Non-Color",
            (0.5, 0.5, 1.0, 1.0),
        )
        alpha_image = _ensure_output_image(
            _bake_pack_data_name(settings, pack_name, "Merged_MergeMask"),
            resolution,
            "Non-Color",
            (0.0, 0.0, 0.0, 1.0),
        )
        _write_pixels(base_image, base_pixels)
        _write_pixels(normal_image, normal_pixels)
        _write_pixels(alpha_image, _alpha_map_pixels(merged_coverage))
        _tag_merged_image(base_image, pack_name)
        _tag_merged_image(normal_image, pack_name)
        _tag_merged_image(alpha_image, pack_name)

        material = _ensure_merged_material(
            pack_name, base_image, normal_image, alpha_image, pack_objects,
        )
        for obj in pack_objects:
            obj[BAKE_MERGED_BASE_COLOR_IMAGE_PROP] = base_image.name
            obj[BAKE_MERGED_NORMAL_IMAGE_PROP] = normal_image.name
            obj[BAKE_MERGED_ALPHA_IMAGE_PROP] = alpha_image.name
            _assign_material_to_object(obj, material)
        target.active_material = material

        skipped = len(objects) - len(packs)
        message = f"Merged {len(packs)} texture pack(s) into {pack_name}"
        if skipped:
            message += f", skipped {skipped} object(s)"
        unreadable_images = _count_unreadable_pack_images(packs, resolution)
        if unreadable_images:
            message += f", ignored {unreadable_images} unreadable image(s)"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_bake_temp_images(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_bake_temp_images"
    bl_label = "Clear All Bake Images"
    bl_description = "Delete all Bake_Temp images from the current blend file"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_bake_temp_images())

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=440,
            confirm_text="Clear All Bake Images",
        )

    def draw(self, context):
        images = _bake_temp_images()
        layout = self.layout
        layout.label(text="This will delete temporary bake images from the blend file.", icon="ERROR")
        layout.label(text=f"Images found: {len(images)}")
        layout.label(text="Only images starting with Bake_Temp_ will be removed.")

    def execute(self, context):
        images = _bake_temp_images()
        if not images:
            self.report({"INFO"}, "No Bake_Temp images found")
            return {"CANCELLED"}

        removed_count = 0
        for image in images:
            bpy.data.images.remove(image)
            removed_count += 1

        self.report({"INFO"}, f"Removed {removed_count} Bake_Temp image(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_bake_task(bpy.types.Operator):
    bl_idname = "object.polygroups_bake_task"
    bl_label = "Bake Task"
    bl_description = "Run selected-to-active baking as a staged task with progress feedback"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    prepare_materials: bpy.props.BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_baking_settings
        target = _active_mesh(context)
        return not settings.bake_task_is_running and target is not None and bool(_source_meshes(context, target))

    def _set_status(self, context, stage, progress, message):
        settings = context.scene.polygroups_baking_settings
        settings.bake_task_stage = stage
        settings.bake_task_progress = progress
        settings.bake_task_message = message
        context.window_manager.progress_update(progress)
        _redraw_bake_ui(context)

    def _finish(self, context, success, message, cancelled=False):
        global _BAKE_CURSOR_HANDLE
        settings = context.scene.polygroups_baking_settings
        self.artifact_repair = None
        projection = getattr(self, 'projection', None)
        if projection is not None:
            projection.close()
            self.projection = None
        if not success:
            _invalidate_artifact_mask(self.target)
        settings.bake_task_is_running = False
        settings.bake_task_stage = "DONE" if success else ("CANCELLED" if cancelled else "FAILED")
        settings.bake_task_progress = 100.0 if success else (0.0 if cancelled else settings.bake_task_progress)
        settings.bake_task_message = message
        _restore_bake_render_objects(getattr(self, "render_visibility", {}))
        self.render_visibility = {}
        if success:
            _disable_highpoly_sources_after_bake(settings, self.sources)
        if getattr(self, "_timer", None) is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        if _BAKE_CURSOR_HANDLE is not None:
            bpy.types.SpaceView3D.draw_handler_remove(_BAKE_CURSOR_HANDLE, "WINDOW")
            _BAKE_CURSOR_HANDLE = None
        context.window_manager.progress_end()
        _redraw_bake_ui(context)
        self.report({"INFO" if success or cancelled else "ERROR"}, message)
        return {"FINISHED" if success else "CANCELLED"}

    def _launch_pass(self, context, node, bake_type):
        _set_active_bake_node(self.target, node)
        _configure_bake_settings(context, self.settings, bake_type)
        if not self.settings.use_selected_to_active:
            _select_sources_and_target(context, [], self.target)
        if bpy.app.background:
            return bpy.ops.object.bake(type=bake_type)
        return bpy.ops.object.bake("INVOKE_DEFAULT", type=bake_type)

    def _step(self, context):
        if self.stage == "FIX_INDEX":
            fixed = _auto_fix_selected_generated_indices(context, self.settings)
            self._set_status(context, self.stage, 8, f"Fixing Generated.N indices ({fixed} changed)")
            self.stage = "PACK_UV"
        elif self.stage == "PACK_UV":
            if self.settings.auto_pack_uv_before_bake:
                self._set_status(context, self.stage, 12, "Packing lowpoly UVs with UVPackmaster")
                if not _auto_pack_target_uvs(context, self.target, self.settings, self.report):
                    return self._finish(context, False, "UV packing before bake failed")
            self.stage = "PREPARE_MATERIALS" if self.prepare_materials else "PREPARE_MESH"
        elif self.stage == "PREPARE_MATERIALS":
            changed = 0
            for obj in self.sources:
                for material in obj.data.materials:
                    if _set_polygroup_material_texture_only(material):
                        changed += 1
            self._set_status(context, self.stage, 20, f"Preparing materials ({changed} changed)")
            self.stage = "PREPARE_MESH"
        elif self.stage == "PREPARE_MESH":
            self._set_status(context, self.stage, 32, "Preparing lowpoly mesh and AutoCage")
            if self.target.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            if not _apply_auto_cage_if_enabled(context, self.target, self.sources, self.settings, self.report):
                return self._finish(context, False, "Cage preparation failed")
            self.material, self.base_node, self.normal_node = _ensure_bake_material(self.target, self.settings)
            _invalidate_artifact_mask(self.target)
            self.target.active_material = self.material
            _select_sources_and_target(context, self.sources, self.target)
            self.stage = "BASE_READY" if self.settings.bake_base_color else "NORMAL_READY"
        elif self.stage == "BASE_READY":
            self._set_status(context, self.stage, 42, "Baking Base Color")
            self.stage = "BASE_LAUNCH"
        elif self.stage == "BASE_LAUNCH":
            result = self._launch_pass(context, self.base_node, "DIFFUSE")
            if "CANCELLED" in result:
                return self._finish(context, False, "Base Color bake cancelled")
            self.wait_ticks = 2
            self.stage = "BASE_WAIT"
        elif self.stage == "BASE_WAIT":
            self.wait_ticks -= 1
            if self.wait_ticks <= 0 and not bpy.app.is_job_running("OBJECT_BAKE"):
                self._set_status(context, self.stage, 65, "Base Color bake complete")
                self.stage = "NORMAL_READY"
        elif self.stage == "NORMAL_READY":
            if not self.settings.bake_normal:
                self.stage = "ARTIFACT_START"
            else:
                self._set_status(context, self.stage, 68, "Baking Normal")
                self.stage = "NORMAL_LAUNCH"
        elif self.stage == "NORMAL_LAUNCH":
            if self.settings.bake_artifact_mask:
                _configure_bake_settings(context, self.settings, 'NORMAL')
                self.projection = ProjectionSession(context, self.target, self.sources, self.settings, self.normal_node.image, read_normal=False)
                self.projection.watch()
            result = self._launch_pass(context, self.normal_node, "NORMAL")
            if "CANCELLED" in result:
                return self._finish(context, False, "Normal bake cancelled")
            self.wait_ticks = 2
            self.stage = "NORMAL_WAIT"
        elif self.stage == "NORMAL_WAIT":
            self.wait_ticks -= 1
            if self.wait_ticks <= 0 and not bpy.app.is_job_running("OBJECT_BAKE"):
                if getattr(self, 'projection', None):
                    self.projection.capture_normal()
                self._set_status(context, self.stage, 90, "Normal bake complete")
                self.stage = "ARTIFACT_START"
        elif self.stage == 'ARTIFACT_START':
            if not self.settings.bake_artifact_mask:
                self.stage = 'POSTPROCESS'
            else:
                if getattr(self, 'projection', None) is None:
                    _configure_bake_settings(context, self.settings, 'NORMAL')
                    self.projection = ProjectionSession(context, self.target, self.sources, self.settings, self.normal_node.image)
                self.diagnostic_passes = list(self.projection.passes())
                self.stage = 'ARTIFACT_LAUNCH'
        elif self.stage == 'ARTIFACT_LAUNCH':
            kind = self.diagnostic_passes[0]
            self._set_status(context, kind + '_COVERAGE', 90 if kind != 'UV' else 92, 'Projection diagnostics: ' + kind)
            bake_type = self.projection.prepare(kind)
            result = bpy.ops.object.bake(type=bake_type) if bpy.app.background else bpy.ops.object.bake('INVOKE_DEFAULT', type=bake_type)
            if 'CANCELLED' in result:
                return self._finish(context, False, 'Projection diagnostic bake cancelled')
            self.wait_ticks = 2
            self.stage = 'ARTIFACT_WAIT'
        elif self.stage == 'ARTIFACT_WAIT':
            self.wait_ticks -= 1
            if self.wait_ticks <= 0 and not bpy.app.is_job_running('OBJECT_BAKE'):
                self.projection.complete()
                self.diagnostic_passes.pop(0)
                self.stage = 'ARTIFACT_LAUNCH' if self.diagnostic_passes else 'ARTIFACT_CLASSIFY'
        elif self.stage == 'ARTIFACT_CLASSIFY':
            self._set_status(context, self.stage, 93, 'Classifying reversed normals and ray misses')
            image, metadata = self.projection.result()
            if metadata['overlaps']:
                self.report({'WARNING'}, 'Overlapping UVs: projection ownership is ambiguous')
            self.artifact_repair = self.projection.repair
            self.projection.close()
            self.projection = None
            self.stage = 'POSTPROCESS'
        elif self.stage == "POSTPROCESS":
            self._set_status(context, self.stage, 93, "Creating Alpha map and filling background")
            if getattr(self, 'artifact_repair', None) is not None:
                self._set_status(context, 'AUTOFILL', 94, 'Filling masked Normal and Base Color pixels')
            _finalize_with_artifact_autofill(self.target, self.settings, getattr(self, 'artifact_repair', None), self.report)
            self.artifact_repair = None
            self.stage = "SAVE"
        elif self.stage == "SAVE":
            self._set_status(context, self.stage, 95, "Saving bake textures")
            if self.prepare_materials and self.settings.auto_save_textures_after_bake:
                bpy.ops.object.polygroups_save_bake_textures()
            self.stage = "FINALIZE"
        elif self.stage == "FINALIZE":
            self._set_status(context, self.stage, 99, "Finalizing bake")
            return self._finish(context, True, "Bake finished")
        return None

    def invoke(self, context, event):
        global _BAKE_CURSOR_HANDLE, _BAKE_CURSOR_POSITION
        self.settings = context.scene.polygroups_baking_settings
        if not self.settings.bake_base_color and not self.settings.bake_normal:
            self.report({"WARNING"}, "Enable at least one bake pass")
            return {"CANCELLED"}
        self.target = _active_mesh(context)
        self.sources = _source_meshes(context, self.target)
        self.render_visibility = _isolate_bake_render_objects(self.target, self.sources)
        self.stage = "FIX_INDEX"
        self.wait_ticks = 0
        self.artifact_repair = None
        self.cancel_requested = False
        self.settings.bake_task_is_running = True
        self.settings.bake_task_stage = "STARTING"
        self.settings.bake_task_progress = 1.0
        self.settings.bake_task_message = "Starting bake task"
        if event is not None:
            _BAKE_CURSOR_POSITION = (event.mouse_region_x, event.mouse_region_y)
        context.window_manager.progress_begin(0, 100)
        if bpy.app.background:
            try:
                while self.settings.bake_task_is_running:
                    result = self._step(context)
                    if result is not None:
                        return result
            except Exception as error:
                return self._finish(context, False, f"Bake failed: {error}")
            return {"FINISHED"}
        _BAKE_CURSOR_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _draw_bake_cursor_status, (), "WINDOW", "POST_PIXEL",
        )
        self._timer = context.window_manager.event_timer_add(0.12, window=context.window)
        context.window_manager.modal_handler_add(self)
        _redraw_bake_ui(context)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def modal(self, context, event):
        global _BAKE_CURSOR_POSITION
        if not self.settings.bake_task_is_running:
            if bpy.app.is_job_running('OBJECT_BAKE'):
                self.cancel_requested = True
                return {'PASS_THROUGH'}
            return self._finish(
                context, False, t(context, "bake_cancelled"), cancelled=True,
            )
        if event.type == "MOUSEMOVE":
            _BAKE_CURSOR_POSITION = (event.mouse_region_x, event.mouse_region_y)
        if event.type == "ESC" and event.value == "PRESS":
            self.cancel_requested = True
            cancelled_message = t(context, "bake_cancelled")
            self._set_status(context, "CANCELLING", 0, cancelled_message)
            # Let Blender's running bake operator receive Esc as well. Once its
            # job exits, the timer branch below performs all task cleanup.
            if bpy.app.is_job_running("OBJECT_BAKE"):
                return {"PASS_THROUGH"}
            return self._finish(context, False, cancelled_message, cancelled=True)
        if event.type == "TIMER":
            if self.cancel_requested:
                if bpy.app.is_job_running("OBJECT_BAKE"):
                    return {"RUNNING_MODAL"}
                return self._finish(
                    context, False, t(context, "bake_cancelled"), cancelled=True,
                )
            try:
                result = self._step(context)
            except Exception as error:
                return self._finish(context, False, f"Bake failed: {error}")
            if result is not None:
                return result
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if not bpy.app.is_job_running("OBJECT_BAKE"):
            self._finish(
                context, False, t(context, "bake_cancelled"), cancelled=True,
            )


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
        settings = context.scene.polygroups_baking_settings
        _auto_fix_selected_generated_indices(context, settings)
        target = _active_mesh(context)
        sources = _source_meshes(context, target)
        _invalidate_artifact_mask(target)

        if not settings.bake_base_color and not settings.bake_normal:
            self.report({"WARNING"}, "Enable at least one bake pass")
            return {"CANCELLED"}

        if target.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if not _auto_pack_target_uvs(context, target, settings, self.report):
            return {"CANCELLED"}
        if not _apply_auto_cage_if_enabled(context, target, sources, settings, self.report):
            return {"CANCELLED"}
        material, base_node, normal_node = _ensure_bake_material(target, settings)
        _invalidate_artifact_mask(target)
        target.active_material = material
        _select_sources_and_target(context, sources, target)

        if settings.bake_base_color:
            _bake_to_node(context, target, base_node, "DIFFUSE", settings)

        try:
            repair = _run_normal_and_artifact(context, target, sources, settings, normal_node)
            _finalize_with_artifact_autofill(target, settings, repair, self.report)
        except Exception as error:
            self.report({'ERROR'}, f'Normal/projection bake failed: {error}')
            return {'CANCELLED'}
        _disable_highpoly_sources_after_bake(settings, sources)
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
        settings = context.scene.polygroups_baking_settings
        _auto_fix_selected_generated_indices(context, settings)
        target = _active_mesh(context)
        sources = _source_meshes(context, target)
        _invalidate_artifact_mask(target)

        if target.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        if not _auto_pack_target_uvs(context, target, settings, self.report):
            return {"CANCELLED"}

        changed_count = 0
        for obj in sources:
            for material in obj.data.materials:
                if _set_polygroup_material_texture_only(material):
                    changed_count += 1

        if not _apply_auto_cage_if_enabled(context, target, sources, settings, self.report):
            return {"CANCELLED"}

        material, base_node, normal_node = _ensure_bake_material(target, settings)
        _invalidate_artifact_mask(target)
        target.active_material = material
        _select_sources_and_target(context, sources, target)

        if settings.bake_base_color:
            _bake_to_node(context, target, base_node, "DIFFUSE", settings)

        try:
            repair = _run_normal_and_artifact(context, target, sources, settings, normal_node)
            _finalize_with_artifact_autofill(target, settings, repair, self.report)
        except Exception as error:
            self.report({'ERROR'}, f'Normal/projection bake failed: {error}')
            return {'CANCELLED'}
        if settings.auto_save_textures_after_bake:
            try:
                save_result = bpy.ops.object.polygroups_save_bake_textures()
            except Exception as error:
                self.report({"WARNING"}, f"Auto save textures failed: {error}")
            else:
                if "FINISHED" not in save_result:
                    self.report({"WARNING"}, "Auto save textures was not completed")

        _disable_highpoly_sources_after_bake(settings, sources)
        self.report(
            {"INFO"},
            f"Prepared {changed_count} material(s) and finished bake",
        )
        return {"FINISHED"}
