import bpy


POST_CUT_RETRY_LIMIT = 20
POST_CUT_INTERVAL = 0.1


def _select_all_edit_mesh():
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
    bpy.ops.mesh.select_all(action="SELECT")


def _mark_selected_edges(obj_name, clear_selection_after_cutting):
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return None

    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")
    bpy.ops.mesh.mark_seam(clear=False)

    if clear_selection_after_cutting:
        bpy.ops.mesh.select_all(action="DESELECT")

    return True


class MESH_OT_polygroups_quick_knife_seam(bpy.types.Operator):
    bl_idname = "mesh.polygroups_quick_knife_seam"
    bl_label = "Quick Knife Seam"
    bl_description = "Use Bisect and mark its cut line as seams after confirming"
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
        description="Mark the Bisect cut line as seams after confirming the cut",
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
    _confirmation_requested = False
    _confirmation_delay = 0
    _postprocess_attempts = 0
    _cancel_requested = False

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
        self._confirmation_requested = False
        self._confirmation_delay = 0
        self._postprocess_attempts = 0
        self._cancel_requested = False
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

        self._timer = context.window_manager.event_timer_add(
            POST_CUT_INTERVAL,
            window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._cancel_requested = True
            return {"PASS_THROUGH"}

        if event.value == "PRESS" and event.type in {"SPACE", "RET", "NUMPAD_ENTER"}:
            self._confirmation_requested = True
            self._confirmation_delay = 0
            self._postprocess_attempts = 0
            return {"PASS_THROUGH"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
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
            self.clear_selection_after_cutting,
        )
        if marked_count is not None:
            self._finish(context)
            return {"FINISHED"}

        self._postprocess_attempts += 1
        if self._postprocess_attempts >= POST_CUT_RETRY_LIMIT:
            self.report({"WARNING"}, "Bisect finished, but selected edges were not ready")
            self._finish(context)
            return {"CANCELLED"}

        return {"PASS_THROUGH"}

    def _finish(self, context):
        if self._finished:
            return

        self._finished = True
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
