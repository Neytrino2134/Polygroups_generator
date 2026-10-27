"""Relax the active UV map after topology changes without moving island borders."""
import bmesh
import bpy


def _selection(loop, uv):
    if hasattr(loop, 'uv_select_vert'):
        return loop.uv_select_vert, loop.uv_select_edge
    return loop[uv].select, loop[uv].select_edge


def _set_selection(loop, uv, vertex, edge):
    if hasattr(loop, 'uv_select_vert'):
        loop.uv_select_vert, loop.uv_select_edge = vertex, edge
    else:
        loop[uv].select, loop[uv].select_edge = vertex, edge


def boundary_loops(bm, uv, epsilon=1e-7):
    """Find marked seams, open edges and unmarked UV discontinuities by corner."""
    result, boundaries = set(), set()
    for edge in bm.edges:
        sides = list(edge.link_loops)
        boundary = edge.seam or len(sides) != 2
        if not boundary:
            first = {loop.vert: loop[uv].uv for loop in (sides[0], sides[0].link_loop_next)}
            second = {loop.vert: loop[uv].uv for loop in (sides[1], sides[1].link_loop_next)}
            boundary = any((first[vertex] - second[vertex]).length > epsilon for vertex in edge.verts)
        if boundary:
            boundaries.add(edge)
            for side in sides:
                result.update((side, side.link_loop_next))
    return result, boundaries


def relax_uv_boundaries(context, obj):
    """Temporarily pin borders and unwrap; keep original pins/seams and selection.

    Operates on applied topology only. No UV map is created, packed or rescaled.
    Returns the number of pinned boundary corners; UV-less meshes are a no-op.
    """
    if not obj.data.uv_layers or not obj.data.polygons:
        return 0
    if obj.mode != 'OBJECT' or context.active_object != obj:
        raise ValueError('UV boundary relaxation requires the active mesh in Object Mode')
    selected, active = tuple(context.selected_objects), context.view_layer.objects.active
    select_mode = tuple(context.tool_settings.mesh_select_mode)
    uv_sync = context.tool_settings.use_uv_select_sync
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    uv = bm.loops.layers.uv.active
    corners = [(loop, loop[uv].uv.copy(), loop[uv].pin_uv, *_selection(loop, uv))
               for face in bm.faces for loop in face.loops]
    elements = [(element, element.select, element.hide) for domain in (bm.verts, bm.edges, bm.faces) for element in domain]
    seams = [(edge, edge.seam) for edge in bm.edges]
    history = list(bm.select_history)
    face_active = bm.faces.active
    pinned, boundaries = boundary_loops(bm, uv)
    success = False
    try:
        if not pinned:
            return 0
        for element, _, _ in elements:
            element.hide = False
            element.select = True
        for loop, _, _, _, _ in corners:
            _set_selection(loop, uv, True, True)
        for loop in pinned:
            loop[uv].pin_uv = True
        # UV splits need seams during unwrap even if the user never marked them.
        for edge in boundaries:
            edge.seam = True
        context.tool_settings.mesh_select_mode = (False, False, True)
        context.tool_settings.use_uv_select_sync = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        result = bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=False, correct_aspect=False, margin=0.0)
        if 'FINISHED' not in result:
            raise RuntimeError('Pinned-border UV unwrap did not finish')
        # Preserve exact coordinates even if the native solver rounds pinned UVs.
        for loop, coordinate, pinned_before, _, _ in corners:
            if loop in pinned or pinned_before:
                loop[uv].uv = coordinate
        success = True
        return len(pinned)
    finally:
        for loop, coordinate, pinned_before, selected_before, edge_selected in corners:
            if not success:
                loop[uv].uv = coordinate
            loop[uv].pin_uv = pinned_before
            _set_selection(loop, uv, selected_before, edge_selected)
        for edge, seam in seams:
            edge.seam = seam
        for element, selected_before, hidden in elements:
            element.hide = hidden
            element.select = selected_before
        bm.select_history.clear()
        for element in history:
            bm.select_history.add(element)
        bm.faces.active = face_active
        context.tool_settings.mesh_select_mode = select_mode
        context.tool_settings.use_uv_select_sync = uv_sync
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        for original in selected:
            original.select_set(True)
        context.view_layer.objects.active = active
