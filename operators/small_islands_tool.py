"""Gesture tool for merging small seam islands inside a painted screen area."""

import bmesh
import bpy


TOOL_ID = "polygroups_generator.small_islands_merger_tool"
SELECTOR_TOOL_ID = "polygroups_generator.island_selector_tool"


def _linked_seam_islands(seed_faces):
    linked = set(seed_faces)
    stack = list(seed_faces)
    while stack:
        face = stack.pop()
        for edge in face.edges:
            if edge.seam or edge.hide:
                continue
            for neighbor in edge.link_faces:
                if neighbor not in linked and not neighbor.hide:
                    linked.add(neighbor)
                    stack.append(neighbor)
    return linked


def _edge_uv_continuous(edge, uv_layer):
    if len(edge.link_faces) != 2:
        return False
    if uv_layer is None:
        return not edge.seam
    first, second = edge.link_faces
    for vert in edge.verts:
        first_loop = next((loop for loop in first.loops if loop.vert == vert), None)
        second_loop = next((loop for loop in second.loops if loop.vert == vert), None)
        if first_loop is None or second_loop is None:
            return False
        if (first_loop[uv_layer].uv - second_loop[uv_layer].uv).length_squared > 1.0e-10:
            return False
    return True


def _linked_uv_islands(seed_faces, uv_layer):
    linked = set(seed_faces)
    stack = list(seed_faces)
    while stack:
        face = stack.pop()
        for edge in face.edges:
            if edge.hide or edge.seam or not _edge_uv_continuous(edge, uv_layer):
                continue
            for neighbor in edge.link_faces:
                if neighbor not in linked and not neighbor.hide:
                    linked.add(neighbor)
                    stack.append(neighbor)
    return linked


class _IslandGestureMixin:
    """Non-RNA implementation shared by two independently registered operators."""

    settings_property = "small_islands_merger_shape"
    merge_after_selection = True
    use_uv_islands = False
    selection_mode_property = None

    @classmethod
    def poll(cls, context):
        return (context.mode == "EDIT_MESH" and context.active_object is not None
                and context.active_object.type == "MESH" and len(context.objects_in_mode) == 1
                and context.area is not None and context.area.type == "VIEW_3D")

    def invoke(self, context, event):
        self.shape = getattr(context.scene.polygroups_generator_settings, self.settings_property)
        selection_mode = (
            getattr(context.scene.polygroups_generator_settings, self.selection_mode_property)
            if self.selection_mode_property else "NEW"
        )
        if self.selection_mode_property and event.shift:
            selection_mode = "ADD"
        self._native_mode = "ADD" if selection_mode == "ADD" else "SET"
        self._points = [(event.mouse_region_x, event.mouse_region_y)]
        self._area = context.area
        self._select_mode_before = tuple(context.tool_settings.mesh_select_mode)
        bm = bmesh.from_edit_mesh(context.active_object.data)
        self._selection_before = [
            [item.select for item in sequence]
            for sequence in (bm.verts, bm.edges, bm.faces)
        ]
        self._selected_face_indices_before = {
            face.index for face in bm.faces if face.select and not face.hide
        }
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        if self._native_mode == "SET":
            bpy.ops.mesh.select_all(action="DESELECT")
        if self.shape == "TWEAK":
            bpy.ops.view3d.select(
                location=(event.mouse_region_x, event.mouse_region_y),
                deselect_all=self._native_mode == "SET",
            )
            self._handle = None
            return self._finish(context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw, (), "WINDOW", "POST_PIXEL",
        )
        if self.shape == "CIRCLE":
            self._native_circle(self._points[0])
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Drag to select seam islands; release to analyze and merge")
        return {"RUNNING_MODAL"}

    def _native_circle(self, point):
        bpy.ops.view3d.select_circle(
            x=int(point[0]), y=int(point[1]), radius=self.radius,
            wait_for_input=False, mode="ADD",
        )

    def _apply_native_selection(self):
        if self.shape == "BOX":
            x1, y1 = self._points[0]
            x2, y2 = self._points[-1]
            bpy.ops.view3d.select_box(
                xmin=int(min(x1, x2)), xmax=int(max(x1, x2)),
                ymin=int(min(y1, y2)), ymax=int(max(y1, y2)),
                wait_for_input=False, mode=self._native_mode,
            )
        elif len(self._points) >= 3:
            path = [
                {"name": "", "loc": (int(x), int(y)), "time": index / 1000.0}
                for index, (x, y) in enumerate(self._points)
            ]
            bpy.ops.view3d.select_lasso(path=path, mode=self._native_mode)

    def _draw(self):
        if not self._points:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader

        points = self._points
        if self.shape == "BOX" and len(points) > 1:
            a, b = points[0], points[-1]
            points = [a, (b[0], a[1]), b, (a[0], b[1]), a]
        elif self.shape == "LASSO" and len(points) > 1:
            points = points + [points[0]]
        elif self.shape == "CIRCLE":
            from math import cos, sin, tau
            center = points[-1]
            points = [(center[0] + cos(tau * i / 48) * self.radius,
                       center[1] + sin(tau * i / 48) * self.radius) for i in range(49)]
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", 1.5)
        shader.uniform_float("color", (1.0, 0.45, 0.08, 1.0))
        batch_for_shader(shader, "LINE_STRIP", {"pos": points}).draw(shader)

    def _finish(self, context, cancel=False):
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None
        context.workspace.status_text_set(None)
        self._area.tag_redraw()
        if cancel:
            self._restore_selection(context)
            return {"CANCELLED"}
        if self.shape != "CIRCLE":
            self._apply_native_selection()
        bm = bmesh.from_edit_mesh(context.active_object.data)
        seeds = {face for face in bm.faces if face.select and not face.hide}
        if not seeds:
            self.report({"WARNING"}, "No polygons touched")
            self._restore_selection(context)
            return {"CANCELLED"}
        if self.use_uv_islands:
            uv_layer = bm.loops.layers.uv.active
            selected_faces = _linked_uv_islands(seeds, uv_layer)
        else:
            selected_faces = _linked_seam_islands(seeds)
        selected_indices = {face.index for face in selected_faces}
        if self._native_mode == "ADD":
            selected_indices.update(self._selected_face_indices_before)
        bpy.ops.mesh.select_all(action="DESELECT")
        bm = bmesh.from_edit_mesh(context.active_object.data)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            face.select_set(face.index in selected_indices)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(context.active_object.data, loop_triangles=False, destructive=False)
        if self.merge_after_selection:
            settings = context.scene.polygroups_generator_settings
            settings.small_island_selected_area = True
            return bpy.ops.mesh.polygroups_analyze_and_merge_seams("EXEC_DEFAULT")
        return {"FINISHED"}

    def _restore_selection(self, context):
        bpy.ops.mesh.select_all(action="DESELECT")
        bm = bmesh.from_edit_mesh(context.active_object.data)
        for sequence, flags in zip((bm.verts, bm.edges, bm.faces), self._selection_before):
            for item, selected in zip(sequence, flags):
                item.select = selected
        bm.select_flush_mode()
        context.tool_settings.mesh_select_mode = self._select_mode_before
        bmesh.update_edit_mesh(context.active_object.data, loop_triangles=False, destructive=False)

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE", "WINDOW_DEACTIVATE"}:
            result = self._finish(context, cancel=True)
            if event.type == "RIGHTMOUSE" and context.mode == "EDIT_MESH":
                bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
            return result
        if event.type == "MOUSEMOVE":
            point = (event.mouse_region_x, event.mouse_region_y)
            if self.shape == "BOX":
                if len(self._points) == 1:
                    self._points.append(point)
                else:
                    self._points[-1] = point
            else:
                self._points.append(point)
            if self.shape == "CIRCLE":
                self._native_circle(point)
            self._area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            return self._finish(context)
        return {"RUNNING_MODAL"}


