"""Cutter draw helpers."""
import bpy
from mathutils import Vector
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
    CUTTER_PIN_SEAMS_PROP,
    CUTTER_PROP,
    CUTTER_SOURCE_TOOL_PROP,
    CUTTER_TYPE_PROP,
)
from .cutter_paths import (
    _simplify_path_points,
    _write_cutter_path_points,
)
from .cutter_objects import (
    _add_solidify_modifier,
    _create_cutter_arc,
    _create_cutter_local_ring,
    _create_cutter_path,
    _create_cutter_plane,
    _find_path_to_continue,
    _material,
    _tool_collection,
)


class OBJECT_OT_polygroups_draw_cutter_plane(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_plane"
    bl_label = "Draw Cutter Plane"
    bl_description = "Draw an object-mode cutter plane from two viewport clicks"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the cutter start point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _start_pos = None
    _mouse_pos = None
    _draw_handle = None
    _shift_locked = False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._start_pos = None
        self._mouse_pos = None
        self._draw_handle = None
        self._shift_locked = False

        if self.use_event_as_start:
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if region is None:
                return {"CANCELLED"}

            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Cutter: A placed, click B. Hold Shift for horizontal/vertical lock")
        else:
            context.workspace.status_text_set("Object Seam Cutter: click A in the viewport. Hold Shift after A to lock axis")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._start_pos is not None and area == self._start_area and region == self._start_region:
                del rv3d
                self._shift_locked = event.shift
                self._mouse_pos = _axis_locked_region_pos(
                    self._start_pos,
                    region_pos,
                    self._shift_locked,
                )
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return {"RUNNING_MODAL"}

        if self._start_pos is None:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Cutter: A placed, click B. Hold Shift for horizontal/vertical lock")
            return {"RUNNING_MODAL"}

        if area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for both cutter points")
            return {"RUNNING_MODAL"}

        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        settings = context.scene.polygroups_object_seam_cutter_settings
        self._shift_locked = event.shift
        end_pos = _axis_locked_region_pos(self._start_pos, region_pos, self._shift_locked)
        plane = _screen_cut_plane(
            self._start_area,
            self._start_region,
            self._start_rv3d,
            self._start_pos,
            end_pos,
            target,
            settings.cutter_size_multiplier,
        )
        if plane is None:
            self.report({"WARNING"}, "Cutter line is too short")
            return {"RUNNING_MODAL"}

        cutter = _create_cutter_plane(
            "Seam_Cutter_Plane",
            plane[0],
            plane[1],
            plane[2],
            plane[3],
            settings.cutter_alpha,
            settings.cutter_solidify_thickness,
        )
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class _LocalDiskCutterInteraction:
    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _start_pos = None
    _mouse_pos = None
    _draw_handle = None
    _shift_locked = False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._start_pos = None
        self._mouse_pos = None
        self._draw_handle = None
        self._shift_locked = False

        if self.use_event_as_start:
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if region is None:
                return {"CANCELLED"}
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set(f"{self.bl_label}: A placed, click B across the local section")
        else:
            context.workspace.status_text_set(f"{self.bl_label}: click A in the viewport")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._start_pos is not None and area == self._start_area and region == self._start_region:
                del rv3d
                self._shift_locked = event.shift
                self._mouse_pos = _axis_locked_region_pos(
                    self._start_pos,
                    region_pos,
                    self._shift_locked,
                )
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return {"RUNNING_MODAL"}

        if self._start_pos is None:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._start_pos = region_pos
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set(f"{self.bl_label}: A placed, click B across the local section")
            return {"RUNNING_MODAL"}

        if area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for both cutter points")
            return {"RUNNING_MODAL"}

        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        settings = context.scene.polygroups_object_seam_cutter_settings
        self._shift_locked = event.shift
        end_pos = _axis_locked_region_pos(self._start_pos, region_pos, self._shift_locked)
        try:
            cutter = self._create_cutter(context, target, end_pos, settings)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"RUNNING_MODAL"}
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_local_ring_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_draw_cutter_local_ring(_LocalDiskCutterInteraction, bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_local_ring"
    bl_label = "Draw Local Ring Cutter"
    bl_description = "Draw a local circular cutter disk from two viewport clicks"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    def _create_cutter(self, context, target, end_pos, settings):
        surface = _screen_local_ring_surface(
            self._start_area,
            self._start_region,
            self._start_rv3d,
            self._start_pos,
            end_pos,
            target,
            settings.cutter_local_ring_radius_offset,
            settings.cutter_local_ring_fit_mode,
        )
        if surface is None:
            raise ValueError("Local ring diameter is too short")

        cutter = _create_cutter_local_ring(
            "Seam_Cutter_Local_Ring",
            surface[0],
            surface[1],
            surface[2],
            surface[3],
            settings.cutter_local_ring_segments,
            settings.cutter_alpha,
            settings.cutter_thickness,
        )
        cutter[CUTTER_PIN_SEAMS_PROP] = settings.cutter_local_ring_mark_pinned
        return cutter


class OBJECT_OT_polygroups_draw_cutter_local_contour(_LocalDiskCutterInteraction, bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_local_contour"
    bl_label = "Draw Local Contour Cutter"
    bl_description = "Click across a local part of the mesh to create a filled cutter fitted to its cross-section"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    def _create_cutter(self, context, target, end_pos, settings):
        from ..core.local_contour import fitted_section_with_retries
        from bpy_extras import view3d_utils

        seed, normal, depsgraph = _screen_section_plane(
            context, self._start_region, self._start_rv3d, self._start_pos, end_pos, target,
        )
        start_world = view3d_utils.region_2d_to_location_3d(
            self._start_region, self._start_rv3d, Vector(self._start_pos), seed)
        end_world = view3d_utils.region_2d_to_location_3d(
            self._start_region, self._start_rv3d, Vector(end_pos), seed)
        vertices, faces = fitted_section_with_retries(
            target, depsgraph, seed, normal,
            settings.cutter_contour_points, settings.cutter_contour_offset,
            search_scale=(end_world - start_world).length,
        )
        mesh = bpy.data.meshes.new("Seam_Cutter_Local_Contour")
        mesh.from_pydata([tuple(v - seed) for v in vertices], [], faces)
        mesh.update()
        cutter = bpy.data.objects.new("Seam_Cutter_Local_Contour", mesh)
        cutter.location = seed
        cutter[CUTTER_PROP] = True
        cutter[CUTTER_TYPE_PROP] = "LOCAL_CONTOUR"
        cutter[CUTTER_PIN_SEAMS_PROP] = settings.cutter_local_contour_mark_pinned
        cutter.data.materials.append(_material(settings.cutter_alpha))
        _add_solidify_modifier(cutter, settings.cutter_thickness)
        _tool_collection("LOCAL_CONTOUR").objects.link(cutter)
        return cutter


class OBJECT_OT_polygroups_draw_cutter_arc(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_arc"
    bl_label = "Draw Cutter Arc"
    bl_description = "Draw an object-mode cutter arc from three viewport clicks"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the arc start point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _points = None
    _mouse_pos = None
    _draw_handle = None
    _preview_segments = 16

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._points = []
        self._mouse_pos = None
        self._draw_handle = None
        self._preview_segments = context.scene.polygroups_object_seam_cutter_settings.cutter_arc_segments

        if self.use_event_as_start:
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if region is None:
                return {"CANCELLED"}

            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._points.append(region_pos)
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Arc Cutter: A placed, click B")
        else:
            context.workspace.status_text_set("Object Seam Arc Cutter: click A in the viewport")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._points and area == self._start_area and region == self._start_region:
                del rv3d
                self._mouse_pos = region_pos
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"RUNNING_MODAL"}

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return {"RUNNING_MODAL"}

        if not self._points:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
            self._points.append(region_pos)
            self._mouse_pos = region_pos
            self._add_draw_handler()
            context.workspace.status_text_set("Object Seam Arc Cutter: A placed, click B")
            return {"RUNNING_MODAL"}

        if area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for all arc points")
            return {"RUNNING_MODAL"}

        self._points.append(region_pos)
        self._mouse_pos = region_pos
        if len(self._points) == 2:
            context.workspace.status_text_set("Object Seam Arc Cutter: B placed, click C")
            self._tag_redraw()
            return {"RUNNING_MODAL"}

        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        settings = context.scene.polygroups_object_seam_cutter_settings
        surface = _screen_arc_surface(
            self._start_area,
            self._start_region,
            self._start_rv3d,
            self._points[0],
            self._points[1],
            self._points[2],
            target,
            settings.cutter_size_multiplier,
            settings.cutter_arc_segments,
        )
        if surface is None:
            self.report({"WARNING"}, "Arc points are too close or almost collinear")
            self._points.pop()
            return {"RUNNING_MODAL"}

        cutter = _create_cutter_arc(
            "Seam_Cutter_Arc",
            surface[0],
            surface[1],
            surface[2],
            settings.cutter_alpha,
            settings.cutter_thickness,
        )
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_arc_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()


class OBJECT_OT_polygroups_draw_cutter_path(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_path"
    bl_label = "Draw Cutter Path"
    bl_description = "Draw an object-mode cutter path snapped to the active mesh surface"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the first path point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _start_rv3d = None
    _points = None
    _surface_points = None
    _mouse_pos = None
    _mouse_surface_point = None
    _draw_handle = None
    _view_navigation_active = False

    def _is_view_navigation_event(self, event):
        if event.type == "MOUSEMOVE" and self._view_navigation_active:
            return True

        if event.type in {"MIDDLEMOUSE", "LEFTMOUSE"} and event.value == "RELEASE":
            self._view_navigation_active = False
            if event.type == "MIDDLEMOUSE":
                return True

        if event.type == "MIDDLEMOUSE" and event.value == "PRESS":
            self._view_navigation_active = True
            return True

        if event.type == "LEFTMOUSE" and event.alt:
            if event.value == "PRESS":
                self._view_navigation_active = True
            return True

        if event.type in {
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "WHEELINMOUSE",
            "WHEELOUTMOUSE",
            "TRACKPADPAN",
            "TRACKPADZOOM",
            "NDOF_MOTION",
            "NDOF_BUTTON_MENU",
            "NDOF_BUTTON_FIT",
            "NDOF_BUTTON_TOP",
            "NDOF_BUTTON_BOTTOM",
            "NDOF_BUTTON_LEFT",
            "NDOF_BUTTON_RIGHT",
            "NDOF_BUTTON_FRONT",
            "NDOF_BUTTON_BACK",
        }:
            return True

        return False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._start_rv3d = None
        self._points = []
        self._surface_points = []
        self._mouse_pos = None
        self._mouse_surface_point = None
        self._draw_handle = None
        self._view_navigation_active = False

        if self.use_event_as_start:
            if not self._add_point_from_event(context, event):
                return {"CANCELLED"}
            self._add_draw_handler()
            context.workspace.status_text_set(
                "Object Seam Path Cutter: Ctrl+Click points, navigate view normally, Enter/Space to confirm",
            )
        else:
            context.workspace.status_text_set("Object Seam Path Cutter: Ctrl+Click first surface point")

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if self._is_view_navigation_event(event):
            return {"PASS_THROUGH"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type in {"RET", "NUMPAD_ENTER", "SPACE"} and event.value == "PRESS":
            if len(self._surface_points) < 2:
                self.report({"WARNING"}, "Cutter path needs at least two points")
                return {"RUNNING_MODAL"}
            return self._create_path(context)

        if event.type == "BACK_SPACE" and event.value == "PRESS":
            if self._surface_points:
                self._points.pop()
                self._surface_points.pop()
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._surface_points and area == self._start_area and region == self._start_region:
                self._mouse_pos = region_pos
                self._mouse_surface_point = self._surface_point_from_region(context, region, rv3d, region_pos)
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"PASS_THROUGH"}

        if not event.ctrl:
            return {"PASS_THROUGH"}

        if not self._add_point_from_event(context, event):
            return {"RUNNING_MODAL"}

        if self._draw_handle is None:
            self._add_draw_handler()
        context.workspace.status_text_set(
            "Object Seam Path Cutter: Ctrl+Click points, navigate view normally, Enter/Space to confirm",
        )
        return {"RUNNING_MODAL"}

    def _add_point_from_event(self, context, event):
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            return False

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return False

        if not self._points:
            self._start_area = area
            self._start_region = region
            self._start_rv3d = rv3d
        elif area != self._start_area or region != self._start_region:
            self.report({"WARNING"}, "Use the same viewport for all path points")
            return False

        hit = _surface_hit_from_region_pos(region, rv3d, region_pos, target)
        if hit is None:
            self.report({"WARNING"}, "No surface under cursor")
            return False

        if self._surface_points:
            previous = self._surface_points[-1]["location"]
            if (hit[0] - previous).length < 0.000001:
                return False

        self._points.append(region_pos)
        self._surface_points.append(
            {
                "location": hit[0],
                "normal": hit[1],
            },
        )
        self._mouse_pos = region_pos
        self._mouse_surface_point = None
        self._tag_redraw()
        return True

    def _surface_point_from_region(self, context, region, rv3d, region_pos):
        del context
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            return None

        hit = _surface_hit_from_region_pos(region, rv3d, region_pos, target)
        if hit is None:
            return None

        if self._surface_points and (hit[0] - self._surface_points[-1]["location"]).length < 0.000001:
            return None

        return {
            "location": hit[0],
            "normal": hit[1],
        }

    def _create_path(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        cutter = None
        if settings.continue_path_cutters:
            cutter, joined_points = _find_path_to_continue(
                self._surface_points,
                settings.cutter_path_join_distance,
            )
            if cutter is not None:
                _write_cutter_path_points(cutter, joined_points)
                cutter[CUTTER_SOURCE_TOOL_PROP] = "PATH"

        if cutter is None:
            cutter = _create_cutter_path(
                "Seam_Cutter_Path",
                self._surface_points,
                settings.cutter_path_render_u,
                settings.cutter_extrude,
                settings.cutter_alpha,
                thickness=settings.cutter_thickness,
            )
        bpy.ops.object.select_all(action="DESELECT")
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_path_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._mouse_surface_point = None
        self._tag_redraw()


def _stabilize_stroke_position(current, raw, radius, factor):
    """Return a delayed screen-space point using brush-style radius and smoothing."""
    raw = Vector(raw)
    if current is None:
        return raw
    current = Vector(current)
    delta = raw - current
    radius = max(0.0, float(radius))
    if delta.length <= radius:
        return current
    target = raw - delta.normalized() * radius
    response = max(0.01, min(1.0, 1.0 - float(factor)))
    return current.lerp(target, response)


class OBJECT_OT_polygroups_draw_cutter_draw(bpy.types.Operator):
    bl_idname = "object.polygroups_draw_cutter_draw"
    bl_label = "Draw Cutter Path"
    bl_description = "Draw a freehand cutter path snapped to the active mesh surface"
    bl_options = {"REGISTER", "UNDO"}

    use_event_as_start: bpy.props.BoolProperty(
        name="Use Event As Start",
        description="Use the invoking mouse event as the first stroke point",
        default=False,
        options={"HIDDEN"},
    )

    _target_name = ""
    _start_area = None
    _start_region = None
    _points = None
    _surface_points = None
    _mouse_pos = None
    _draw_handle = None
    _view_navigation_active = False
    _is_drawing = False
    _stabilized_pos = None

    def _is_view_navigation_event(self, event):
        if event.type == "MOUSEMOVE" and self._view_navigation_active:
            return True

        if event.type in {"MIDDLEMOUSE", "LEFTMOUSE"} and event.value == "RELEASE":
            self._view_navigation_active = False
            if event.type == "MIDDLEMOUSE":
                return True

        if event.type == "MIDDLEMOUSE" and event.value == "PRESS":
            self._view_navigation_active = True
            return True

        if event.type == "LEFTMOUSE" and event.alt:
            if event.value == "PRESS":
                self._view_navigation_active = True
            return True

        if event.type in {
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "WHEELINMOUSE",
            "WHEELOUTMOUSE",
            "TRACKPADPAN",
            "TRACKPADZOOM",
            "NDOF_MOTION",
            "NDOF_BUTTON_MENU",
            "NDOF_BUTTON_FIT",
            "NDOF_BUTTON_TOP",
            "NDOF_BUTTON_BOTTOM",
            "NDOF_BUTTON_LEFT",
            "NDOF_BUTTON_RIGHT",
            "NDOF_BUTTON_FRONT",
            "NDOF_BUTTON_BACK",
        }:
            return True

        return False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        self._target_name = context.active_object.name
        self._start_area = None
        self._start_region = None
        self._points = []
        self._surface_points = []
        self._mouse_pos = None
        self._draw_handle = None
        self._view_navigation_active = False
        self._is_drawing = False
        self._stabilized_pos = None

        if self.use_event_as_start:
            self._is_drawing = True
            if not self._add_point_from_event(context, event, force=True):
                return {"CANCELLED"}
            self._add_draw_handler()
        context.workspace.status_text_set(
            "Object Seam Draw Cutter: hold Ctrl and drag on surface, release to finish",
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not self._is_drawing and self._is_view_navigation_event(event):
            return {"PASS_THROUGH"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS" and event.ctrl:
            self._is_drawing = True
            self._add_point_from_event(context, event, force=True)
            if self._draw_handle is None:
                self._add_draw_handler()
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
            if self._points and area == self._start_area and region == self._start_region:
                del rv3d
                if not (self._is_drawing and event.ctrl):
                    self._mouse_pos = region_pos
                    self._tag_redraw()
            if self._is_drawing and event.ctrl:
                self._add_point_from_event(context, event)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._is_drawing:
            self._add_point_from_event(context, event)
            if len(self._surface_points) < 2:
                self.report({"WARNING"}, "Cutter draw stroke needs at least two points")
                self._finish(context)
                return {"CANCELLED"}
            return self._create_draw_result(context)

        return {"PASS_THROUGH"}

    def _add_point_from_event(self, context, event, force=False):
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            return False

        area, region, rv3d, region_pos = _view3d_under_mouse(context, event)
        if region is None:
            return False

        if not self._points:
            self._start_area = area
            self._start_region = region
        elif area != self._start_area or region != self._start_region:
            return False

        settings = context.scene.polygroups_object_seam_cutter_settings
        if settings.cutter_draw_stabilize_stroke:
            if force:
                self._stabilized_pos = Vector(region_pos)
            else:
                self._stabilized_pos = _stabilize_stroke_position(
                    self._stabilized_pos,
                    region_pos,
                    settings.cutter_draw_stabilize_radius,
                    settings.cutter_draw_stabilize_factor,
                )
            region_pos = self._stabilized_pos
        else:
            self._stabilized_pos = Vector(region_pos)

        hit = _surface_hit_from_region_pos(region, rv3d, region_pos, target)
        if hit is None:
            return False

        if self._surface_points and not force:
            previous = self._surface_points[-1]["location"]
            if (hit[0] - previous).length < settings.cutter_draw_min_point_distance:
                return False

        self._points.append(region_pos)
        self._surface_points.append(
            {
                "location": hit[0],
                "normal": hit[1],
            },
        )
        self._mouse_pos = region_pos
        self._tag_redraw()
        return True

    def _create_draw_result(self, context):
        settings = context.scene.polygroups_object_seam_cutter_settings
        target = bpy.data.objects.get(self._target_name)
        if target is None:
            self._finish(context)
            return {"CANCELLED"}

        path_points = _simplify_path_points(
            self._surface_points,
            settings.cutter_draw_simplify_distance,
        )

        cutter = None
        if settings.continue_path_cutters:
            cutter, joined_points = _find_path_to_continue(
                path_points,
                settings.cutter_path_join_distance,
            )
            if cutter is not None:
                _write_cutter_path_points(cutter, joined_points)
                cutter[CUTTER_SOURCE_TOOL_PROP] = "DRAW"

        if cutter is None:
            cutter = _create_cutter_path(
                "Seam_Cutter_Path",
                path_points,
                settings.cutter_path_render_u,
                settings.cutter_extrude,
                settings.cutter_alpha,
                "DRAW",
                thickness=settings.cutter_thickness,
            )

        bpy.ops.object.select_all(action="DESELECT")
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target
        self._finish(context)
        return {"FINISHED"}

    def _add_draw_handler(self):
        if self._draw_handle is not None:
            return

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cutter_path_overlay,
            (self,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._tag_redraw()

    def _tag_redraw(self):
        if self._start_area is not None:
            self._start_area.tag_redraw()

    def _finish(self, context):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._tag_redraw()
