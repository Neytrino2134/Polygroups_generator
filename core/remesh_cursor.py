"""Transient remesh percentage beside the pointer in 3D viewports."""
import bpy
import blf

_positions = {}


def update_remesh_cursor(context, event):
    if context.window is None or not hasattr(event, "mouse_x"):
        return
    _positions[context.window.as_pointer()] = (event.mouse_x, event.mouse_y)
    for area in context.window.screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


class RemeshCursor:
    def __init__(self, context, label="Remesh"):
        self.percent = 0.0
        self.label = label
        self.secondary_percent = None
        self.secondary_label = "Remesh"
        self.status_line = None
        self.window = context.window
        self.handle = None
        if not bpy.app.background and self.window is not None:
            self.handle = bpy.types.SpaceView3D.draw_handler_add(self.draw, (), "WINDOW", "POST_PIXEL")

    def draw(self):
        context = bpy.context
        if context.window != self.window or context.region is None:
            return
        position = _positions.get(self.window.as_pointer())
        if position is None:
            return
        region = context.region
        x, y = position[0] - region.x, position[1] - region.y
        if not (0 <= x < region.width and 0 <= y < region.height):
            return
        scale = context.preferences.system.ui_scale
        blf.size(0, 14 * scale)
        primary = f"{self.label} {self.percent:.0f}%"
        if self.secondary_percent is not None:
            primary += f" / {self.secondary_label} {self.secondary_percent:.0f}%"
        lines = [primary]
        if self.status_line:
            lines.append(self.status_line)
        width = max(blf.dimensions(0, line)[0] for line in lines)
        line_height = blf.dimensions(0, primary)[1]
        line_spacing = 18 * scale
        x = max(4, min(x + 20 * scale, region.width - width - 4))
        y = max(4 + (len(lines) - 1) * line_spacing,
                min(y - 24 * scale, region.height - line_height - 4))
        for index, line in enumerate(lines):
            line_y = y - index * line_spacing
            blf.color(0, 0, 0, 0, 1)
            blf.position(0, x + 1, line_y - 1, 0)
            blf.draw(0, line)
            blf.color(0, 1, 1, 1, 1)
            blf.position(0, x, line_y, 0)
            blf.draw(0, line)

    def close(self):
        if self.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, "WINDOW")
            self.handle = None
            for area in self.window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
