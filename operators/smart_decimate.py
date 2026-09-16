import bpy
import re


SMART_DECIMATE_GROUP_NAME = "AI Retopo UV Seam Protect"
SMART_DECIMATE_MODIFIER_NAME = "Smart Decimate"
SEAMS_DECIMATE_MODIFIER_NAME = "Seams Decimate"
SMART_DECIMATE_DUPLICATE_SUFFIX = "_SmartDecimated"


def _clear_vertex_group(obj, group):
    vertex_indices = [vertex.index for vertex in obj.data.vertices]
    if not vertex_indices:
        return

    try:
        group.remove(vertex_indices)
    except RuntimeError:
        pass


def _select_seam_edges(obj):
    mesh = obj.data

    for vertex in mesh.vertices:
        vertex.select = False
    for edge in mesh.edges:
        edge.select = edge.use_seam
        if edge.use_seam:
            for vertex_index in edge.vertices:
                mesh.vertices[vertex_index].select = True
    for polygon in mesh.polygons:
        polygon.select = False

    mesh.update()


def _decimated_name(name):
    match = re.search(r"\.\d+$", name)
    if match:
        return f"{name[:match.start()]}{SMART_DECIMATE_DUPLICATE_SUFFIX}{match.group()}"
    return f"{name}{SMART_DECIMATE_DUPLICATE_SUFFIX}"


def _duplicate_mesh_object(context, obj):
    duplicate = obj.copy()
    duplicate.data = obj.data.copy()
    duplicate.animation_data_clear()
    duplicate.name = _decimated_name(obj.name)
    duplicate.data.name = _decimated_name(obj.data.name)

    for collection in obj.users_collection or (context.scene.collection,):
        collection.objects.link(duplicate)

    return duplicate


class OBJECT_OT_polygroups_smart_decimate(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_decimate"
    bl_label = "Smart Decimate"
    bl_description = "Decimate seam vertices and non-seam areas with separate ratios"
    bl_options = {"REGISTER", "UNDO"}

    triangle_limit: bpy.props.IntProperty(
        name="Triangle Limit",
        description="Automatically fit decimate ratios to this triangle budget; 0 uses manual ratios",
        default=0,
        min=0,
    )
    ratio: bpy.props.FloatProperty(
        name="Ratio",
        description="Decimate ratio for non-seam areas",
        default=0.4,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    seams_ratio: bpy.props.FloatProperty(
        name="Seams Decimate Ratio",
        description="Decimate ratio for seam vertices",
        default=0.9,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    duplicate_and_apply: bpy.props.BoolProperty(
        name="Duplicate And Apply Decimate",
        description="Duplicate the active object, add Smart Decimate to the duplicate, and apply it",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        source_obj = context.active_object
        original_mode = source_obj.mode

        context.view_layer.objects.active = source_obj
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        obj = _duplicate_mesh_object(context, source_obj) if self.duplicate_and_apply else source_obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj

        seam_edges = [edge for edge in obj.data.edges if edge.use_seam]
        if not seam_edges:
            if self.duplicate_and_apply:
                bpy.data.objects.remove(obj, do_unlink=True)
                context.view_layer.objects.active = source_obj
                source_obj.select_set(True)
            self.report({"WARNING"}, "Active mesh has no UV seam edges")
            return {"CANCELLED"}

        seam_vertex_indices = sorted(
            {
                vertex_index
                for edge in seam_edges
                for vertex_index in edge.vertices
            }
        )

        group = obj.vertex_groups.get(SMART_DECIMATE_GROUP_NAME)
        if group is None:
            group = obj.vertex_groups.new(name=SMART_DECIMATE_GROUP_NAME)
        else:
            _clear_vertex_group(obj, group)
        group.add(seam_vertex_indices, 1.0, "REPLACE")
        obj.vertex_groups.active_index = group.index

        seams_modifier = obj.modifiers.get(SEAMS_DECIMATE_MODIFIER_NAME)
        if seams_modifier is None or seams_modifier.type != "DECIMATE":
            seams_modifier = obj.modifiers.new(SEAMS_DECIMATE_MODIFIER_NAME, "DECIMATE")
        seams_modifier.decimate_type = "COLLAPSE"
        seams_modifier.ratio = self.seams_ratio
        seams_modifier.vertex_group = group.name
        seams_modifier.invert_vertex_group = False
        seams_modifier.vertex_group_factor = 1.0

        modifier = obj.modifiers.get(SMART_DECIMATE_MODIFIER_NAME)
        if modifier is None or modifier.type != "DECIMATE":
            modifier = obj.modifiers.new(SMART_DECIMATE_MODIFIER_NAME, "DECIMATE")

        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = self.ratio
        modifier.vertex_group = group.name
        modifier.invert_vertex_group = True
        modifier.vertex_group_factor = 1.0

        # Keep the seam pass before the non-seam pass, including on repeated runs.
        while obj.modifiers.find(seams_modifier.name) > obj.modifiers.find(modifier.name):
            bpy.ops.object.modifier_move_up(modifier=seams_modifier.name)

        _select_seam_edges(obj)

        budget_suffix = ""
        budget_unreached = False
        if self.triangle_limit > 0:
            from .smart_lods import _fit_ratios

            triangles, body_ratio, seam_ratio = _fit_ratios(
                obj, seams_modifier, modifier, self.triangle_limit,
                context.evaluated_depsgraph_get(),
            )
            budget_unreached = triangles > self.triangle_limit
            budget_suffix = (
                f", {triangles}/{self.triangle_limit} tris "
                f"(body {body_ratio:.3f}, seams {seam_ratio:.3f})"
            )
            if budget_unreached:
                budget_suffix += "; triangle limit could not be reached"

        applied_suffix = ""
        if self.duplicate_and_apply:
            try:
                bpy.ops.object.modifier_apply(modifier=seams_modifier.name)
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                applied_suffix = ", applied to duplicate"
            except RuntimeError as error:
                self.report({"WARNING"}, f"{obj.name}: {error}")

        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        self.report(
            {"WARNING"} if budget_unreached else {"INFO"},
            (
                f"Seams Decimate and Smart Decimate added: {len(seam_vertex_indices)} seam "
                f"vertex/vertices from {len(seam_edges)} seam edge(s){applied_suffix}{budget_suffix}"
            ),
        )
        return {"FINISHED"}
