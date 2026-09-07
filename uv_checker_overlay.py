"""Transparent UV checker drawn over Solid viewport shading."""

from array import array
import time

import bpy
import gpu
from gpu_extras.batch import batch_for_shader


_DRAW_HANDLE = None
_SHADER = None
_BATCH_CACHE = None
_CACHE_ID_POINTERS = set()
_UV_BUFFER = array("f")
_EDIT_CACHE_CHECK_AT = 0.0
_EDIT_CACHE_INTERVAL = 0.5


VERTEX_SHADER = """
void main()
{
    checker_uv = uv;
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
}
"""


FRAGMENT_SHADER = """
void main()
{
    vec2 cell = floor(checker_uv * scale);
    float tile = mod(cell.x + cell.y, 2.0);
    vec3 dark_color = vec3(0.055, 0.075, 0.105);
    vec3 light_color = vec3(0.78, 0.82, 0.88);
    fragColor = vec4(mix(dark_color, light_color, tile), opacity);
}
"""


def checker_geometry(obj):
    """Return world positions and active-UV coordinates for mesh triangles."""
    if obj is None or obj.type != "MESH":
        return [], []
    mesh = obj.data
    matrix = obj.matrix_world
    if obj.mode == "EDIT":
        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            return [], []
        positions = []
        uvs = []
        for triangle in bm.calc_loop_triangles():
            for loop in triangle:
                positions.append(matrix @ loop.vert.co)
                uvs.append(loop[uv_layer].uv.copy())
        return positions, uvs

    uv_layer = mesh.uv_layers.active
    if uv_layer is None:
        return [], []
    mesh.calc_loop_triangles()
    positions = []
    uvs = []
    for triangle in mesh.loop_triangles:
        for loop_index in triangle.loops:
            loop = mesh.loops[loop_index]
            positions.append(matrix @ mesh.vertices[loop.vertex_index].co)
            uvs.append(uv_layer.data[loop_index].uv.copy())
    return positions, uvs


def _uv_signature(uv_layer):
    """Fast content signature used to notice UV-only edits."""
    global _UV_BUFFER
    size = len(uv_layer.data) * 2
    if len(_UV_BUFFER) != size:
        _UV_BUFFER = array("f", [0.0]) * size
    if size:
        uv_layer.data.foreach_get("uv", _UV_BUFFER)
    return hash(_UV_BUFFER.tobytes())


def _edit_uv_signature(obj):
    """Read live Edit Mode UVs without copying the BMesh back to Mesh."""
    import bmesh

    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        return 0
    values = array("f")
    for face in bm.faces:
        for loop in face.loops:
            uv = loop[uv_layer].uv
            values.extend((uv.x, uv.y))
    return hash(values.tobytes())


def _cache_key(obj):
    mesh = obj.data
    uv_layer = mesh.uv_layers.active
    return (
        obj.as_pointer(), mesh.as_pointer(), obj.mode, uv_layer.name if uv_layer else "",
        len(mesh.vertices), len(mesh.loops), len(mesh.polygons),
        tuple(value for row in obj.matrix_world for value in row),
        _edit_uv_signature(obj) if uv_layer and obj.mode == "EDIT" else 0,
    )


def _checker_batch(obj):
    global _BATCH_CACHE, _CACHE_ID_POINTERS, _EDIT_CACHE_CHECK_AT
    if (
        obj.mode == "EDIT"
        and _BATCH_CACHE is not None
        and _BATCH_CACHE[0][0] == obj.as_pointer()
        and time.monotonic() < _EDIT_CACHE_CHECK_AT
    ):
        return _BATCH_CACHE[1]
    key = _cache_key(obj)
    if _BATCH_CACHE is not None and _BATCH_CACHE[0] == key:
        return _BATCH_CACHE[1]
    positions, uvs = checker_geometry(obj)
    batch = batch_for_shader(_shader(), "TRIS", {"pos": positions, "uv": uvs}) if positions else None
    _BATCH_CACHE = (key, batch)
    _CACHE_ID_POINTERS = {obj.as_pointer(), obj.data.as_pointer()}
    _EDIT_CACHE_CHECK_AT = time.monotonic() + _EDIT_CACHE_INTERVAL
    return batch


def _shader():
    global _SHADER
    if _SHADER is None:
        interface = gpu.types.GPUStageInterfaceInfo("polygroups_checker_interface")
        interface.smooth("VEC2", "checker_uv")
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, "VEC3", "pos")
        info.vertex_in(1, "VEC2", "uv")
        info.vertex_out(interface)
        info.push_constant("MAT4", "ModelViewProjectionMatrix")
        info.push_constant("FLOAT", "scale")
        info.push_constant("FLOAT", "opacity")
        info.fragment_out(0, "VEC4", "fragColor")
        info.vertex_source(VERTEX_SHADER)
        info.fragment_source(FRAGMENT_SHADER)
        _SHADER = gpu.shader.create_from_info(info)
    return _SHADER


def clear_cache(*_args):
    global _BATCH_CACHE, _CACHE_ID_POINTERS, _EDIT_CACHE_CHECK_AT
    _BATCH_CACHE = None
    _CACHE_ID_POINTERS = set()
    _EDIT_CACHE_CHECK_AT = 0.0


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


def exceeds_polygon_limit(obj, polygon_limit):
    return bool(
        polygon_limit > 0
        and obj is not None
        and obj.type == "MESH"
        and len(obj.data.polygons) > polygon_limit
    )


def draw_checker_overlay():
    context = bpy.context
    space = context.space_data
    if space is None or space.type != "VIEW_3D" or space.shading.type != "SOLID":
        return
    scene = context.scene
    if scene is None:
        return
    settings = scene.polygroups_seam_finalization_settings
    if not settings.show_checker_solid_mode or settings.checker_overlay_opacity <= 0.0:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or obj.mode not in {"OBJECT", "EDIT"}:
        return
    if exceeds_polygon_limit(obj, settings.checker_overlay_max_polygons):
        return
    batch = _checker_batch(obj)
    if batch is None:
        return

    shader = _shader()
    old_blend = gpu.state.blend_get()
    old_depth_test = gpu.state.depth_test_get()
    old_depth_mask = gpu.state.depth_mask_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("LESS_EQUAL")
        gpu.state.depth_mask_set(False)
        shader.bind()
        shader.uniform_float("ModelViewProjectionMatrix", gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix())
        shader.uniform_float("scale", scene.polygroups_generator_settings.checker_scale)
        shader.uniform_float("opacity", settings.checker_overlay_opacity)
        batch.draw(shader)
    finally:
        gpu.state.depth_mask_set(old_depth_mask)
        gpu.state.depth_test_set(old_depth_test)
        gpu.state.blend_set(old_blend)


def register():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is None:
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            draw_checker_overlay, (), "WINDOW", "POST_VIEW"
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
