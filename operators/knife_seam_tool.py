import bpy
from mathutils import Vector


POST_CUT_RETRY_LIMIT = 20
POST_CUT_INTERVAL = 0.1


def _mark_selected_edges(obj_name, clear_selection_after_cutting):
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return None

    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
    bpy.ops.mesh.mark_seam(clear=False)

    if clear_selection_after_cutting:
        bpy.ops.mesh.select_all(action="DESELECT")

    return True


def _screen_plane_world(context, start_region_pos, end_region_pos):
    from bpy_extras import view3d_utils

    region = context.region
    rv3d = context.region_data
    start = Vector(start_region_pos)
    end = Vector(end_region_pos)

    if (end - start).length < 2.0:
        return None, None

    start_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, start)
    end_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, end)
    start_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, start)
    end_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, end)

    if rv3d.is_perspective:
        plane_co = start_origin
        plane_no = start_vector.cross(end_vector)
    else:
        plane_co = start_origin
        plane_no = (end_origin - start_origin).cross(start_vector)

    if plane_no.length < 0.000001:
        return None, None

    plane_no.normalize()
    return plane_co, plane_no


def _world_plane_to_local(obj, plane_co, plane_no):
    matrix = obj.matrix_world
    local_co = matrix.inverted() @ plane_co
    local_no = matrix.to_3x3().transposed() @ plane_no
    local_no.normalize()
    return local_co, local_no


def _stable_view_cut(
    obj_name,
    plane_co,
    plane_no,
    only_selected,
    mark_seam,
    clear_selection_after_cutting,
):
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return None

    import bmesh

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    if only_selected:
        geom = [
            element
            for sequence in (bm.verts, bm.edges, bm.faces)
            for element in sequence
            if element.select and not element.hide
        ]
    else:
        geom = [
            element
            for sequence in (bm.verts, bm.edges, bm.faces)
            for element in sequence
            if not element.hide
        ]

    if not geom:
        return 0

    if clear_selection_after_cutting:
        for vertex in bm.verts:
            vertex.select = False
        for edge in bm.edges:
            edge.select = False
        for face in bm.faces:
            face.select = False

    local_co, local_no = _world_plane_to_local(obj, plane_co, plane_no)
    result = bmesh.ops.bisect_plane(
        bm,
        geom=geom,
        plane_co=local_co,
        plane_no=local_no,
        clear_inner=False,
        clear_outer=False,
    )

    cut_edges = [element for element in result.get("geom_cut", ()) if isinstance(element, bmesh.types.BMEdge)]
    for edge in cut_edges:
        edge.select = not clear_selection_after_cutting
        if mark_seam:
            edge.seam = True

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return len(cut_edges)


