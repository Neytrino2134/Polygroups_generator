import json
import time
import uuid
import bpy
from math import cos
from math import radians
from math import sin
from math import tau
from mathutils import Matrix
from mathutils import Vector

from ..sound import play_operation_done_sound
from .apply_weld import apply_weld_to_objects
from .mesh_checks import _delete_faces_by_indices
from .mesh_checks import _edge_face_data
from .mesh_checks import _fixable_issue_total
from .mesh_checks import _refresh_mesh_check
from .mesh_checks import _select_edges
from .mesh_checks import _thin_protrusion_faces
from .mesh_checks import analyze_mesh
from .relax_seams import relax_seams
from ..pin_edges import pin_layer, set_pinned


from .cutter_screen import (
    _view3d_under_mouse,
    _target_bounds,
    _axis_lock_mode,
    _axis_locked_region_pos,
    _surface_hit_from_region_pos,
    _target_ray_cast_world,
    _screen_cut_plane,
    _arc_center_2d,
    _angle_delta_ccw,
    _screen_arc_points,
    _screen_arc_surface,
    _screen_section_plane,
    _screen_local_ring_surface,
)
from .cutter_overlay import (
    _draw_cutter_overlay,
    _draw_cutter_arc_overlay,
    _draw_cutter_path_overlay,
    _draw_cutter_local_ring_overlay,
)


from .cutter_constants import (
    AUTOFIX_MAX_HOLE_EDGE_COUNT,
    AUTOFIX_MAX_HOLE_LOOPS,
    AUTOFIX_MAX_LOOSE_GEOMETRY,
    AUTOFIX_MAX_PROTRUSION_FACES,
    AUTOWELD_MODIFIER_NAME,
    AUTOWELD_VERTEX_GROUP_NAME,
    BOOLEAN_PATH_PLACEHOLDER_MATERIAL_NAME,
    BOOLEAN_PATH_TEMP_MATERIAL_NAME,
    CUTTER_BACKUP_COLLECTION_NAME,
    CUTTER_BACKUP_OWNER_PROP,
    CUTTER_BACKUP_PREFIX,
    CUTTER_BACKUP_SNAPSHOT_PROP,
    CUTTER_COLLECTION_BY_TOOL,
    CUTTER_COLLECTION_NAME,
    CUTTER_DRAW_DATA_PROP,
    CUTTER_INSTANCE_ID_PROP,
    CUTTER_ORIGINAL_NAME_PROP,
    CUTTER_PATH_DATA_PROP,
    CUTTER_PATH_TILT_STEP,
    CUTTER_PIN_SEAMS_PROP,
    CUTTER_PROP,
    CUTTER_SOLIDIFY_MODIFIER_NAME,
    CUTTER_SOURCE_TOOL_PROP,
    CUTTER_TYPE_PROP,
    DEFAULT_CUTTER_PATH_TILT,
    DEFAULT_NON_PLANE_CUTTER_THICKNESS,
)
from .cutter_paths import (
    _curve_point_local_co,
    _curve_spline_points,
    _cutter_planes_world,
    _draw_stroke_data,
    _draw_stroke_path_points,
    _join_draw_stroke_points,
    _join_path_points,
    _path_cutter_path_points,
    _path_cutter_planes_world,
    _path_cutter_segments_world,
    _path_data,
    _path_normals_world,
    _path_points_world,
    _path_tilts,
    _selected_cutter_path_curves,
    _set_bezier_handle_auto,
    _simplify_path_points,
    _update_curve_path_data_from_splines,
    _write_cutter_path_points,
    _write_draw_stroke_points,
)
from .cutter_objects import (
    _add_solidify_modifier,
    _apply_mirrored_cutter_scales,
    _collection,
    _collection_objects_recursive,
    _convert_draw_stroke_to_cutter_path,
    _copy_mirror_cutter,
    _create_cutter_arc,
    _create_cutter_draw_stroke,
    _create_cutter_local_ring,
    _create_cutter_path,
    _create_cutter_plane,
    _cutter_collection_objects,
    _draw_strokes_from_cutters,
    _draw_strokes_in_collection,
    _ensure_local_contour_cutter,
    _find_cutter_target,
    _find_draw_stroke_to_continue,
    _find_path_to_continue,
    _has_selected_cutters_for_apply,
    _is_cutter_name,
    _is_cutter_object,
    _is_local_contour_cutter,
    _is_target_mesh_candidate,
    _join_draw_strokes,
    _join_path_cutters,
    _material,
    _mirror_matrix_from_target,
    _path_cutters_in_collection,
    _prefer_highpoly_generated,
    _selected_cutters,
    _selected_cutters_only,
    _tool_collection,
    _tool_collection_type_for_cutter,
)
from .cutter_mesh import (
    _apply_arc_cutters_to_mesh,
    _apply_boolean_cutter_to_mesh,
    _apply_cutters_to_mesh,
    _apply_knife_intersect_cutter_to_mesh,
    _apply_object_scale,
    _apply_plane_cutters_to_mesh,
    _boundary_hole_loops_for_autofix,
    _clear_mesh_component_selection,
    _count_open_boundary_edges,
    _cutter_apply_method,
    _cutter_boolean_solver,
    _cutter_mark_pinned,
    _cutter_thickness,
    _delete_loose_geometry_for_autofix,
    _dissolve_degenerate_seam_geometry,
    _duplicate_boolean_cutter_as_mesh,
    _ensure_material_slot,
    _extend_arc_cutter_mesh_ends,
    _fill_boundary_hole_loop_for_autofix,
    _fill_open_nonmanifold_boundaries,
    _fill_split_cut_boundaries,
    _intersect_cutter_surface,
    _material_slot_index,
    _mesh_has_selected_edges,
    _path_boolean_material,
    _path_placeholder_material,
    _prepare_cutters_for_apply,
    _prepare_seam_band_autoweld,
    _prepare_target_for_autofix,
    _prepare_target_path_boolean_materials,
    _remove_cutter_faces_and_mark_seams,
    _remove_fin_faces_for_autofix,
    _remove_material_if_unused,
    _remove_material_slot_by_index,
    _smart_relax_seams_for_autofix,
    _split_selected_edges,
    _split_supported_cutters,
    _sync_autoweld_vertex_group,
    _triangulate_ngons_for_autofix,
    _world_plane_to_local,
)
from .cutter_draw import (
    OBJECT_OT_polygroups_draw_cutter_arc,
    OBJECT_OT_polygroups_draw_cutter_draw,
    OBJECT_OT_polygroups_draw_cutter_local_contour,
    OBJECT_OT_polygroups_draw_cutter_local_ring,
    OBJECT_OT_polygroups_draw_cutter_path,
    OBJECT_OT_polygroups_draw_cutter_plane,
    _LocalDiskCutterInteraction,
    _stabilize_stroke_position,
)


