import bpy


SMART_DECIMATE_GROUP_NAME = "AI Retopo UV Seam Protect"
SMART_DECIMATE_MODIFIER_NAME = "Smart Decimate"
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


def _duplicate_mesh_object(context, obj):
    duplicate = obj.copy()
    duplicate.data = obj.data.copy()
    duplicate.animation_data_clear()
    duplicate.name = f"{obj.name}{SMART_DECIMATE_DUPLICATE_SUFFIX}"
    duplicate.data.name = f"{obj.data.name}{SMART_DECIMATE_DUPLICATE_SUFFIX}"

    target_collection = context.collection or context.scene.collection
    target_collection.objects.link(duplicate)

    return duplicate


class OBJECT_OT_polygroups_smart_decimate(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_decimate"
    bl_label = "Smart Decimate"
    bl_description = "Protect UV seam vertices with a vertex group, then add an inverted Decimate modifier"
    bl_options = {"REGISTER", "UNDO"}

    ratio: bpy.props.FloatProperty(
        name="Ratio",
        description="Decimate ratio for non-seam areas",
        default=0.4,
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

        modifier = obj.modifiers.get(SMART_DECIMATE_MODIFIER_NAME)
        if modifier is None or modifier.type != "DECIMATE":
            modifier = obj.modifiers.new(SMART_DECIMATE_MODIFIER_NAME, "DECIMATE")

        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = self.ratio
        modifier.vertex_group = group.name
        modifier.invert_vertex_group = True
        modifier.vertex_group_factor = 1.0

        _select_seam_edges(obj)

        applied_suffix = ""
        if self.duplicate_and_apply:
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                applied_suffix = ", applied to duplicate"
            except RuntimeError as error:
                self.report({"WARNING"}, f"{obj.name}: {error}")

        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        self.report(
            {"INFO"},
            (
                f"Smart Decimate added: protected {len(seam_vertex_indices)} seam "
                f"vertex/vertices from {len(seam_edges)} seam edge(s){applied_suffix}"
            ),
        )
        return {"FINISHED"}
