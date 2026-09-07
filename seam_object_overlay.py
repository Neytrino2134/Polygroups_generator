"""Viewport overlay that makes mesh seams visible in Object Mode."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader


_DRAW_HANDLE = None
_SHADER = None
_BATCH_CACHE = None
_CACHE_ID_POINTERS = set()


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


def exceeds_polygon_limit(obj, polygon_limit):
    return bool(
        polygon_limit > 0
        and obj is not None
        and obj.type == "MESH"
        and len(obj.data.polygons) > polygon_limit
    )


def _cache_key(obj):
    mesh = obj.data
    return (
        obj.as_pointer(),
        mesh.as_pointer(),
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.polygons),
        tuple(value for row in obj.matrix_world for value in row),
    )


def _shader():
    global _SHADER
    if _SHADER is None:
        _SHADER = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    return _SHADER


def _seam_batch(obj):
    global _BATCH_CACHE, _CACHE_ID_POINTERS
    key = _cache_key(obj)
    if _BATCH_CACHE is not None and _BATCH_CACHE[0] == key:
        return _BATCH_CACHE[1]
    points = seam_line_points(obj)
    shader = _shader()
    batch = batch_for_shader(shader, "LINES", {"pos": points}) if points else None
    _BATCH_CACHE = (key, batch)
    _CACHE_ID_POINTERS = {obj.as_pointer(), obj.data.as_pointer()}
    return batch


def clear_cache(*_args):
    global _BATCH_CACHE, _CACHE_ID_POINTERS
    _BATCH_CACHE = None
    _CACHE_ID_POINTERS = set()


def invalidate_geometry(_scene, depsgraph):
    if not _CACHE_ID_POINTERS:
        return
    for update in depsgraph.updates:
        if not (update.is_updated_geometry or update.is_updated_transform):
            continue
        try:
            pointer = update.id.original.as_pointer()
        except (AttributeError, ReferenceError):
            try:
                pointer = update.id.as_pointer()
            except (AttributeError, ReferenceError):
                continue
        if pointer in _CACHE_ID_POINTERS:
            clear_cache()
            return


def draw_seams_object_mode():
    context = bpy.context
    if (context.mode != "OBJECT" or context.scene is None
            or context.space_data is None
            or context.space_data.type != "VIEW_3D"
            or not context.space_data.overlay.show_overlays):
        return
    settings = getattr(context.scene, "polygroups_seam_preparation_settings", None)
    if settings is None or not settings.show_seams_object_mode:
        return

    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return
    if exceeds_polygon_limit(obj, settings.seam_overlay_max_polygons):
        return
    batch = _seam_batch(obj)
    if batch is None:
        return
    shader = _shader()
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
    if invalidate_geometry not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(invalidate_geometry)


def unregister():
    global _DRAW_HANDLE, _SHADER
    if invalidate_geometry in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(invalidate_geometry)
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
        _DRAW_HANDLE = None
    clear_cache()
    _SHADER = None
