"""UV Preserve Decimate: meshoptimizer half-edge collapse that keeps every UV exact."""
from math import radians

import bpy

from ..core import meshopt_simplify
from .smart_decimate import _duplicate_mesh_object, run_on_generated_targets

UV_PRESERVE_DUPLICATE_SUFFIX = "_UVDecimated"


class OBJECT_OT_polygroups_uv_preserve_decimate(bpy.types.Operator):
    bl_idname = "object.polygroups_uv_preserve_decimate"
    bl_label = "UV Preserve Decimate"
    bl_description = ("Decimate with meshoptimizer: edges collapse into existing vertices, so positions "
                      "and UVs stay exact and textures do not slide; no UV re-unwrap needed")
    bl_options = {"REGISTER", "UNDO"}

    triangle_limit: bpy.props.IntProperty(
        name="Triangle Limit", description="Target triangle count; 0 uses Ratio", default=0, min=0)
    ratio: bpy.props.FloatProperty(
        name="Ratio", description="Fraction of source triangles to keep when Triangle Limit is 0",
        default=0.25, min=0.0, max=1.0, subtype="FACTOR")
    seam_mode: bpy.props.EnumProperty(name="Seams", items=meshopt_simplify.SEAM_MODE_ITEMS, default="LOCK")
    uv_weight: bpy.props.FloatProperty(
        name="UV Weight", description="Importance of UV error relative to geometric error",
        default=1.0, min=0.0, soft_max=10.0)
    max_error: bpy.props.FloatProperty(
        name="Max Error", description="Stop before this relative error (1.0 = only the triangle budget limits)",
        default=1.0, min=0.0, max=1.0, subtype="FACTOR")
    lock_open_borders: bpy.props.BoolProperty(
        name="Lock Open Borders", description="Never move vertices on open mesh borders", default=False)
    join_triangles: bpy.props.BoolProperty(
        name="Join Triangles To Quads",
        description="Merge triangle pairs into quads without moving vertices or crossing seams/materials",
        default=True)
    join_angle: bpy.props.FloatProperty(
        name="Quad Angle", description="Max face and shape angle for joining triangle pairs into quads",
        default=radians(60), min=0.0, max=radians(180), subtype="ANGLE")
    duplicate: bpy.props.BoolProperty(
        name="Decimate A Duplicate", description="Keep the active object and decimate a copy", default=True)
    hide_source: bpy.props.BoolProperty(
        name="Hide LOW After Decimate", default=False,
        description="Disable the original LOW object in the viewport after successful decimation")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        source_obj = context.active_object
        if not source_obj.data.uv_layers:
            self.report({"WARNING"}, f"{source_obj.name}: mesh has no UV map")
            return {"CANCELLED"}
        if not meshopt_simplify.is_available():
            self.report({"ERROR"}, f"meshoptimizer library missing: {meshopt_simplify.DLL_PATH}")
            return {"CANCELLED"}
        if source_obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        if self.duplicate:
            obj = _duplicate_mesh_object(context, source_obj, UV_PRESERVE_DUPLICATE_SUFFIX)
        else:
            obj = source_obj
            if obj.data.users > 1:
                obj.data = obj.data.copy()
        source_triangles = meshopt_simplify.triangle_count(obj.data)
        target = self.triangle_limit or max(1, round(source_triangles * self.ratio))
        try:
            stats = meshopt_simplify.simplify_mesh(
                obj.data, target, seam_mode=self.seam_mode, uv_weight=self.uv_weight,
                max_error=self.max_error, lock_open_borders=self.lock_open_borders,
                join_triangles=self.join_triangles, join_angle=self.join_angle)
        except (RuntimeError, ValueError) as error:
            if self.duplicate:
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            self.report({"WARNING"}, f"{source_obj.name}: UV Preserve Decimate failed: {error}")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
        from ..core.smart_arrange import arrange_decimated
        arrange_decimated(context, source_obj, obj)
        if self.hide_source and obj is not source_obj:
            source_obj.hide_viewport = True
        unreached = stats["triangles"] > target
        message = (f"UV Preserve Decimate: {stats['source_triangles']} -> {stats['triangles']}/{target} tris, "
                   f"{stats['polygons']} faces, {stats['locked']} seam vertices {self.seam_mode.lower()}")
        if unreached:
            message += "; triangle limit not reached (try Prefer Seams or a higher Max Error)"
        self.report({"WARNING"} if unreached else {"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_uv_preserve_decimate_all_generated(bpy.types.Operator):
    bl_idname = "object.polygroups_uv_preserve_decimate_all_generated"
    bl_label = "UV Preserve Decimate All Generated"
    bl_description = "UV Preserve Decimate the highest numbered Retopo in each Generated.N collection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and not context.scene.polygroups_model_preparation_settings.batch_is_running)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        return run_on_generated_targets(
            self, context, "UV Preserve Decimate", settings.uv_decimate_hide_source,
            lambda: bpy.ops.object.polygroups_uv_preserve_decimate(
                triangle_limit=settings.uv_decimate_triangle_limit,
                ratio=settings.uv_decimate_ratio,
                seam_mode=settings.uv_decimate_seam_mode,
                uv_weight=settings.uv_decimate_uv_weight,
                max_error=settings.uv_decimate_max_error,
                lock_open_borders=settings.uv_decimate_lock_open_borders,
                join_triangles=settings.uv_decimate_join_triangles,
                join_angle=settings.uv_decimate_join_angle,
                duplicate=settings.uv_decimate_duplicate,
                hide_source=settings.uv_decimate_hide_source,
            ),
        )