ACTIVE_CUTTER_APPLY = None


class OBJECT_OT_polygroups_convert_draw_strokes_to_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_convert_draw_strokes_to_cutter_paths"
    bl_label = "Convert Draw Strokes To Cutter Paths"
    bl_description = "Convert freehand cutter draw strokes to cutter path curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected = [
            obj
            for obj in context.selected_objects
            if obj.type == "CURVE" and obj.get(CUTTER_PROP) and obj.get(CUTTER_TYPE_PROP) == "DRAW_STROKE"
        ]
        strokes = selected or _draw_strokes_from_cutters(_selected_cutters(context, context.active_object))
        if not strokes:
            self.report({"WARNING"}, "No cutter draw strokes found")
            return {"CANCELLED"}

        converted = []
        for stroke in strokes:
            cutter = _convert_draw_stroke_to_cutter_path(context, stroke)
            if cutter is not None:
                converted.append(cutter)

        if not converted:
            self.report({"WARNING"}, "No cutter draw strokes could be converted")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        for cutter in converted:
            cutter.select_set(True)
        context.view_layer.objects.active = converted[-1]
        self.report({"INFO"}, f"Converted {len(converted)} draw stroke(s) to cutter path(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_join_draw_strokes(bpy.types.Operator):
    bl_idname = "object.polygroups_join_draw_strokes"
    bl_label = "Join Selected Draw Strokes"
    bl_description = "Join selected cutter draw strokes into one continuous draw stroke"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        strokes = [
            obj
            for obj in context.selected_objects
            if obj.type == "CURVE" and obj.get(CUTTER_PROP) and obj.get(CUTTER_TYPE_PROP) == "DRAW_STROKE"
        ]
        if len(strokes) < 2:
            self.report({"WARNING"}, "Select at least two cutter draw strokes")
            return {"CANCELLED"}

        stroke, joined_count = _join_draw_strokes(strokes, settings.cutter_draw_join_distance)
        if stroke is None or not joined_count:
            self.report({"WARNING"}, "No draw strokes were close enough to join")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        stroke.select_set(True)
        context.view_layer.objects.active = stroke
        self.report({"INFO"}, f"Joined {joined_count + 1} draw stroke(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_join_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_join_cutter_paths"
    bl_label = "Join Selected Cutter Paths"
    bl_description = "Join selected cutter path curves into one continuous cutter path"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        paths = [
            obj
            for obj in context.selected_objects
            if obj.type == "CURVE" and obj.get(CUTTER_PROP) and obj.get(CUTTER_TYPE_PROP) == "PATH"
        ]
        if len(paths) < 2:
            self.report({"WARNING"}, "Select at least two cutter paths")
            return {"CANCELLED"}

        path, joined_count = _join_path_cutters(paths, settings.cutter_path_join_distance)
        if path is None or not joined_count:
            self.report({"WARNING"}, "No cutter paths were close enough to join")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        path.select_set(True)
        context.view_layer.objects.active = path
        self.report({"INFO"}, f"Joined {joined_count + 1} cutter path(s)")
        return {"FINISHED"}


def _run_selected_cutter_curve_edit_op(context, curves, operator_callback):
    original_active = context.view_layer.objects.active
    original_selection = tuple(context.selected_objects)
    changed = 0

    if context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass

    try:
        for obj in curves:
            if obj.name not in context.view_layer.objects:
                continue
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.curve.select_all(action="SELECT")
            operator_callback(obj)
            bpy.ops.object.mode_set(mode="OBJECT")
            _update_curve_path_data_from_splines(obj)
            changed += 1
    finally:
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        for obj in original_selection:
            if obj.name in context.view_layer.objects:
                obj.select_set(True)
        if original_active and original_active.name in context.view_layer.objects:
            context.view_layer.objects.active = original_active

    return changed


class OBJECT_OT_polygroups_bezier_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_bezier_cutter_paths"
    bl_label = "Bezier Cutter Paths"
    bl_description = "Convert selected cutter path and draw curves to Bezier splines with automatic handles"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def convert_to_bezier(obj):
            del obj
            try:
                bpy.ops.curve.spline_type_set(type="BEZIER")
            except RuntimeError:
                pass
            try:
                bpy.ops.curve.handle_type_set(type="AUTO")
            except (RuntimeError, TypeError):
                try:
                    bpy.ops.curve.handle_type_set(type="AUTOMATIC")
                except (RuntimeError, TypeError):
                    pass

        changed = _run_selected_cutter_curve_edit_op(context, curves, convert_to_bezier)
        for obj in curves:
            for spline in obj.data.splines:
                if spline.type != "BEZIER":
                    continue
                for point in spline.bezier_points:
                    _set_bezier_handle_auto(point)
                    if hasattr(point, "tilt") and abs(point.tilt) < 0.000001:
                        point.tilt = DEFAULT_CUTTER_PATH_TILT
            obj.data.update_tag()

        self.report({"INFO"}, f"Converted {changed} cutter curve(s) to Bezier")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_toggle_cyclic_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_toggle_cyclic_cutter_paths"
    bl_label = "Toggle Cyclic Cutter Paths"
    bl_description = "Toggle cyclic state on selected cutter path and draw curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def toggle_cyclic(obj):
            try:
                bpy.ops.curve.cyclic_toggle(direction="CYCLIC_U")
            except (RuntimeError, TypeError):
                for spline in obj.data.splines:
                    spline.use_cyclic_u = not spline.use_cyclic_u

        changed = _run_selected_cutter_curve_edit_op(context, curves, toggle_cyclic)
        self.report({"INFO"}, f"Toggled cyclic on {changed} cutter curve(s)")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_smooth_cutter_paths(bpy.types.Operator):
    bl_idname = "object.polygroups_smooth_cutter_paths"
    bl_label = "Smooth Cutter Paths"
    bl_description = "Smooth selected cutter path and draw curve points"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def smooth_curve(obj):
            del obj
            try:
                bpy.ops.curve.smooth()
            except RuntimeError:
                pass

        changed = _run_selected_cutter_curve_edit_op(context, curves, smooth_curve)
        self.report({"INFO"}, f"Smoothed {changed} cutter curve(s)")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_smooth_cutter_path_tilt(bpy.types.Operator):
    bl_idname = "object.polygroups_smooth_cutter_path_tilt"
    bl_label = "Smooth Cutter Path Tilt"
    bl_description = "Smooth tilt values on selected cutter path and draw curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        curves = _selected_cutter_path_curves(context)
        if not curves:
            self.report({"WARNING"}, "Select cutter path or draw curves")
            return {"CANCELLED"}

        def smooth_tilt(obj):
            del obj
            try:
                bpy.ops.curve.smooth_tilt()
            except RuntimeError:
                pass

        changed = _run_selected_cutter_curve_edit_op(context, curves, smooth_tilt)
        self.report({"INFO"}, f"Smoothed tilt on {changed} cutter curve(s)")
        return {"FINISHED"} if changed else {"CANCELLED"}


class OBJECT_OT_polygroups_tilt_cutter_path(bpy.types.Operator):
    bl_idname = "object.polygroups_tilt_cutter_path"
    bl_label = "Tilt Cutter Path"
    bl_description = "Apply tilt to selected cutter path curves"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        items=(
            ("DECREASE", "Decrease", "Decrease tilt"),
            ("INCREASE", "Increase", "Increase tilt"),
            ("RESET", "Reset", "Reset tilt"),
        ),
        default="INCREASE",
    )

    def execute(self, context):
        if context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        delta = CUTTER_PATH_TILT_STEP
        if self.mode == "DECREASE":
            delta = -delta

        changed = 0
        changed_objects = []
        for obj in context.selected_objects:
            if (
                obj.type != "CURVE"
                or not obj.get(CUTTER_PROP)
                or obj.get(CUTTER_TYPE_PROP) not in {"PATH", "DRAW_STROKE"}
            ):
                continue

            object_changed = False
            for spline in obj.data.splines:
                for point in _curve_spline_points(spline):
                    if not hasattr(point, "tilt"):
                        continue
                    if self.mode == "RESET":
                        point.tilt = DEFAULT_CUTTER_PATH_TILT
                    else:
                        point.tilt += delta
                    changed += 1
                    object_changed = True
            if object_changed:
                _update_curve_path_data_from_splines(obj)
                changed_objects.append(obj)

        if not changed:
            self.report({"WARNING"}, "No selected cutter path curves")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        for obj in changed_objects:
            obj.select_set(True)
        context.view_layer.objects.active = changed_objects[0]
        bpy.ops.object.mode_set(mode="OBJECT")
        self.report({"INFO"}, f"Updated tilt on {changed} path point(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_copy_mirror_cutters(bpy.types.Operator):
    bl_idname = "object.polygroups_copy_mirror_cutters"
    bl_label = "Copy Mirror Cutters"
    bl_description = "Copy selected cutter objects and mirror them in Object Mode around the active mesh origin"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = context.active_object
        return (
            _is_target_mesh_candidate(target)
            and bool(_selected_cutters_only(context))
        )

    def execute(self, context):
        target = context.active_object
        cutters = _selected_cutters_only(context)
        settings = context.scene.polygroups_object_seam_cutter_settings
        if target is None or not cutters:
            self.report({"WARNING"}, "Select cutter objects and make the mirror mesh active")
            return {"CANCELLED"}

        mirror_matrix = _mirror_matrix_from_target(target, settings.cutter_mirror_axis)
        mirrored_cutters = []
        for cutter in cutters:
            mirrored = _copy_mirror_cutter(cutter, mirror_matrix)
            if mirrored is not None:
                mirrored_cutters.append(mirrored)
        if not mirrored_cutters:
            self.report({"WARNING"}, "Selected cutters could not be mirrored")
            return {"CANCELLED"}

        if not _apply_mirrored_cutter_scales(context, mirrored_cutters):
            for mirrored in mirrored_cutters:
                if mirrored.name in bpy.data.objects:
                    bpy.data.objects.remove(mirrored, do_unlink=True)
            self.report({"ERROR"}, "Could not apply scale to mirrored cutters")
            return {"CANCELLED"}

        context.view_layer.objects.active = target
        target.select_set(True)
        self.report(
            {"INFO"},
            f"Copied and mirrored {len(mirrored_cutters)} cutter(s) on {settings.cutter_mirror_axis}",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_auto_fix_after_cutter(bpy.types.Operator):
    bl_idname = "object.polygroups_auto_fix_after_cutter"
    bl_label = "Autofix After Cutter"
    bl_description = "Fill open boundaries and triangulate n-gons without running a full mesh check"
    bl_options = {"REGISTER", "UNDO"}

    target_name: bpy.props.StringProperty(default="")

    def _target(self, context):
        target = bpy.data.objects.get(self.target_name)
        if target is not None and target.type == "MESH":
            return target
        active = context.active_object
        if active is not None and active.type == "MESH":
            return active
        return None

    def execute(self, context):
        target = self._target(context)
        if target is None:
            self.report({"WARNING"}, "No mesh target found for autofix")
            return {"CANCELLED"}

        _prepare_target_for_autofix(context, target)
        settings = context.scene.polygroups_object_seam_cutter_settings
        removed_fins = 0
        removed_loose = 0
        if settings.cutter_auto_fix_fin_faces:
            removed_fins = _remove_fin_faces_for_autofix(context, target)
            removed_loose = _delete_loose_geometry_for_autofix(context, target)
        filled_faces = _fill_open_nonmanifold_boundaries(target)
        relaxed_vertices = (
            _smart_relax_seams_for_autofix(context, target)
            if settings.cutter_auto_fix_smart_relax_seams else 0
        )
        triangulated_ngons = (
            _triangulate_ngons_for_autofix(target)
            if settings.cutter_auto_fix_triangulate_ngons else 0
        )
        self.report(
            {"INFO"},
            f"Autofix removed {removed_fins} fin face(s) and {removed_loose} loose item(s), "
            f"filled {filled_faces} polygon(s), "
            f"relaxed {relaxed_vertices} seam vertex/vertices, "
            f"triangulated {triangulated_ngons} n-gon(s)",
        )
        return {"FINISHED"}


def _redraw_cutter_apply(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _cutter_backup_for(target):
    backup = bpy.data.objects.get(CUTTER_BACKUP_PREFIX + target.name)
    return backup if backup is not None and backup.type == "MESH" else None


def _ensure_cutter_backup(context, target):
    backup = _cutter_backup_for(target)
    if backup is not None:
        return backup, False
    backup = target.copy()
    backup.data = target.data.copy()
    backup.animation_data_clear()
    backup.name = CUTTER_BACKUP_PREFIX + target.name
    backup.data.name = CUTTER_BACKUP_PREFIX + target.data.name
    for collection in target.users_collection or (context.scene.collection,):
        collection.objects.link(backup)
    backup.hide_viewport = True
    backup.hide_render = True
    try:
        backup.hide_set(True)
    except RuntimeError:
        pass
    return backup, True


def _cutter_backup_collection(context):
    collection = bpy.data.collections.get(CUTTER_BACKUP_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(CUTTER_BACKUP_COLLECTION_NAME)
        context.scene.collection.children.link(collection)
    collection.hide_viewport = True
    collection.hide_render = True
    return collection


def _remember_applied_cutters(context, target, cutters):
    backup, _created = _ensure_cutter_backup(context, target)
    owner = backup.name
    collection = _cutter_backup_collection(context)
    remembered = []
    for cutter in cutters:
        instance_id = cutter.get(CUTTER_INSTANCE_ID_PROP)
        if not instance_id:
            instance_id = uuid.uuid4().hex
            cutter[CUTTER_INSTANCE_ID_PROP] = instance_id
        for existing in list(collection.objects):
            if (existing.get(CUTTER_BACKUP_OWNER_PROP) == owner
                    and existing.get(CUTTER_INSTANCE_ID_PROP) == instance_id):
                bpy.data.objects.remove(existing, do_unlink=True)
        snapshot = cutter.copy()
        snapshot.data = cutter.data.copy()
        snapshot.animation_data_clear()
        snapshot.name = f"BackupCutter_{target.name}_{cutter.name}"
        snapshot[CUTTER_BACKUP_OWNER_PROP] = owner
        snapshot[CUTTER_BACKUP_SNAPSHOT_PROP] = True
        snapshot[CUTTER_ORIGINAL_NAME_PROP] = cutter.name
        collection.objects.link(snapshot)
        snapshot.hide_viewport = True
        snapshot.hide_render = True
        try:
            snapshot.hide_set(True)
        except RuntimeError:
            pass
        remembered.append(snapshot)
    return remembered


def _restore_applied_cutters(context, backup):
    snapshots = [
        obj for obj in bpy.data.objects
        if obj.get(CUTTER_BACKUP_SNAPSHOT_PROP)
        and obj.get(CUTTER_BACKUP_OWNER_PROP) == backup.name
    ]
    restored = []
    for snapshot in snapshots:
        instance_id = snapshot.get(CUTTER_INSTANCE_ID_PROP)
        for current in list(bpy.data.objects):
            if current == snapshot or current.get(CUTTER_BACKUP_SNAPSHOT_PROP):
                continue
            if current.get(CUTTER_INSTANCE_ID_PROP) == instance_id:
                bpy.data.objects.remove(current, do_unlink=True)
        cutter = snapshot.copy()
        cutter.data = snapshot.data.copy()
        cutter.animation_data_clear()
        cutter.name = snapshot.get(CUTTER_ORIGINAL_NAME_PROP, snapshot.name)
        cutter.hide_viewport = False
        cutter.hide_render = False
        for key in (CUTTER_BACKUP_OWNER_PROP, CUTTER_BACKUP_SNAPSHOT_PROP):
            if key in cutter:
                del cutter[key]
        _tool_collection(_tool_collection_type_for_cutter(cutter)).objects.link(cutter)
        try:
            cutter.hide_set(False)
        except RuntimeError:
            pass
        restored.append(cutter)
    return restored


class OBJECT_OT_polygroups_create_cutter_backup(bpy.types.Operator):
    bl_idname = "object.polygroups_create_cutter_backup"
    bl_label = "Create Cutter Backup"
    bl_description = "Create a hidden Backup_ copy unless one already exists"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _find_cutter_target(context) is not None

    def execute(self, context):
        target = _find_cutter_target(context)
        if target is None:
            return {"CANCELLED"}
        backup, created = _ensure_cutter_backup(context, target)
        message = f"Created hidden backup: {backup.name}" if created else f"Backup already exists: {backup.name}"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_restore_cutter_backup(bpy.types.Operator):
    bl_idname = "object.polygroups_restore_cutter_backup"
    bl_label = "Restore Cutter Backup"
    bl_description = "Restore a copy of the hidden Backup_ object"
    bl_options = {"REGISTER", "UNDO"}

    current_action: bpy.props.EnumProperty(
        name="Current Mesh",
        items=(
            ("DELETE", "Delete Current Mesh", "Delete the selected current mesh before restoring"),
            ("KEEP", "Keep Current Mesh", "Keep the selected mesh under a Current_ name"),
        ),
        default="DELETE",
    )
    restore_cutters: bpy.props.BoolProperty(
        name="Restore Cutters",
        description="Restore all cutters remembered across Apply Cutter Seams iterations",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        target = context.active_object
        return target is not None and target.type == "MESH" and _cutter_backup_for(target) is not None

    def invoke(self, context, event):
        del event
        return context.window_manager.invoke_props_dialog(
            self, width=420, confirm_text="Restore Backup",
        )

    def draw(self, context):
        self.layout.label(text="What should happen to the selected current mesh?", icon="QUESTION")
        self.layout.prop(self, "current_action", expand=True)
        self.layout.prop(self, "restore_cutters", icon="MOD_BOOLEAN")

    def execute(self, context):
        target = context.active_object
        backup = _cutter_backup_for(target)
        if backup is None:
            self.report({"WARNING"}, f"No {CUTTER_BACKUP_PREFIX}{target.name} found")
            return {"CANCELLED"}
        source_name = backup.name[len(CUTTER_BACKUP_PREFIX):]
        collections = tuple(target.users_collection) or tuple(backup.users_collection) or (context.scene.collection,)
        if self.current_action == "DELETE":
            bpy.data.objects.remove(target, do_unlink=True)
        else:
            target.name = "Current_" + source_name
        restored = backup.copy()
        restored.data = backup.data.copy()
        restored.animation_data_clear()
        restored.name = source_name
        restored.data.name = source_name
        for collection in collections:
            collection.objects.link(restored)
        restored.hide_viewport = False
        restored.hide_render = False
        restored.hide_set(False)
        restored_cutters = _restore_applied_cutters(context, backup) if self.restore_cutters else []
        for obj in context.selected_objects:
            obj.select_set(False)
        restored.select_set(True)
        context.view_layer.objects.active = restored
        self.report(
            {"INFO"},
            f"Restored {restored.name} from {backup.name}; restored {len(restored_cutters)} cutter(s)",
        )
        return {"FINISHED"}


class CutterApplySession:
    def __init__(self, context, target, cutters, report):
        from ..core.remesh_cursor import RemeshCursor

        self.context_scene = context.scene
        self.target = target
        self.cutters = list(cutters)
        self.report = report
        self.settings = context.scene.polygroups_object_seam_cutter_settings
        self.status = self.settings
        self.index = 0
        self.marked_edges = 0
        self.filled_before = self.filled_after = 0
        self.triangulated_before = self.triangulated_after = 0
        self.removed_fins_before = self.removed_fins_after = 0
        self.removed_loose_before = self.removed_loose_after = 0
        self.done = False
        self.timer = None
        self.cursor = RemeshCursor(context, label="Cutter")
        self.status.cutter_apply_is_running = True
        self.status.cutter_apply_stage = "BACKUP"
        self.status.cutter_apply_message = "Creating or checking backup"
        self.status.cutter_apply_progress = 0

    def set_stage(self, stage, progress, message):
        self.status.cutter_apply_stage = stage
        self.status.cutter_apply_progress = progress
        self.status.cutter_apply_message = message
        self.cursor.percent = progress

    def _autofix(self, context, suffix):
        removed_fins = removed_loose = 0
        if self.settings.cutter_auto_fix_fin_faces:
            removed_fins = _remove_fin_faces_for_autofix(context, self.target)
            removed_loose = _delete_loose_geometry_for_autofix(context, self.target)
        filled = _fill_open_nonmanifold_boundaries(self.target)
        setattr(self, f"removed_fins_{suffix}", removed_fins)
        setattr(self, f"removed_loose_{suffix}", removed_loose)
        setattr(self, f"filled_{suffix}", filled)

    def finish(self, context, stage, message=""):
        if self.done:
            return
        self.done = True
        self.status.cutter_apply_is_running = False
        self.status.cutter_apply_stage = stage
        self.status.cutter_apply_progress = 100 if stage == "DONE" else self.status.cutter_apply_progress
        self.status.cutter_apply_message = message
        self.cursor.percent = self.status.cutter_apply_progress
        self.cursor.close()
        _redraw_cutter_apply(context)

    def step(self, context):
        if self.done:
            return
        try:
            stage = self.status.cutter_apply_stage
            if stage == "BACKUP":
                backup, created = _ensure_cutter_backup(context, self.target)
                message = f"Created {backup.name}" if created else f"Using existing {backup.name}"
                self.set_stage("PREPARING", 4, message)
            elif stage == "PREPARING":
                _apply_object_scale(context, self.target)
                self.cutters = _prepare_cutters_for_apply(context, self.cutters)
                _remember_applied_cutters(context, self.target, self.cutters)
                _clear_mesh_component_selection(self.target.data)
                self.set_stage("AUTOFIX_BEFORE", 8, "Autofixing before cutting")
            elif stage == "AUTOFIX_BEFORE":
                if self.settings.cutter_auto_fix_mesh:
                    self._autofix(context, "before")
                self.set_stage("CUTTING", 18, "Cutting 0 / %d" % len(self.cutters))
            elif stage == "CUTTING":
                if self.index < len(self.cutters):
                    cutter = self.cutters[self.index]
                    self.marked_edges += _apply_cutters_to_mesh(context, self.target, [cutter])
                    self.index += 1
                    progress = 18 + 52 * self.index / max(1, len(self.cutters))
                    self.set_stage(
                        "CUTTING", progress,
                        f"Cutting {self.index} / {len(self.cutters)}: {cutter.name}",
                    )
                else:
                    self.set_stage("AUTOFIX_AFTER", 74, "Autofixing after cutting")
            elif stage == "AUTOFIX_AFTER":
                if self.settings.cutter_auto_fix_mesh:
                    self._autofix(context, "after")
                self.set_stage("FINDING_GAPS", 88, "Finding and closing seam gaps")
            elif stage == "FINDING_GAPS":
                if self.settings.cutter_auto_fix_mesh and self.settings.cutter_auto_fix_seam_check:
                    _prepare_target_for_autofix(context, self.target)
                    bpy.ops.mesh.polygroups_check_and_close_seam_gaps()
                self.set_stage("MERGING_ISLANDS", 92, "Checking and merging small islands")
            elif stage == "MERGING_ISLANDS":
                if self.settings.cutter_auto_fix_mesh and self.settings.cutter_auto_fix_small_islands:
                    _prepare_target_for_autofix(context, self.target)
                    bpy.ops.mesh.polygroups_merge_small_islands(
                        preview=False,
                        threshold_override=self.settings.cutter_auto_fix_small_islands_threshold,
                    )
                self.set_stage("WELDING", 96, "Welding nearby vertices")
            elif stage == "WELDING":
                if self.settings.cutter_auto_fix_mesh and self.settings.cutter_auto_fix_weld:
                    _dissolve_degenerate_seam_geometry(
                        self.target,
                        self.settings.cutter_auto_fix_weld_distance,
                    )
                    _prepare_seam_band_autoweld(
                        self.target,
                        self.settings.cutter_auto_fix_weld_distance,
                    )
                    apply_weld_to_objects(
                        context,
                        [self.target],
                        self.settings.cutter_auto_fix_weld_distance,
                        self.report,
                    )
                    # Weld can create a new zero-area or folded face while
                    # merging the seam band, so validate the result once more.
                    _dissolve_degenerate_seam_geometry(
                        self.target,
                        self.settings.cutter_auto_fix_weld_distance,
                    )
                    _sync_autoweld_vertex_group(self.target)
                self.set_stage("RELAXING_SEAMS", 97, "Smart relaxing seams")
            elif stage == "RELAXING_SEAMS":
                if self.settings.cutter_auto_fix_mesh and self.settings.cutter_auto_fix_smart_relax_seams:
                    _smart_relax_seams_for_autofix(context, self.target)
                self.set_stage("TRIANGULATING_NGONS", 98, "Triangulating n-gons")
            elif stage == "TRIANGULATING_NGONS":
                if self.settings.cutter_auto_fix_mesh and self.settings.cutter_auto_fix_triangulate_ngons:
                    self.triangulated_after = _triangulate_ngons_for_autofix(self.target)
                self.set_stage("FINALIZING", 99, "Finalizing cutter operation")
            elif stage == "FINALIZING":
                self.settings.last_cutter_count = len(self.cutters)
                self.settings.last_marked_edge_count = self.marked_edges
                if self.settings.delete_cutters_after_apply:
                    for cutter in self.cutters:
                        if cutter in set(bpy.data.objects):
                            bpy.data.objects.remove(cutter, do_unlink=True)
                elif self.settings.hide_cutters_after_apply:
                    for cutter in self.cutters:
                        if cutter in set(bpy.data.objects):
                            cutter.hide_set(True)
                            cutter.hide_viewport = True
                message = (
                    f"Applied {len(self.cutters)} cutter object(s), "
                    f"marked {self.marked_edges} seam edge(s)"
                )
                self.report({"INFO"}, message)
                play_operation_done_sound(context)
                self.finish(context, "DONE", message)
        except Exception as error:
            self.report({"ERROR"}, f"Apply Cutter Seams failed: {error}")
            self.finish(context, "FAILED", str(error))


def stop_cutter_apply(*_args):
    global ACTIVE_CUTTER_APPLY
    if ACTIVE_CUTTER_APPLY is not None:
        ACTIVE_CUTTER_APPLY.finish(bpy.context, "CANCELLED", "Cutter operation cancelled")
        if ACTIVE_CUTTER_APPLY.timer is not None:
            try:
                bpy.context.window_manager.event_timer_remove(ACTIVE_CUTTER_APPLY.timer)
            except Exception:
                pass
            ACTIVE_CUTTER_APPLY.timer = None
        ACTIVE_CUTTER_APPLY = None


class OBJECT_OT_polygroups_apply_cutter_seams(bpy.types.Operator):
    bl_idname = "object.polygroups_apply_cutter_seams"
    bl_label = "Apply Cutter Seams To Active"
    bl_description = "Apply selected cutter planes to the active mesh and mark cut edges as seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            ACTIVE_CUTTER_APPLY is None
            and
            context.mode == "OBJECT"
            and _find_cutter_target(context) is not None
            and _has_selected_cutters_for_apply(context)
        )

    def execute(self, context):
        global ACTIVE_CUTTER_APPLY
        target = _find_cutter_target(context)
        if target is None:
            self.report({"WARNING"}, "No active mesh target found")
            return {"CANCELLED"}
        context.view_layer.objects.active = target
        settings = context.scene.polygroups_object_seam_cutter_settings
        cutters = [cutter for cutter in _selected_cutters_only(context) if cutter != target]
        if not cutters:
            self.report({"WARNING"}, "Select at least one cutter object")
            return {"CANCELLED"}

        self._session = CutterApplySession(context, target, cutters, self.report)
        ACTIVE_CUTTER_APPLY = self._session
        if bpy.app.background:
            while not self._session.done:
                self._session.step(context)
            ACTIVE_CUTTER_APPLY = None
            return {"FINISHED"} if self._session.status.cutter_apply_stage == "DONE" else {"CANCELLED"}

        self._next_tick = time.monotonic()
        self._session.timer = context.window_manager.event_timer_add(0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        _redraw_cutter_apply(context)
        return {"RUNNING_MODAL"}

    def _cleanup(self, context):
        global ACTIVE_CUTTER_APPLY
        if self._session.timer is not None:
            context.window_manager.event_timer_remove(self._session.timer)
            self._session.timer = None
        if ACTIVE_CUTTER_APPLY is self._session:
            ACTIVE_CUTTER_APPLY = None

    def modal(self, context, event):
        from ..core.remesh_cursor import update_remesh_cursor
        update_remesh_cursor(context, event)
        if event.type == "ESC":
            self._session.finish(context, "CANCELLED", "Cutter operation cancelled")
        elif event.type != "TIMER" or time.monotonic() < self._next_tick:
            return {"PASS_THROUGH"}
        else:
            self._next_tick = time.monotonic() + 0.05
            self._session.step(context)
        _redraw_cutter_apply(context)
        if self._session.done:
            self._cleanup(context)
            return {"FINISHED" if self._session.status.cutter_apply_stage == "DONE" else "CANCELLED"}
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self._session.finish(context, "CANCELLED", "Cutter operation cancelled")
        self._cleanup(context)


class OBJECT_OT_polygroups_split_object_by_cutters(bpy.types.Operator):
    bl_idname = "object.polygroups_split_object_by_cutters"
    bl_label = "Split Object"
    bl_description = "Split the active mesh into separate objects using selected cutter planes or arcs"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def execute(self, context):
        target = context.active_object
        settings = context.scene.polygroups_object_seam_cutter_settings
        cutters = _split_supported_cutters(_selected_cutters(context, target))
        if not cutters:
            self.report({"WARNING"}, "Select at least one cutter plane or arc")
            return {"CANCELLED"}

        _clear_mesh_component_selection(target.data)
        marked_edges = _apply_cutters_to_mesh(context, target, cutters)
        if not marked_edges:
            self.report({"WARNING"}, "No cut edges were created")
            return {"CANCELLED"}

        parts = _split_selected_edges(context, target, separate_objects=True)
        filled_faces = _fill_split_cut_boundaries(parts) if settings.fill_split_cutters else 0
        settings.last_cutter_count = len(cutters)
        settings.last_marked_edge_count = marked_edges

        if len(parts) > 4:
            self.report(
                {"WARNING"},
                "Split created many parts. Make sure the plane or arc fully crosses the mesh.",
            )
            return {"FINISHED"}

        self.report(
            {"INFO"},
            f"Split object with {len(cutters)} cutter object(s), created {len(parts)} part(s), filled {filled_faces} face(s)",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_select_cutter_planes(bpy.types.Operator):
    bl_idname = "object.polygroups_select_cutter_planes"
    bl_label = "Select Cutter Planes"
    bl_description = "Select all PolyGroups cutter plane objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.object.select_all(action="DESELECT")
        cutters = [
            obj
            for obj in _cutter_collection_objects()
            if _is_cutter_object(obj)
        ]
        if not cutters:
            return {"CANCELLED"}

        for obj in cutters:
            obj.hide_set(False)
            obj.hide_viewport = False
            obj.select_set(True)

        context.view_layer.objects.active = cutters[-1]
        return {"FINISHED"}


class OBJECT_OT_polygroups_clear_cutter_planes(bpy.types.Operator):
    bl_idname = "object.polygroups_clear_cutter_planes"
    bl_label = "Clear Cutter Planes"
    bl_description = "Delete all PolyGroups cutter plane objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cutters = [
            obj
            for obj in _cutter_collection_objects()
            if _is_cutter_object(obj)
        ]
        if not cutters:
            return {"CANCELLED"}

        for cutter in cutters:
            bpy.data.objects.remove(cutter, do_unlink=True)
        return {"FINISHED"}
