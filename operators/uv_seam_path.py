"""UV Tweak-style island selection and low-turn seam paths."""
import bmesh
import bpy
from mathutils import Matrix, Vector
from ..core.edge_seam_path import find_edge_path

TOOL_ID = "polygroups_generator.uv_seam_path_tool"
_ANCHORS = {}
_ACTIVE_KEYS = set()

def _key(context):
    return context.window.as_pointer(), context.area.as_pointer()

def _mouse_uv(context, event):
    return Vector(context.region.view2d.region_to_view(
        event.mouse_x - context.region.x, event.mouse_y - context.region.y))

def _activate_tool_state(context, reset_anchor=False):
    key = _key(context)
    settings = context.scene.tool_settings
    settings.use_uv_select_sync = False
    settings.uv_select_mode = "VERTEX"
    context.scene.polygroups_seam_preparation_settings.show_seams_uv_editor = True
    if reset_anchor:
        _ANCHORS.pop(key, None)
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.reveal(select=True)
    except RuntimeError:
        pass
    _ACTIVE_KEYS.add(key)
    context.area.tag_redraw()

def _uv_continuous(edge, uv_layer):
    if len(edge.link_faces) != 2:
        return False
    first, second = edge.link_faces
    for vert in edge.verts:
        a = next(loop for loop in first.loops if loop.vert == vert)
        b = next(loop for loop in second.loops if loop.vert == vert)
        if (a[uv_layer].uv - b[uv_layer].uv).length_squared > 1.0e-12:
            return False
    return True

def _uv_island(seed, uv_layer):
    result, stack = {seed}, [seed]
    while stack:
        face = stack.pop()
        for edge in face.edges:
            if edge.hide or edge.seam or not _uv_continuous(edge, uv_layer):
                continue
            for neighbor in edge.link_faces:
                if not neighbor.hide and neighbor not in result:
                    result.add(neighbor)
                    stack.append(neighbor)
    return result

def _pick_loop(context, event):
    bm = bmesh.from_edit_mesh(context.active_object.data)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        return None
    x, y = event.mouse_x - context.region.x, event.mouse_y - context.region.y
    limit = float("inf")
    result = None
    sync = context.scene.tool_settings.use_uv_select_sync
    for face in bm.faces:
        if face.hide or (not sync and not face.select):
            continue
        for loop in face.loops:
            point = context.region.view2d.view_to_region(*loop[uv_layer].uv, clip=False)
            distance = (point[0] - x) ** 2 + (point[1] - y) ** 2
            if distance <= limit:
                limit = distance
                result = face.index, loop.vert.index, loop[uv_layer].uv.copy()
    return result

def _route_data(faces, uv_layer, anchor_index, anchor_uv):
    allowed, coordinates = set(), {}
    for face in faces:
        for loop in face.loops:
            coordinates.setdefault(loop.vert, []).append(loop[uv_layer].uv.copy())
        for edge in face.edges:
            linked = sum(linked_face in faces for linked_face in edge.link_faces)
            if linked == 1 or (linked == 2 and _uv_continuous(edge, uv_layer)):
                allowed.add(edge)
    positions = {vert: Vector((sum(p.x for p in points) / len(points),
                               sum(p.y for p in points) / len(points), 0.0))
                 for vert, points in coordinates.items()}
    for vert in coordinates:
        if vert.index == anchor_index:
            positions[vert] = Vector((anchor_uv.x, anchor_uv.y, 0.0))
            break
    return allowed, positions

def _select_uv_edges(context, path, faces, uv_layer):
    points, face_set = [], set(faces)
    for edge in path:
        loop = next((loop for face in edge.link_faces if face in face_set
                     for loop in face.loops if loop.edge == edge), None)
        if loop is not None:
            points.append((loop[uv_layer].uv + loop.link_loop_next[uv_layer].uv) * 0.5)
    context.scene.tool_settings.uv_select_mode = "EDGE"
    bpy.ops.uv.select_all(action="DESELECT")
    for point in points:
        bpy.ops.uv.select(location=point, extend=True)

