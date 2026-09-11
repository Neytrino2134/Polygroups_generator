"""Display mesh seams on their actual UV loop coordinates."""
import bmesh
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .localization import t

_HANDLE = None
_SNAPSHOTS = {}


def _modal_active(window):
    return bool(window.modal_operators)


def refresh_snapshots():
    """Read edit data only between modal operations, never from a draw callback."""
    snapshots = {}
    wm = bpy.context.window_manager
    if wm is None:
        return 0.15
    # Transform/undo may rebuild edit data. Keep all BMesh access out of that
    # interval, including when the modal operation belongs to another window.
    if any(_modal_active(window) for window in wm.windows):
        _SNAPSHOTS.clear()
        return 0.15
    for window in wm.windows:
        settings = getattr(window.scene, "polygroups_seam_preparation_settings", None)
        if settings is None or not settings.show_seams_uv_editor:
            continue
        area = next((a for a in window.screen.areas
                     if a.type == "IMAGE_EDITOR" and a.spaces.active.mode == "UV"), None)
        if area is None:
            continue
        with bpy.context.temp_override(window=window, area=area):
            context = bpy.context
            if context.mode != "EDIT_MESH":
                continue
            segments = []
            for obj in context.objects_in_mode_unique_data:
                if obj.type != "MESH" or not obj.data.is_editmode:
                    continue
                bm = bmesh.from_edit_mesh(obj.data)
                uv_layer = bm.loops.layers.uv.active
                if uv_layer is not None:
                    segments.extend(seam_uv_segments(
                        bm, uv_layer, context.scene.tool_settings.use_uv_select_sync,
                    ))
            # Store only copied float tuples, never edit-mesh elements or layers.
            snapshots[window.as_pointer()] = tuple(segments)
    changed = snapshots != _SNAPSHOTS
    _SNAPSHOTS.clear()
    _SNAPSHOTS.update(snapshots)
    if changed:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == "IMAGE_EDITOR":
                    area.tag_redraw()
    return 0.15


@bpy.app.handlers.persistent
def clear_snapshots(*_args):
    _SNAPSHOTS.clear()


def seam_uv_segments(bm, uv_layer, sync):
    """Include each visible UV side of a seam, including separated islands."""
    segments = []
    seen = set()
    for face in bm.faces:
        if face.hide or (not sync and not face.select):
            continue
        for loop in face.loops:
            if not loop.edge.seam or loop.edge.hide:
                continue
            first = tuple(loop[uv_layer].uv)
            second = tuple(loop.link_loop_next[uv_layer].uv)
            key = tuple(sorted((first, second)))
            if key not in seen:
                seen.add(key)
                segments.append((first, second))
    return segments


def draw_uv_seams():
    context = bpy.context
    space = context.space_data
    if (space is None or space.type != "IMAGE_EDITOR" or space.mode != "UV"
            or context.mode != "EDIT_MESH"):
        return
    settings = context.scene.polygroups_seam_preparation_settings
    if not settings.show_seams_uv_editor:
        return
    if any(_modal_active(window) for window in context.window_manager.windows):
        return
    if hasattr(space, "overlay") and not space.overlay.show_overlays:
        return
    points = []
    for first, second in _SNAPSHOTS.get(context.window.as_pointer(), ()):
        a = context.region.view2d.view_to_region(*first, clip=False)
        b = context.region.view2d.view_to_region(*second, clip=False)
        if -2147483648 not in (*a, *b):
            points.extend((a, b))
    if not points:
        return
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": points})
    blend = gpu.state.blend_get()
    depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", 2.5 * context.preferences.system.ui_scale)
        shader.uniform_float("color", (1.0, 0.12, 0.03, 1.0))
        batch.draw(shader)
    finally:
        gpu.state.blend_set(blend)
        gpu.state.depth_test_set(depth)


class IMAGE_PT_polygroups_uv_seams(bpy.types.Panel):
    bl_label = "UV Seam Tools"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "AI Retopo"

    @classmethod
    def poll(cls, context):
        return context.space_data.mode == "UV"

    def draw(self, context):
        self.layout.prop(
            context.scene.polygroups_seam_preparation_settings,
            "show_seams_uv_editor", text=t(context, "show_seams_uv_editor"),
            toggle=True, icon="EDGE_SEAM",
        )
        self.layout.prop(
            context.scene.polygroups_seam_preparation_settings,
            "uv_seam_path_auto_rip", text=t(context, "uv_seam_path_auto_rip"),
            toggle=True, icon="UV",
        )


def register():
    global _HANDLE
    bpy.utils.register_class(IMAGE_PT_polygroups_uv_seams)
    if not bpy.app.timers.is_registered(refresh_snapshots):
        bpy.app.timers.register(refresh_snapshots, first_interval=0.15, persistent=True)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre,
                     bpy.app.handlers.redo_pre):
        if clear_snapshots not in handlers:
            handlers.append(clear_snapshots)
    if _HANDLE is None:
        _HANDLE = bpy.types.SpaceImageEditor.draw_handler_add(
            draw_uv_seams, (), "WINDOW", "POST_PIXEL",
        )


def unregister():
    global _HANDLE
    if bpy.app.timers.is_registered(refresh_snapshots):
        bpy.app.timers.unregister(refresh_snapshots)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre,
                     bpy.app.handlers.redo_pre):
        if clear_snapshots in handlers:
            handlers.remove(clear_snapshots)
    clear_snapshots()
    if _HANDLE is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_HANDLE, "WINDOW")
        _HANDLE = None
    bpy.utils.unregister_class(IMAGE_PT_polygroups_uv_seams)