class MESH_OT_polygroups_small_islands_merger_gesture(
    _IslandGestureMixin,
    bpy.types.Operator,
):
    bl_idname = "mesh.polygroups_small_islands_merger_gesture"
    bl_label = "Small Islands Merger"
    bl_description = "Select touched seam islands with a gesture and merge their small seams"
    bl_options = {"REGISTER", "UNDO"}

    shape: bpy.props.EnumProperty(
        name="Selection",
        items=(
            ("BOX", "Box", "Select seam islands touched by a box"),
            ("LASSO", "Lasso", "Select seam islands touched by a lasso"),
            ("CIRCLE", "Circle", "Paint over seam islands with a circle"),
        ),
        default="BOX",
    )
    radius: bpy.props.IntProperty(name="Radius", default=30, min=2, max=500, subtype="PIXEL")


class MESH_OT_polygroups_island_selector_gesture(
    _IslandGestureMixin,
    bpy.types.Operator,
):
    bl_idname = "mesh.polygroups_island_selector_gesture"
    bl_label = "Island Selector"
    bl_description = "Select complete UV islands with Tweak, Box, Lasso, or Circle"

    shape: bpy.props.EnumProperty(
        name="Selection",
        items=(
            ("TWEAK", "Tweak", "Click a polygon or vertex to select its UV island"),
            ("BOX", "Box", "Select UV islands touched by a box"),
            ("LASSO", "Lasso", "Select UV islands touched by a lasso"),
            ("CIRCLE", "Circle", "Paint over UV islands with a circle"),
        ),
        default="TWEAK",
    )
    radius: bpy.props.IntProperty(name="Radius", default=30, min=2, max=500, subtype="PIXEL")
    settings_property = "island_selector_shape"
    merge_after_selection = False
    use_uv_islands = True
    selection_mode_property = "island_selector_selection_mode"