def _select_uv_faces(context, faces, uv_layer):
    points = [sum((loop[uv_layer].uv for loop in face.loops), Vector((0.0, 0.0))) / len(face.loops)
              for face in faces]
    settings = context.scene.tool_settings
    settings.uv_select_mode = "FACE"
    bpy.ops.uv.select_all(action="DESELECT")
    for point in points:
        bpy.ops.uv.select(location=point, extend=True)
    settings.uv_select_mode = "VERTEX"

def _endpoint_uv(bm, uv_layer, vertex_index, target):
    bm.verts.ensure_lookup_table()
    points = [loop[uv_layer].uv.copy() for loop in bm.verts[vertex_index].link_loops]
    return min(points, key=lambda point: (point - target).length_squared) if points else target.copy()

class IMAGE_OT_polygroups_uv_island_select(bpy.types.Operator):
    bl_idname = "image.polygroups_uv_island_select"
    bl_label = "Select UV Island"
    bl_options = {"UNDO"}
    def invoke(self, context, event):
        _ANCHORS.pop(_key(context), None)
        picked = _pick_loop(context, event)
        if picked is None:
            return {"CANCELLED"}
        bm = bmesh.from_edit_mesh(context.active_object.data)
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        faces = _uv_island(bm.faces[picked[0]], uv_layer)
        _select_uv_faces(context, faces, uv_layer)
        context.area.tag_redraw()
        return {"FINISHED"}

class IMAGE_OT_polygroups_uv_vertex_select(bpy.types.Operator):
    bl_idname = "image.polygroups_uv_vertex_select"
    bl_label = "Select UV Vertex"
    bl_options = {"UNDO"}
    def invoke(self, context, event):
        picked = _pick_loop(context, event)
        if picked is None:
            _ANCHORS.pop(_key(context), None)
            return bpy.ops.uv.select(
                deselect_all=True, location=_mouse_uv(context, event))
        _face_index, vertex_index, uv = picked
        context.scene.tool_settings.uv_select_mode = "VERTEX"
        bpy.ops.uv.select_all(action="DESELECT")
        result = bpy.ops.uv.select(location=uv, deselect_all=True)
        _ANCHORS[_key(context)] = {
            "object": context.active_object.name,
            "vertex": vertex_index,
            "uv": uv.copy(),
        }
        context.area.tag_redraw()
        return result

class IMAGE_OT_polygroups_uv_seam_path_exit(bpy.types.Operator):
    bl_idname = "image.polygroups_uv_seam_path_exit"
    bl_label = "Exit UV Seam Path"
    def execute(self, context):
        key = _key(context)
        _ANCHORS.pop(key, None)
        _ACTIVE_KEYS.discard(key)
        return bpy.ops.wm.tool_set_by_id(name="builtin.select_box", space_type="IMAGE_EDITOR")

class IMAGE_OT_polygroups_uv_seam_tool_state(bpy.types.Operator):
    bl_idname = "image.polygroups_uv_seam_tool_state"
    bl_label = "UV Seam Path State"
    bl_options = {"INTERNAL"}
    def invoke(self, context, event):
        settings = context.scene.tool_settings
        seam_settings = context.scene.polygroups_seam_preparation_settings
        key = _key(context)
        if key not in _ACTIVE_KEYS:
            _activate_tool_state(context, reset_anchor=True)
            return {"PASS_THROUGH"}
        if settings.use_uv_select_sync:
            settings.use_uv_select_sync = False
        if settings.uv_select_mode != "VERTEX":
            settings.uv_select_mode = "VERTEX"
            context.area.tag_redraw()
        if not seam_settings.show_seams_uv_editor:
            seam_settings.show_seams_uv_editor = True
        return {"PASS_THROUGH"}

