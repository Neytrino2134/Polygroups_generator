import bpy


BISECT_OPERATOR_IDS = {"MESH_OT_bisect", "mesh.bisect"}
POST_CUT_RETRY_LIMIT = 20
POST_CUT_INTERVAL = 0.1


def _has_running_operator(window_manager, operator_ids):
    for operator in window_manager.operators:
        identifier = getattr(operator, "bl_idname", None)
        if not identifier:
            bl_rna = getattr(operator, "bl_rna", None)
            identifier = getattr(bl_rna, "identifier", "")

        if identifier in operator_ids:
            return True

    return False


def _edge_key(edge):
    return tuple(sorted((edge.vertices[0], edge.vertices[1])))


def _capture_edge_keys(obj):
    return {_edge_key(edge) for edge in obj.data.edges}


def _select_all_edit_mesh():
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
    bpy.ops.mesh.select_all(action="SELECT")


def _apply_post_cut_bmesh(obj_name, original_edge_keys, mark_seam, clear_selection_after_cutting):
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return False

    import bmesh

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    if mark_seam:
        for edge in bm.edges:
            current_key = tuple(sorted((edge.verts[0].index, edge.verts[1].index)))
            if current_key not in original_edge_keys:
                edge.seam = True

    if clear_selection_after_cutting:
        for vertex in bm.verts:
            vertex.select = False
        for edge in bm.edges:
            edge.select = False
        for face in bm.faces:
            face.select = False
        bm.select_flush_mode()

    bmesh.update_edit_mesh(obj.data)
    return True


def _schedule_post_cut_processing(obj_name, original_edge_keys, mark_seam, clear_selection_after_cutting):
    state = {"attempts": 0}

    def _callback():
        if _has_running_operator(bpy.context.window_manager, BISECT_OPERATOR_IDS):
            state["attempts"] += 1
            return POST_CUT_INTERVAL if state["attempts"] < POST_CUT_RETRY_LIMIT else None

        result = _apply_post_cut_bmesh(
            obj_name,
            original_edge_keys,
            mark_seam,
            clear_selection_after_cutting,
        )
        if result is False:
            state["attempts"] += 1
            return POST_CUT_INTERVAL if state["attempts"] < POST_CUT_RETRY_LIMIT else None

        return None

    bpy.app.timers.register(_callback, first_interval=POST_CUT_INTERVAL)


class MESH_OT_polygroups_quick_knife_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_quick_knife_seam"
    bl_label = "Quick Knife Seam"
    bl_description = "Single-gesture cut through the mesh, then mark the cut as seams and optionally clear selection"
    bl_options = {"REGISTER", "UNDO"}

    use_fill: bpy.props.BoolProperty(
        name="Fill",
        description="Fill the cut with a new face",
        default=False,
    )
    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Tolerance for the bisect cut",
        default=0.0001,
        min=0.0,
        soft_max=0.01,
        precision=5,
    )
    mark_seam: bpy.props.BoolProperty(
        name="Mark As Seam",
        description="Mark newly created cut edges as seams",
        default=True,
    )
    clear_selection_after_cutting: bpy.props.BoolProperty(
        name="Clear Selection After Cutting",
        description="Deselect vertices, edges, and faces after the cut",
        default=True,
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
        settings = context.scene.polygroups_quick_knife_seam_settings

        self._object_name = obj.name
        self._finished = False
        self._postprocess_delay = 0
        self._original_edge_keys = _capture_edge_keys(obj)
        self.use_fill = settings.use_fill
        self.threshold = settings.threshold
        self.mark_seam = settings.mark_seam
        self.clear_selection_after_cutting = settings.clear_selection_after_cutting

        _select_all_edit_mesh()

        result = bpy.ops.mesh.bisect(
            "INVOKE_DEFAULT",
            use_fill=self.use_fill,
            clear_inner=False,
            clear_outer=False,
            threshold=self.threshold,
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

        if _has_running_operator(context.window_manager, BISECT_OPERATOR_IDS):
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
