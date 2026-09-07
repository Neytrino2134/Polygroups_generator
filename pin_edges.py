"""Persistent pinned seam edges and their Edit Mode viewport overlay."""
import bpy
import bmesh

PIN_LAYER = "polygroups_pin_edge"
PIN_COLOR = (1.0, 0.18, 0.75, 1.0)
_draw_handle = None


def pin_layer(bm, create=False):
    layer = bm.edges.layers.int.get(PIN_LAYER)
    return layer or (bm.edges.layers.int.new(PIN_LAYER) if create else None)


def is_pinned(edge, layer):
    return bool(layer is not None and edge[layer])


def set_pinned(edges, layer, value=True):
    for edge in edges:
        edge[layer] = int(value)


def draw_pinned_edges():
    context = bpy.context
    if (context.mode != "EDIT_MESH" or context.area is None or context.area.type != "VIEW_3D"
            or context.region is None or context.region_data is None
            or context.space_data is None
            or not context.space_data.overlay.show_overlays):
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    viewport = gpu.state.viewport_get()[2:]
    scale = context.preferences.system.ui_scale
    coords = []
    for obj in context.objects_in_mode_unique_data:
        if obj.type != "MESH":
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        layer = pin_layer(bm)
        if layer is None:
            continue
        matrix = obj.matrix_world
        for edge in bm.edges:
            if edge.hide or not is_pinned(edge, layer):
                continue
            coords.extend((matrix @ edge.verts[0].co, matrix @ edge.verts[1].co))
    if not coords:
        return
    blend = gpu.state.blend_get()
    depth_test = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        # Match Blender's edit-mesh overlay: hidden by the surface normally,
        # but visible through it when the viewport X-Ray switch is enabled.
        gpu.state.depth_test_set(
            "NONE" if context.space_data.shading.show_xray else "LESS_EQUAL"
        )
        shader.bind()
        shader.uniform_float("viewportSize", viewport)
        shader.uniform_float("lineWidth", max(2.0, 2.5 * scale))
        shader.uniform_float("color", PIN_COLOR)
        batch_for_shader(shader, "LINES", {"pos": coords}).draw(shader)
    finally:
        gpu.state.depth_test_set(depth_test)
        gpu.state.blend_set(blend)


def register():
    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(draw_pinned_edges, (), "WINDOW", "POST_VIEW")


def unregister():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
        _draw_handle = None