class IMAGE_OT_polygroups_uv_seam_path_click(bpy.types.Operator):
    bl_idname = "image.polygroups_uv_seam_path_click"
    bl_label = "UV Seam Path"
    bl_options = {"UNDO"}
    def invoke(self, context, event):
        picked = _pick_loop(context, event)
        if picked is None:
            return {"CANCELLED"}
        face_index, end_index, end_uv = picked
        key, anchor = _key(context), _ANCHORS.get(_key(context))
        context.scene.tool_settings.uv_select_mode = "VERTEX"
        if anchor is None or anchor["object"] != context.active_object.name:
            bpy.ops.uv.select_all(action="DESELECT")
            bpy.ops.uv.select(location=end_uv, deselect_all=True)
            _ANCHORS[key] = {"object": context.active_object.name,
                             "vertex": end_index, "uv": end_uv.copy()}
            return {"FINISHED"}
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None or face_index >= len(bm.faces) or anchor["vertex"] >= len(bm.verts):
            _ANCHORS.pop(key, None)
            return {"CANCELLED"}
        faces = _uv_island(bm.faces[face_index], uv_layer)
        allowed, positions = _route_data(faces, uv_layer, anchor["vertex"], anchor["uv"])
        positions[bm.verts[end_index]] = Vector((end_uv.x, end_uv.y, 0.0))
        path = find_edge_path(bm, bm.verts[anchor["vertex"]], bm.verts[end_index],
                              Matrix.Identity(4), allowed_edges=allowed,
                              vertex_positions=positions)
        if not path:
            self.report({"WARNING"}, "No UV edge path connects these vertices")
            return {"CANCELLED"}
        bm.edges.index_update()
        indices = tuple(edge.index for edge in path)
        _select_uv_edges(context, path, faces, uv_layer)
        bm = bmesh.from_edit_mesh(obj.data); bm.edges.ensure_lookup_table()
        for index in indices:
            if index < len(bm.edges): bm.edges[index].seam = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        if context.scene.polygroups_seam_preparation_settings.uv_seam_path_auto_rip:
            try:
                bpy.ops.uv.rip_move("EXEC_DEFAULT", UV_OT_rip={"location": end_uv},
                    TRANSFORM_OT_translate={"value": (0.001, 0.0, 0.0)})
            except RuntimeError as error:
                self.report({"WARNING"}, f"UV Rip failed: {error}")
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.active
        end_uv = _endpoint_uv(bm, uv_layer, end_index, end_uv + Vector((0.001, 0.0)))
        context.scene.tool_settings.uv_select_mode = "VERTEX"
        bpy.ops.uv.select_all(action="DESELECT")
        bpy.ops.uv.select(location=end_uv, deselect_all=True)
        _ANCHORS[key] = {"object": obj.name, "vertex": end_index, "uv": end_uv.copy()}
        context.area.tag_redraw()
        return {"FINISHED"}

class WM_OT_polygroups_activate_uv_seam_path(bpy.types.Operator):
    bl_idname = "wm.polygroups_activate_uv_seam_path"
    bl_label = "Activate UV Seam Path"
    def execute(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type != "IMAGE_EDITOR" or area.ui_type != "UV": continue
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region is None: continue
                with context.temp_override(window=window, area=area, region=region):
                    _activate_tool_state(context, reset_anchor=True)
                    bpy.ops.wm.tool_set_by_id(name=TOOL_ID, space_type="IMAGE_EDITOR")
                area.tag_redraw(); return {"FINISHED"}
        self.report({"WARNING"}, "Open a UV Editor and enter Mesh Edit Mode")
        return {"CANCELLED"}

def draw_uv_seam_path_cursor(context, _tool, xy):
    if context.area is None or context.area.type != "IMAGE_EDITOR": return
    from .edge_seam_path import draw_colored_crosshair, draw_tool_badge
    draw_colored_crosshair(context, xy, (1.0, 0.55, 0.08, 1.0))
    draw_tool_badge(context, "UV Seam Path", xy,
                    "Shift + Click: Select island | Ctrl + Click: Draw seam")

def clear_uv_seam_path_sessions():
    _ANCHORS.clear()
    _ACTIVE_KEYS.clear()