class MESH_OT_polygroups_knife_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_knife_seam"
    bl_label = "Knife Seam"
    bl_description = "Use Knife Tool and mark its selected cut edges as seams after confirming"
    bl_options = {"REGISTER", "UNDO"}

    stable_view_cut: bpy.props.BoolProperty(
        name="Stable View Cut",
        description="Use a continuous viewport-plane cut instead of Blender's screen Knife Tool",
        default=True,
    )
    use_occlude_geometry: bpy.props.BoolProperty(
        name="Occlude Geometry",
        description="Limit the cut to visible geometry only",
        default=False,
    )
    only_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Only cut currently selected geometry",
        default=False,
    )
    xray: bpy.props.BoolProperty(
        name="X-Ray",
        description="Show the cut through the mesh while drawing",
        default=True,
    )
    mark_seam: bpy.props.BoolProperty(
        name="Mark As Seam",
        description="Mark selected knife-cut edges as seams after confirming the cut",
        default=True,
    )
    clear_selection_after_cutting: bpy.props.BoolProperty(
        name="Clear Selection After Cutting",
        description="Deselect vertices, edges, and faces after post-cut processing",
        default=False,
    )

    _timer = None
    _object_name = ""
    _finished = False
    _confirmation_requested = False
    _confirmation_delay = 0
    _postprocess_attempts = 0
    _cancel_requested = False
    _start_region_pos = None
    _end_region_pos = None
    _using_stable_view_cut = False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def invoke(self, context, event):
        obj = context.active_object
        self._object_name = obj.name
        self._finished = False
        self._confirmation_requested = False
        self._confirmation_delay = 0
        self._postprocess_attempts = 0
        self._cancel_requested = False
        self._start_region_pos = None
        self._end_region_pos = None
        settings = context.scene.polygroups_knife_seam_settings

        self.stable_view_cut = settings.stable_view_cut
        self.use_occlude_geometry = settings.use_occlude_geometry
        self.only_selected = settings.only_selected
        self.xray = settings.xray
        self.mark_seam = settings.mark_seam
        self.clear_selection_after_cutting = settings.clear_selection_after_cutting

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
        self._using_stable_view_cut = self.stable_view_cut

        if self._using_stable_view_cut:
            self._start_region_pos = (event.mouse_region_x, event.mouse_region_y)
            context.workspace.status_text_set("Knife Seam: click end point, then press Space/Enter")
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}

        result = bpy.ops.mesh.knife_tool(
            "INVOKE_DEFAULT",
            use_occlude_geometry=self.use_occlude_geometry,
            only_selected=self.only_selected,
            xray=self.xray,
            wait_for_input=False,
        )
        if "RUNNING_MODAL" not in result:
            return result

        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if self._using_stable_view_cut:
            return self._modal_stable_view_cut(context, event)

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            # Let Knife consume its cancel event, then remove this observer on timer.
            self._cancel_requested = True
            return {"PASS_THROUGH"}

        if event.type in {"SPACE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            # Pass the confirmation to Knife first; selection appears a moment later.
            self._confirmation_requested = True
            self._confirmation_delay = 0
            self._postprocess_attempts = 0
            return {"PASS_THROUGH"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._cancel_requested:
            self._finish(context)
            return {"CANCELLED"}

        if not self._confirmation_requested:
            return {"PASS_THROUGH"}

        if self._confirmation_delay < 2:
            self._confirmation_delay += 1
            return {"PASS_THROUGH"}

        if not self.mark_seam:
            self._finish(context)
            return {"FINISHED"}

        marked_count = _mark_selected_edges(
            self._object_name,
            clear_selection_after_cutting=self.clear_selection_after_cutting,
        )
        if marked_count is not None:
            self._finish(context)
            return {"FINISHED"}

        self._postprocess_attempts += 1
        if self._postprocess_attempts >= POST_CUT_RETRY_LIMIT:
            self.report({"WARNING"}, "Knife cut finished, but selected edges were not ready")
            self._finish(context)
            return {"CANCELLED"}

        return {"PASS_THROUGH"}

    def _modal_stable_view_cut(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self._end_region_pos is None:
                self._end_region_pos = (event.mouse_region_x, event.mouse_region_y)
                context.workspace.status_text_set("Knife Seam: press Space/Enter to apply")
            return {"RUNNING_MODAL"}

        if event.type in {"SPACE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            if self._end_region_pos is None:
                self.report({"WARNING"}, "Click the end point before confirming the cut")
                return {"RUNNING_MODAL"}

            plane_co, plane_no = _screen_plane_world(
                context,
                self._start_region_pos,
                self._end_region_pos,
            )
            if plane_co is None:
                self.report({"WARNING"}, "Knife Seam line is too short")
                self._finish(context)
                return {"CANCELLED"}

            cut_count = _stable_view_cut(
                self._object_name,
                plane_co,
                plane_no,
                self.only_selected,
                self.mark_seam,
                self.clear_selection_after_cutting,
            )
            self._finish(context)
            if cut_count is None:
                return {"CANCELLED"}
            if cut_count == 0:
                self.report({"WARNING"}, "Knife Seam did not intersect the editable mesh")
            return {"FINISHED"}

        return {"RUNNING_MODAL"}

    def _finish(self, context):
        if self._finished:
            return

        self._finished = True
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.workspace.status_text_set(None)
