"""Non-destructive cyan preview of proposed cuts, including virtual diagonals."""
import bpy

_handles = []


def clear_preview(*args):
    while _handles:
        space, handle = _handles.pop()
        space.draw_handler_remove(handle, 'WINDOW')
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre):
        if clear_preview in handlers:
            handlers.remove(clear_preview)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'VIEW_3D', 'IMAGE_EDITOR'}:
                area.tag_redraw()


def show_preview(obj, bm, cuts):
    clear_preview()
    if bpy.app.background:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    points = []
    uv_points = []
    layer = bm.loops.layers.uv.active
    uv_name = obj.data.uv_layers.active.name if obj.data.uv_layers.active else None
    for index in sorted(cuts):
        edge = bm.edges[index]
        points.extend(vertex.co.copy() for vertex in edge.verts)
        if layer is not None:
            face = edge.link_faces[0]
            uv_points.extend(next(loop[layer].uv.copy() for loop in face.loops if loop.vert == vertex)
                             for vertex in edge.verts)

    def draw(uv_editor=False):
        context = bpy.context
        try:
            if context.active_object != obj or obj.mode != 'EDIT':
                return
            if context.window.modal_operators:
                return
            if hasattr(context.space_data, 'overlay') and not context.space_data.overlay.show_overlays:
                return
            if uv_editor:
                if context.space_data.mode != 'UV':
                    return
                if not uv_points or not obj.data.uv_layers.active or obj.data.uv_layers.active.name != uv_name:
                    return
                coordinates = [(*context.region.view2d.view_to_region(*point, clip=False), 0)
                               for point in uv_points]
            else:
                coordinates = [obj.matrix_world @ point for point in points]
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'LINES', {'pos': coordinates})
            blend = gpu.state.blend_get()
            depth = gpu.state.depth_test_get()
            mask = gpu.state.depth_mask_get()
            try:
                gpu.state.blend_set('ALPHA')
                gpu.state.depth_test_set('NONE' if uv_editor else 'LESS_EQUAL')
                gpu.state.depth_mask_set(False)
                shader.bind()
                shader.uniform_float('viewportSize', gpu.state.viewport_get()[2:])
                shader.uniform_float('lineWidth', 3.0)
                shader.uniform_float('color', (0.05, 0.95, 1.0, 1.0))
                batch.draw(shader)
            finally:
                gpu.state.blend_set(blend)
                gpu.state.depth_test_set(depth)
                gpu.state.depth_mask_set(mask)
        except ReferenceError:
            return

    _handles.append((bpy.types.SpaceView3D, bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_VIEW')))
    _handles.append((bpy.types.SpaceImageEditor, bpy.types.SpaceImageEditor.draw_handler_add(draw, (True,), 'WINDOW', 'POST_PIXEL')))
    bpy.app.handlers.load_pre.append(clear_preview)
    bpy.app.handlers.undo_pre.append(clear_preview)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
