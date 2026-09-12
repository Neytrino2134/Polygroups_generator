import bmesh
import bpy


def ensure_active_uv(obj):
    if obj.data.uv_layers.active is None:
        obj.data.uv_layers.new(name="UVMap")


def _snapshot_edit_selection(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return {
        "verts": {vert.index for vert in bm.verts if vert.select},
        "edges": {edge.index for edge in bm.edges if edge.select},
        "faces": {face.index for face in bm.faces if face.select},
        "select_mode": tuple(bpy.context.tool_settings.mesh_select_mode),
    }


def _restore_edit_selection(obj, snapshot):
    if snapshot is None:
        return

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    for vert in bm.verts:
        vert.select = vert.index in snapshot["verts"]
    for edge in bm.edges:
        edge.select = edge.index in snapshot["edges"]
    for face in bm.faces:
        face.select = face.index in snapshot["faces"]

    bpy.context.tool_settings.mesh_select_mode = snapshot["select_mode"]
    bmesh.update_edit_mesh(obj.data)


def average_all_islands_scale(context, restore_selection=True):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return False

    original_mode = obj.mode
    context.view_layer.objects.active = obj
    ensure_active_uv(obj)

    if original_mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")

    selection_snapshot = _snapshot_edit_selection(obj) if restore_selection else None
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.select_all(action="SELECT")
    except Exception:
        pass
    bpy.ops.uv.average_islands_scale()

    if restore_selection:
        _restore_edit_selection(obj, selection_snapshot)

    if original_mode != "EDIT":
        try:
            bpy.ops.object.mode_set(mode=original_mode)
        except Exception:
            bpy.ops.object.mode_set(mode="OBJECT")

    return True


def unwrap_selected_angle_based(context, average_islands=False):
    obj = context.active_object
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return False

    ensure_active_uv(obj)
    # Seam tools can be modal or chained. Always restore their selection and
    # selection mode so automatic UV work remains an invisible post-process.
    selection_snapshot = _snapshot_edit_selection(obj)
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
    bpy.ops.uv.unwrap(method="ANGLE_BASED")
    if average_islands:
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.uv.select_all(action="SELECT")
        except Exception:
            pass
        bpy.ops.uv.average_islands_scale()
    _restore_edit_selection(obj, selection_snapshot)
    return True


def auto_uv_after_seam_change(context):
    """Unwrap the active mesh after a seam edit without changing selection."""
    settings = context.scene.polygroups_seam_finalization_settings
    if not settings.auto_unwrap_after_seam:
        return False
    obj = context.active_object
    if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
        return False

    ensure_active_uv(obj)
    selection_snapshot = _snapshot_edit_selection(obj)
    try:
        # Path tools normally leave only vertices or edges selected. Explicitly
        # select every face so Auto Unwrap always has geometry to process.
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.unwrap(method="ANGLE_BASED")
        if settings.auto_average_islands_scale_after_unwrap:
            try:
                bpy.ops.uv.select_all(action="SELECT")
            except Exception:
                pass
            bpy.ops.uv.average_islands_scale()
    finally:
        _restore_edit_selection(obj, selection_snapshot)
    return True


def unwrap_all_angle_based(context, average_islands=False):
    obj = context.active_object
    original_mode = obj.mode

    context.view_layer.objects.active = obj
    ensure_active_uv(obj)

    if original_mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")

    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED")
    if average_islands:
        try:
            bpy.ops.uv.select_all(action="SELECT")
        except Exception:
            pass
        bpy.ops.uv.average_islands_scale()

    if original_mode != "EDIT":
        try:
            bpy.ops.object.mode_set(mode=original_mode)
        except Exception:
            bpy.ops.object.mode_set(mode="OBJECT")

    return True


def smart_project_all(
    context,
    obj=None,
    angle_limit=1.1519173063162575,
    island_margin=0.02,
    mark_seams_from_islands=False,
):
    """Run Blender's native Smart UV Project on all faces of one mesh."""
    obj = obj or context.active_object
    if obj is None or obj.type != "MESH":
        return False
    original_mode = obj.mode
    obj.hide_set(False)
    context.view_layer.objects.active = obj
    ensure_active_uv(obj)
    if original_mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        result = bpy.ops.uv.smart_project(angle_limit=angle_limit, island_margin=island_margin)
        if "FINISHED" not in result:
            return False
        if mark_seams_from_islands:
            try:
                bpy.ops.uv.select_all(action="SELECT")
            except Exception:
                pass
            result = bpy.ops.uv.seams_from_islands(mark_seams=True, mark_sharp=False)
            if "FINISHED" not in result:
                return False
    finally:
        if original_mode != "EDIT" and obj.mode == "EDIT":
            try:
                bpy.ops.object.mode_set(mode=original_mode)
            except Exception:
                bpy.ops.object.mode_set(mode="OBJECT")
    return True


def smart_uv_unwrap_all(context, obj=None):
    """Generate smart seams and unwrap one mesh using the add-on workflow."""
    obj = obj or context.active_object
    if obj is None or obj.type != "MESH":
        return False, False

    original_mode = obj.mode
    seam_settings = context.scene.polygroups_seam_finalization_settings
    context.view_layer.objects.active = obj
    obj.hide_set(False)
    if original_mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")

    packed = False
    try:
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        auto_unwrap = seam_settings.auto_unwrap_after_seam
        seam_settings.auto_unwrap_after_seam = False
        try:
            result = bpy.ops.mesh.polygroups_mark_smart_angle_seams()
        finally:
            seam_settings.auto_unwrap_after_seam = auto_unwrap
        if "FINISHED" not in result:
            return False, False

        unwrap_all_angle_based(
            context,
            average_islands=seam_settings.auto_average_islands_scale_after_unwrap,
        )
        if seam_settings.smart_uv_unwrap_auto_pack:
            bpy.ops.uv.select_all(action="SELECT")
            bpy.ops.uv.pack_islands()
            packed = True
    finally:
        if original_mode != "EDIT" and obj.mode == "EDIT":
            try:
                bpy.ops.object.mode_set(mode=original_mode)
            except Exception:
                bpy.ops.object.mode_set(mode="OBJECT")

    return True, packed


class OBJECT_OT_polygroups_unwrap_angle_based(bpy.types.Operator):
    bl_idname = "object.polygroups_unwrap_angle_based"
    bl_label = "Unwrap Angle Based"
    bl_description = "Select the active mesh and unwrap UVs using Blender's Angle Based method"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        settings = context.scene.polygroups_seam_finalization_settings
        unwrap_all_angle_based(context, average_islands=settings.auto_average_islands_scale_after_unwrap)

        suffix = " and averaged UV island scale" if settings.auto_average_islands_scale_after_unwrap else ""
        self.report({"INFO"}, f"Unwrapped UVs with Angle Based method{suffix}")
        return {"FINISHED"}


class OBJECT_OT_polygroups_smart_uv_project(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_uv_project"
    bl_label = "Smart UV Project"
    bl_description = "Select the active mesh and unwrap UVs using Blender's Smart UV Project"
    bl_options = {"REGISTER", "UNDO"}

    angle_limit: bpy.props.FloatProperty(
        name="Angle Limit",
        default=1.1519173063162575,
        min=0.017453292519943295,
        max=1.5533430342749532,
        subtype="ANGLE",
    )
    island_margin: bpy.props.FloatProperty(
        name="Island Margin",
        default=0.02,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        smart_project_all(
            context,
            angle_limit=self.angle_limit,
            island_margin=self.island_margin,
        )
        self.report({"INFO"}, "Unwrapped UVs with Smart UV Project")
        return {"FINISHED"}


class OBJECT_OT_polygroups_smart_uv_unwrap(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_uv_unwrap"
    bl_label = "Smart UV Unwrap"
    bl_description = "Generate smart seams, unwrap with Angle Based, and optionally pack UV islands"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        success, packed = smart_uv_unwrap_all(context)
        if not success:
            return {"CANCELLED"}
        suffix = " and packed islands" if packed else ""
        self.report({"INFO"}, f"Generated smart seams and unwrapped UVs{suffix}")
        return {"FINISHED"}


class OBJECT_OT_polygroups_average_islands_scale(bpy.types.Operator):
    bl_idname = "object.polygroups_average_islands_scale"
    bl_label = "Average Islands Scale"
    bl_description = "Average UV island scale for all UV islands on the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        average_all_islands_scale(context, restore_selection=True)

        self.report({"INFO"}, "Averaged UV island scale")
        return {"FINISHED"}
