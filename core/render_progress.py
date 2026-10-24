"""Live camera preview and overall Auto Render progress in 3D viewports."""
import bpy
import blf


class RenderProgressPreview:
    def __init__(self, context):
        self.scene = context.scene
        self.completed = self.total = 0
        self.asset_label = ''
        self.views = []
        self.handle = None
        if bpy.app.background:
            return
        for window in context.window_manager.windows:
            if window.scene != self.scene:
                continue
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    space = area.spaces.active
                    region = space.region_3d
                    self.views.append((area, space, region, space.camera,
                                       region.view_perspective, region.view_camera_zoom,
                                       tuple(region.view_camera_offset)))
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self.draw, (), 'WINDOW', 'POST_PIXEL')

    def show(self, completed, total, asset_label):
        self.completed, self.total, self.asset_label = completed, total, asset_label
        for area, space, region, *_ in self.views:
            space.camera = self.scene.camera
            region.view_perspective = 'CAMERA'
            region.view_camera_zoom = 0
            region.view_camera_offset = (0, 0)
            area.tag_redraw()

    def draw(self):
        context = bpy.context
        if context.scene != self.scene or context.region is None:
            return
        scale = context.preferences.system.ui_scale
        percent = 100 * self.completed / self.total if self.total else 0
        lines = [f'Render: {self.completed} / {self.total}  |  {percent:.0f}%', self.asset_label]
        blf.size(0, 15 * scale)
        for index, line in enumerate(reversed(lines)):
            x, y = 20 * scale, (24 + index * 22) * scale
            blf.color(0, 0, 0, 0, 1)
            blf.position(0, x + 1, y - 1, 0)
            blf.draw(0, line)
            blf.color(0, 1, 1, 1, 1)
            blf.position(0, x, y, 0)
            blf.draw(0, line)

    def close(self):
        if self.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
            self.handle = None
        for area, space, region, camera, perspective, zoom, offset in self.views:
            try:
                space.camera = camera
                region.view_perspective = perspective
                region.view_camera_zoom = zoom
                region.view_camera_offset = offset
                area.tag_redraw()
            except (ReferenceError, RuntimeError):
                pass
        self.views.clear()
