import bpy


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
        obj = context.active_object
        original_mode = obj.mode

        context.view_layer.objects.active = obj
        if obj.data.uv_layers.active is None:
            obj.data.uv_layers.new(name="UVMap")

        if original_mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.unwrap(method="ANGLE_BASED")

        if original_mode != "EDIT":
            try:
                bpy.ops.object.mode_set(mode=original_mode)
            except Exception:
                bpy.ops.object.mode_set(mode="OBJECT")

        self.report({"INFO"}, "Unwrapped UVs with Angle Based method")
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
        obj = context.active_object
        original_mode = obj.mode

        context.view_layer.objects.active = obj
        if obj.data.uv_layers.active is None:
            obj.data.uv_layers.new(name="UVMap")

        if original_mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(
            angle_limit=self.angle_limit,
            island_margin=self.island_margin,
        )

        if original_mode != "EDIT":
            try:
                bpy.ops.object.mode_set(mode=original_mode)
            except Exception:
                bpy.ops.object.mode_set(mode="OBJECT")

        self.report({"INFO"}, "Unwrapped UVs with Smart UV Project")
        return {"FINISHED"}
