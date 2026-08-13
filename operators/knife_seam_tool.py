import bpy


KNIFE_OPERATOR_IDS = {"MESH_OT_knife_tool", "mesh.knife_tool"}
POST_CUT_RETRY_LIMIT = 20
POST_CUT_INTERVAL = 0.1


def _has_running_knife_tool(window_manager):
    for operator in window_manager.operators:
        identifier = getattr(operator, "bl_idname", None)
        if not identifier:
            bl_rna = getattr(operator, "bl_rna", None)
            identifier = getattr(bl_rna, "identifier", "")

        if identifier in KNIFE_OPERATOR_IDS:
            return True

    return False


def _edge_key(edge):
    return tuple(sorted((edge.vertices[0], edge.vertices[1])))


def _capture_edge_keys(obj):
    return {_edge_key(edge) for edge in obj.data.edges}


def _apply_post_cut_bmesh(obj_name, original_edge_keys, mark_seam, clear_selection_after_cutting):
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return False

    import bmesh

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    marked_count = 0
    if mark_seam:
        for edge in bm.edges:
            current_key = tuple(sorted((edge.verts[0].index, edge.verts[1].index)))
            if current_key not in original_edge_keys and not edge.seam:
                edge.seam = True
                marked_count += 1

    if clear_selection_after_cutting:
        for vertex in bm.verts:
            vertex.select = False
        for edge in bm.edges:
            edge.select = False
        for face in bm.faces:
            face.select = False
        bm.select_flush_mode()

    bmesh.update_edit_mesh(obj.data)
    return marked_count


def _schedule_post_cut_processing(obj_name, original_edge_keys, mark_seam, clear_selection_after_cutting):
    state = {"attempts": 0}

    def _callback():
        if _has_running_knife_tool(bpy.context.window_manager):
            state["attempts"] += 1
            return POST_CUT_INTERVAL if state["attempts"] < POST_CUT_RETRY_LIMIT else None

        marked_count = _apply_post_cut_bmesh(
            obj_name,
            original_edge_keys,
            mark_seam,
            clear_selection_after_cutting,
        )

        if marked_count is False:
            state["attempts"] += 1
            return POST_CUT_INTERVAL if state["attempts"] < POST_CUT_RETRY_LIMIT else None

        return None

    bpy.app.timers.register(_callback, first_interval=POST_CUT_INTERVAL)


class MESH_OT_polygroups_knife_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_knife_seam"
    bl_label = "Knife Seam"
    bl_description = "Cut through the full mesh with Knife Tool and mark new cut edges as seams"
    bl_options = {"REGISTER", "UNDO"}

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
    _postprocess_delay = 0
    _original_edge_keys = None

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def invoke(self, context, event):
        del event
        obj = context.active_object
        self._object_name = obj.name
        self._finished = False
        self._postprocess_delay = 0
        self._original_edge_keys = _capture_edge_keys(obj)
        settings = context.scene.polygroups_knife_seam_settings

        self.use_occlude_geometry = settings.use_occlude_geometry
        self.only_selected = settings.only_selected
        self.xray = settings.xray
        self.mark_seam = settings.mark_seam
        self.clear_selection_after_cutting = settings.clear_selection_after_cutting

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
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        obj = bpy.data.objects.get(self._object_name)
        if obj is None:
            self._finish(context)
            return {"CANCELLED"}

        if _has_running_knife_tool(context.window_manager):
            self._postprocess_delay = 0
            return {"PASS_THROUGH"}

        if self._postprocess_delay < 2:
            self._postprocess_delay += 1
            return {"PASS_THROUGH"}

        _schedule_post_cut_processing(
            self._object_name,
            self._original_edge_keys,
            mark_seam=self.mark_seam,
            clear_selection_after_cutting=self.clear_selection_after_cutting,
        )

        self._finish(context)
        return {"FINISHED"}

    def _finish(self, context):
        if self._finished:
            return

        self._finished = True
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
