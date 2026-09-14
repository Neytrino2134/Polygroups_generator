import bpy


class RENDER_OT_polygroups_apply_resolution(bpy.types.Operator):
    bl_idname = "render.polygroups_apply_resolution"
    bl_label = "Apply to Blender Format"
    bl_description = "Copy the add-on resolution into Blender Output Format for camera-frame preview"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        render = context.scene.render
        render.resolution_x = settings.resolution_x
        render.resolution_y = settings.resolution_y
        render.resolution_percentage = settings.resolution_scale
        render.pixel_aspect_x = 1.0
        render.pixel_aspect_y = 1.0
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
        self.report({"INFO"}, f"Blender Format: {render.resolution_x} × {render.resolution_y} at {render.resolution_percentage}%")
        return {"FINISHED"}
