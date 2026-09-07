"""Viewport overlay that makes mesh seams visible in Object Mode."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader


_DRAW_HANDLE = None


def seam_line_points(obj):
    """Return world-space line endpoints for every seam on a mesh object."""
    if obj is None or obj.type != "MESH":
        return []
    matrix = obj.matrix_world
    vertices = obj.data.vertices
    points = []
    for edge in obj.data.edges:
        if edge.use_seam:
            points.extend((matrix @ vertices[index].co for index in edge.vertices))
    return points


def draw_seams_object_mode():
    context = bpy.context
    if context.mode != "OBJECT" or context.scene is None:
        return
    settings = getattr(context.scene, "polygroups_seam_preparation_settings", None)
    if settings is None or not settings.show_seams_object_mode:
        return

    points = seam_line_points(context.active_object)
    if not points:
        return

    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": points})
    old_blend = gpu.state.blend_get()
    old_depth_test = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("LESS_EQUAL")
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", 2.5 * context.preferences.system.ui_scale)
        shader.uniform_float("color", (1.0, 0.12, 0.03, 1.0))
        batch.draw(shader)
    finally:
        gpu.state.depth_test_set(old_depth_test)
        gpu.state.blend_set(old_blend)


def register():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is None:
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            draw_seams_object_mode, (), "WINDOW", "POST_VIEW"
        )


def unregister():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
        _DRAW_HANDLE = None
