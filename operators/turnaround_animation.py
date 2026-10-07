import os
from math import radians, tau

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from .render_queue import image_extension


TURNAROUND_COLLECTION_PROP = "polygroups_turnaround_collection"
TURNAROUND_SOURCE_PROP = "polygroups_turnaround_source"
TURNAROUND_EMPTY_PROP = "polygroups_turnaround_empty"
TURNAROUND_LABEL_PROP = "polygroups_turnaround_label"
VIEW_LABELS = {0: "Front", 90: "Side 90", 180: "Back 180", 270: "Side 270"}
VIDEO_CONTAINERS = {
    "MKV": (".mkv", "H264"),
    "MPEG4": (".mp4", "H264"),
    "WEBM": (".webm", "WEBM"),
    "QUICKTIME": (".mov", "H264"),
}
_ACTIVE_RENDER_TASK = None


def _create_turnaround_labels(collection, source_name):
    material = bpy.data.materials.new("Turnaround Text")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1, 1, 1, 1)
    material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
    for key, body in [('name', source_name)] + [(str(angle), text) for angle, text in VIEW_LABELS.items()]:
        curve = bpy.data.curves.new(f"Turnaround Label {key}", 'FONT')
        curve.body = body
        curve.align_x = 'CENTER'
        curve.align_y = 'CENTER'
        curve.materials.append(material)
        obj = bpy.data.objects.new(curve.name, curve)
        collection.objects.link(obj)
        obj[TURNAROUND_LABEL_PROP] = key
        obj.hide_render = obj.hide_viewport = key != 'name'


def _show_turnaround_labels(scene, collection, angle=None):
    """Keep captions fixed in the camera frame, independent of asset rotation."""
    camera = scene.camera
    frame = camera.data.view_frame(scene=scene)
    depth = max(camera.data.clip_start * 2, 1.0)
    corners = [v.copy() if camera.data.type == 'ORTHO' else v * (depth / abs(v.z)) for v in frame]
    left, right = min(v.x for v in corners), max(v.x for v in corners)
    bottom, top = min(v.y for v in corners), max(v.y for v in corners)
    for obj in collection.objects:
        key = obj.get(TURNAROUND_LABEL_PROP)
        if key is None:
            continue
        obj.hide_render = obj.hide_viewport = key not in {'name', str(angle)}
        obj.parent = camera
        obj.matrix_parent_inverse.identity()
        obj.rotation_euler = (0, 0, 0)
        obj.scale = (1, 1, 1)
        obj.location = ((left + right) / 2, top - (top - bottom) * .05 if key == 'name' else bottom + (top - bottom) * .05, -depth)
        obj.data.size = (top - bottom) * .035
        bpy.context.view_layer.update()
        if obj.dimensions.x > (right - left) * .9:
            obj.data.size *= (right - left) * .9 / obj.dimensions.x


def _redraw_animation_ui(window_manager):
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _draw_animation_cursor():
    task = _ACTIVE_RENDER_TASK
    if task is None or bpy.context.area != task._area:
        return
    region = bpy.context.region
    if region is None:
        return
    cursor_status = getattr(task, '_cursor_status', 'Render')
    blf.size(0, 12)
    width, height = blf.dimensions(0, cursor_status)
    x = min(max(task._mouse_x + 18, 8), max(8, region.width - width - 8))
    y = min(max(task._mouse_y - 24, 8), max(8, region.height - height - 8))
    factor = min(1.0, max(0.0, task._settings.animation_progress / 100.0))
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    def rectangle(left, bottom, width, height, color):
        batch = batch_for_shader(shader, "TRIS", {"pos": (
            (left, bottom), (left + width, bottom), (left + width, bottom + height),
            (left, bottom), (left + width, bottom + height), (left, bottom + height),
        )})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    gpu.state.blend_set("ALPHA")
    try:
        blf.position(0, x + 1, y - 1, 0)
        blf.color(0, 0.0, 0.0, 0.0, 1.0)
        blf.draw(0, cursor_status)
        blf.position(0, x, y, 0)
        blf.color(0, 1.0, 1.0, 1.0, 1.0)
        blf.draw(0, cursor_status)
        rectangle(16, 16, 360, 62, (0.06, 0.06, 0.07, 0.88))
        rectangle(24, 24, 344, 7, (0.25, 0.25, 0.27, 1.0))
        if factor:
            rectangle(24, 24, 344 * factor, 7, (0.44, 0.30, 0.83, 1.0))
        blf.position(0, 24, 42, 0)
        blf.draw(0, f"Completed {task._frames_done}/{task._total_frames}  {factor * 100:.0f}%")
        blf.position(0, 24, 60, 0)
        blf.draw(0, task._settings.animation_status)
    finally:
        gpu.state.blend_set("NONE")


def _object_world_center(obj):
    if getattr(obj, "bound_box", None):
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return sum(corners, Vector()) / len(corners)
    return obj.matrix_world.translation.copy()


def _action_fcurves(action):
    legacy_curves = getattr(action, "fcurves", None)
    if legacy_curves is not None:
        return list(legacy_curves)
    curves = []
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channelbag in getattr(strip, "channelbags", ()):
                curves.extend(channelbag.fcurves)
    return curves


def _set_linear_interpolation(obj):
    action = getattr(getattr(obj, "animation_data", None), "action", None)
    for curve in _action_fcurves(action):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"


def _scene_collections(root):
    result = []

    def visit(collection):
        result.append(collection)
        for child in collection.children:
            visit(child)

    visit(root)
    return result


def _visibility_snapshot(scene):
    return {
        "collections": [(collection, collection.hide_render, collection.hide_viewport)
                        for collection in _scene_collections(scene.collection)],
        "objects": [(obj, obj.hide_render, obj.hide_viewport) for obj in scene.objects],
    }


def _isolate_turnaround(scene, collection, keep_named_collections=False):
    snapshot = _visibility_snapshot(scene)
    keep = set(collection.objects)
    support = {obj for obj in scene.objects if obj.type in {"CAMERA", "LIGHT"}}
    preserved_collections = set()

    def include_named_collections(candidate, inside_named=False):
        named = (
            keep_named_collections
            and candidate != scene.collection
            and candidate.name.casefold().startswith(("scene", "light", "camera"))
        )
        inside_named = inside_named or named
        if inside_named:
            preserved_collections.add(candidate)
            keep.update(candidate.objects)
        for child in candidate.children:
            include_named_collections(child, inside_named)

    include_named_collections(scene.collection)

    def subtree_is_needed(candidate):
        if (
            candidate == collection
            or candidate in preserved_collections
            or any(obj in support for obj in candidate.objects)
        ):
            return True
        return any(subtree_is_needed(child) for child in candidate.children)

    for obj in scene.objects:
        preserve = obj in keep or obj in support
        obj.hide_render = not preserve
        obj.hide_viewport = not preserve
    for candidate in _scene_collections(scene.collection):
        preserve = candidate == scene.collection or subtree_is_needed(candidate)
        candidate.hide_render = not preserve
        candidate.hide_viewport = not preserve
    return snapshot


def _restore_visibility(snapshot):
    for collection, hide_render, hide_viewport in snapshot.get("collections", ()):
        if collection.name in bpy.data.collections or collection == bpy.context.scene.collection:
            collection.hide_render = hide_render
            collection.hide_viewport = hide_viewport
    for obj, hide_render, hide_viewport in snapshot.get("objects", ()):
        if obj.name in bpy.data.objects:
            obj.hide_render = hide_render
            obj.hide_viewport = hide_viewport


def _render_snapshot(scene):
    render = scene.render
    ffmpeg = render.ffmpeg
    return {
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "fps": render.fps,
        "engine": render.engine,
        "resolution_x": render.resolution_x,
        "resolution_y": render.resolution_y,
        "resolution_percentage": render.resolution_percentage,
        "cycles_samples": scene.cycles.samples if hasattr(scene, "cycles") else None,
        "filepath": render.filepath,
        "use_file_extension": render.use_file_extension,
        "use_overwrite": render.use_overwrite,
        "save_output": render.save_output,
        "media_type": render.image_settings.media_type,
        "file_format": render.image_settings.file_format,
        "color_mode": render.image_settings.color_mode,
        "color_depth": render.image_settings.color_depth,
        "ffmpeg_format": ffmpeg.format,
        "ffmpeg_codec": ffmpeg.codec,
        "ffmpeg_constant_rate_factor": ffmpeg.constant_rate_factor,
    }


def _restore_render(scene, snapshot):
    render = scene.render
    scene.frame_start = snapshot["frame_start"]
    scene.frame_end = snapshot["frame_end"]
    scene.frame_set(snapshot["frame_current"])
    render.fps = snapshot["fps"]
    render.engine = snapshot["engine"]
    render.resolution_x = snapshot["resolution_x"]
    render.resolution_y = snapshot["resolution_y"]
    render.resolution_percentage = snapshot["resolution_percentage"]
    if snapshot["cycles_samples"] is not None:
        scene.cycles.samples = snapshot["cycles_samples"]
    render.filepath = snapshot["filepath"]
    render.use_file_extension = snapshot["use_file_extension"]
    render.use_overwrite = snapshot["use_overwrite"]
    render.save_output = snapshot["save_output"]
    render.image_settings.media_type = snapshot["media_type"]
    render.image_settings.file_format = snapshot["file_format"]
    render.image_settings.color_mode = snapshot["color_mode"]
    render.image_settings.color_depth = snapshot["color_depth"]
    render.ffmpeg.format = snapshot["ffmpeg_format"]
    render.ffmpeg.codec = snapshot["ffmpeg_codec"]
    render.ffmpeg.constant_rate_factor = snapshot["ffmpeg_constant_rate_factor"]


def _configure_animation_output(scene, settings, output_base):
    """Set the media type before its format, as required by Blender 5.2."""
    render = scene.render
    render.image_settings.color_mode = "RGB"
    render.image_settings.color_depth = "8"
    if settings.animation_media_type == "VIDEO":
        extension, codec = VIDEO_CONTAINERS[settings.animation_container]
        render.image_settings.media_type = "VIDEO"
        render.image_settings.file_format = "FFMPEG"
        render.ffmpeg.format = settings.animation_container
        render.ffmpeg.codec = codec
        render.ffmpeg.constant_rate_factor = settings.animation_quality
        render.filepath = output_base
        return f"{output_base}{scene.frame_start:04d}-{scene.frame_end:04d}{extension}"

    render.image_settings.media_type = "IMAGE"
    render.image_settings.file_format = "PNG"
    render.filepath = f"{output_base}_"
    return f"{output_base}_####.png"


def _turnaround_output_directory(settings):
    duplicate = bpy.data.objects.get(settings.animation_object_name)
    source_name = duplicate.get(TURNAROUND_SOURCE_PROP) if duplicate is not None else None
    mesh_name = bpy.path.clean_name(source_name or settings.animation_object_name or "Turnaround")
    return os.path.join(bpy.path.abspath(settings.output_directory), f"{mesh_name}_Turnaround")


def unity_turnaround_render_steps(context):
    """Yield individual render jobs while retaining their temporary scene state."""
    scene = context.scene
    settings = scene.polygroups_render_settings
    collection = bpy.data.collections[settings.animation_collection_name]
    duplicate = bpy.data.objects[settings.animation_object_name]
    root = duplicate.parent
    render_state = _render_snapshot(scene)
    visibility = _isolate_turnaround(scene, collection, settings.animation_keep_scene_collections)
    rotation = root.rotation_euler.copy()
    animation_data = root.animation_data
    action = animation_data.action if animation_data else None
    output_directory = _turnaround_output_directory(settings)
    try:
        os.makedirs(output_directory, exist_ok=True)
        scene.render.engine = 'CYCLES' if settings.render_engine == 'CYCLES' else 'BLENDER_EEVEE'
        if settings.render_engine == 'CYCLES':
            scene.cycles.samples = settings.max_samples
        scene.render.resolution_percentage = 100
        scene.render.use_file_extension = True
        scene.render.use_overwrite = settings.overwrite_existing
        scene.render.save_output = True
        scene.render.image_settings.media_type = 'IMAGE'
        scene.render.image_settings.file_format = settings.animation_views_image_format
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '8'
        if animation_data:
            animation_data.action = None
        scene.frame_set(1)
        base = bpy.path.clean_name(settings.animation_object_name)
        for index, angle in enumerate(VIEW_LABELS, 1):
            root.rotation_euler.z = radians(angle)
            _show_turnaround_labels(scene, collection, angle)
            context.view_layer.update()
            scene.render.filepath = os.path.join(output_directory, f'{base}_{angle:03d}{image_extension(settings.animation_views_image_format)}')
            settings.animation_status = f'Unity: {settings.animation_views_image_format} {index}/4 - {VIEW_LABELS[angle]}'
            yield {'write_still': True}
        root.rotation_euler = rotation
        if animation_data:
            animation_data.action = action
        settings.resolution_x = settings.resolution_y = 1024
        scene.render.resolution_x = scene.render.resolution_y = 1024
        scene.frame_start = 1
        scene.frame_end = max(2, int(settings.animation_frame_count))
        scene.render.fps = settings.animation_fps
        scene.frame_set(1)
        _show_turnaround_labels(scene, collection)
        settings.animation_status = f'Unity: {settings.animation_container} animation'
        output = _configure_animation_output(scene, settings, os.path.join(output_directory, base))
        yield {'animation': True}
        settings.animation_last_output = output
    finally:
        root.rotation_euler = rotation
        if animation_data:
            animation_data.action = action
        _restore_render(scene, render_state)
        _restore_visibility(visibility)


class OBJECT_OT_polygroups_prepare_turnaround_animation(bpy.types.Operator):
    bl_idname = "object.polygroups_prepare_turnaround_animation"
    bl_label = "Prepare Turnaround"
    bl_description = "Duplicate the active object and create a linear 360-degree Z rotation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.active_object is not None

    def execute(self, context):
        scene = context.scene
        settings = scene.polygroups_render_settings
        source = context.active_object
        frame_start = 1
        frame_end = max(frame_start + 1, int(settings.animation_frame_count))

        collection = bpy.data.collections.new("Turnaround Animation")
        scene.collection.children.link(collection)

        duplicate = source.copy()
        if source.data is not None:
            duplicate.data = source.data.copy()
        duplicate.animation_data_clear()
        duplicate.name = f"{source.name}_Turnaround"
        collection.objects.link(duplicate)

        empty = bpy.data.objects.new(f"{source.name}_Turnaround_Root", None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = max(max(source.dimensions) * 0.6, 0.1)
        empty.location = (0.0, 0.0, 0.0)
        empty.rotation_mode = "XYZ"
        collection.objects.link(empty)

        world_matrix = duplicate.matrix_world.copy()
        world_matrix.translation = Vector((0.0, 0.0, 0.0))
        duplicate.parent = empty
        duplicate.matrix_world = world_matrix
        duplicate[TURNAROUND_SOURCE_PROP] = source.name
        empty[TURNAROUND_EMPTY_PROP] = True
        collection[TURNAROUND_COLLECTION_PROP] = True

        empty.rotation_euler.z = 0.0
        empty.keyframe_insert(data_path="rotation_euler", index=2, frame=frame_start)
        empty.rotation_euler.z = tau
        empty.keyframe_insert(data_path="rotation_euler", index=2, frame=frame_end)
        _set_linear_interpolation(empty)

        scene.frame_start = frame_start
        scene.frame_end = frame_end
        scene.frame_set(frame_start)
        _create_turnaround_labels(collection, source.name)
        if scene.camera:
            _show_turnaround_labels(scene, collection)
        settings.animation_collection_name = collection.name
        settings.animation_object_name = duplicate.name
        settings.animation_status = f"Ready: {collection.name}, frames {frame_start}-{frame_end}"

        for obj in context.selected_objects:
            obj.select_set(False)
        duplicate.select_set(True)
        context.view_layer.objects.active = duplicate
        self.report({"INFO"}, settings.animation_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_render_turnaround_views(bpy.types.Operator):
    bl_idname = "object.polygroups_render_turnaround_views"
    bl_label = "Render Four Views"
    bl_description = "Render still images at 0, 90, 180 and 270 degrees in the selected format"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_render_settings
        return bool(settings.animation_collection_name) and not settings.is_running and _ACTIVE_RENDER_TASK is None

    def execute(self, context):
        scene = context.scene
        settings = scene.polygroups_render_settings
        collection = bpy.data.collections.get(settings.animation_collection_name)
        duplicate = bpy.data.objects.get(settings.animation_object_name)
        if collection is None or not collection.get(TURNAROUND_COLLECTION_PROP) or duplicate is None or duplicate.parent is None:
            self.report({"ERROR"}, "Prepare a turnaround animation first")
            return {"CANCELLED"}
        if scene.camera is None:
            self.report({"ERROR"}, "The scene needs an active camera")
            return {"CANCELLED"}

        output_directory = _turnaround_output_directory(settings)
        try:
            os.makedirs(output_directory, exist_ok=True)
        except OSError as error:
            self.report({"ERROR"}, f"Cannot create output folder: {error}")
            return {"CANCELLED"}

        root = duplicate.parent
        render_state = _render_snapshot(scene)
        visibility = _isolate_turnaround(scene, collection, settings.animation_keep_scene_collections)
        saved_rotation = root.rotation_euler.copy()
        animation_data = root.animation_data
        saved_action = animation_data.action if animation_data is not None else None
        settings.is_running = True
        outputs = []
        error = None
        try:
            if animation_data is not None:
                animation_data.action = None
            scene.render.resolution_x = settings.resolution_x
            scene.render.resolution_y = settings.resolution_y
            scene.render.resolution_percentage = settings.resolution_scale
            if settings.render_engine == "CYCLES":
                scene.render.engine = "CYCLES"
                scene.cycles.samples = settings.max_samples
            else:
                try:
                    scene.render.engine = "BLENDER_EEVEE_NEXT"
                except TypeError:
                    scene.render.engine = "BLENDER_EEVEE"
            scene.render.image_settings.media_type = "IMAGE"
            scene.render.image_settings.file_format = settings.animation_views_image_format
            scene.render.image_settings.color_mode = "RGB"
            scene.render.image_settings.color_depth = "8"
            scene.render.use_file_extension = True
            scene.render.use_overwrite = settings.overwrite_existing
            scene.render.save_output = True
            scene.frame_set(scene.frame_start)
            base = bpy.path.clean_name(settings.animation_object_name)
            for angle in (0, 90, 180, 270):
                root.rotation_euler.z = radians(angle)
                _show_turnaround_labels(scene, collection, angle)
                context.view_layer.update()
                path = os.path.join(output_directory, f"{base}_{angle:03d}{image_extension(settings.animation_views_image_format)}")
                scene.render.filepath = path
                result = bpy.ops.render.render(write_still=True)
                if "FINISHED" not in result:
                    raise RuntimeError(f"Render cancelled at {angle} degrees")
                outputs.append(path)
        except Exception as exc:
            error = exc
        finally:
            root.rotation_euler = saved_rotation
            try:
                _restore_render(scene, render_state)
            finally:
                if animation_data is not None:
                    animation_data.action = saved_action
                _restore_visibility(visibility)
                settings.is_running = False

        if error is not None:
            settings.animation_status = f"Four views failed: {error}"
            self.report({"ERROR"}, settings.animation_status)
            return {"CANCELLED"}
        settings.animation_last_output = output_directory
        settings.animation_status = f"Saved {len(outputs)} views to {output_directory}"
        self.report({"INFO"}, settings.animation_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_render_turnaround_animation(bpy.types.Operator):
    bl_idname = "object.polygroups_render_turnaround_animation"
    bl_label = "Render Animation"
    bl_description = "Render the prepared turnaround as video or PNG frames while temporarily isolating its geometry"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_render_settings
        return bool(settings.animation_collection_name) and not settings.is_running and _ACTIVE_RENDER_TASK is None

    def _begin(self, context):
        scene = context.scene
        settings = scene.polygroups_render_settings
        collection = bpy.data.collections.get(settings.animation_collection_name)
        if collection is None or not collection.get(TURNAROUND_COLLECTION_PROP):
            self.report({"ERROR"}, "Prepare a turnaround animation first")
            return False
        if scene.camera is None:
            self.report({"ERROR"}, "The scene needs an active camera")
            return False

        output_directory = _turnaround_output_directory(settings)
        try:
            os.makedirs(output_directory, exist_ok=True)
        except OSError as error:
            self.report({"ERROR"}, f"Cannot create output folder: {error}")
            return False

        name = bpy.path.clean_name(settings.animation_object_name or collection.name)
        output_base = os.path.join(output_directory, name)
        self._scene = scene
        self._settings = settings
        self._window_manager = context.window_manager
        self._render_state = _render_snapshot(scene)
        self._visibility = _isolate_turnaround(
            scene, collection, settings.animation_keep_scene_collections,
        )
        self._output_file = ""
        self._timer = None
        self._draw_handle = None
        self._handlers_registered = False
        self._finished = False
        self._render_completed = False
        self._render_cancelled = False
        self._frames_done = 0
        self._total_frames = max(2, int(settings.animation_frame_count))
        settings.is_running = True
        settings.animation_progress = 0.0
        settings.animation_status = "Rendering animation..."
        try:
            scene.frame_start = 1
            scene.frame_end = self._total_frames
            scene.render.fps = settings.animation_fps
            scene.render.resolution_x = settings.resolution_x
            scene.render.resolution_y = settings.resolution_y
            scene.render.resolution_percentage = settings.resolution_scale
            _show_turnaround_labels(scene, collection)
            if settings.render_engine == "CYCLES":
                scene.render.engine = "CYCLES"
                scene.cycles.samples = settings.max_samples
            else:
                try:
                    scene.render.engine = "BLENDER_EEVEE_NEXT"
                except TypeError:
                    scene.render.engine = "BLENDER_EEVEE"
            scene.render.use_file_extension = True
            scene.render.use_overwrite = settings.overwrite_existing
            scene.render.save_output = True
            self._output_file = _configure_animation_output(scene, settings, output_base)
        except Exception as error:
            self._finish(error=error)
            return False
        return True

    def _finish(self, *, completed=False, error=None):
        global _ACTIVE_RENDER_TASK
        if self._finished:
            return {"FINISHED"} if completed else {"CANCELLED"}
        self._finished = True
        if self._handlers_registered:
            for handlers, callback in (
                (bpy.app.handlers.render_post, self._on_render_post),
                (bpy.app.handlers.render_complete, self._on_render_complete),
                (bpy.app.handlers.render_cancel, self._on_render_cancel),
            ):
                if callback in handlers:
                    handlers.remove(callback)
            self._handlers_registered = False
        if self._timer is not None:
            self._window_manager.event_timer_remove(self._timer)
            self._timer = None
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        if getattr(self, "_progress_started", False):
            self._window_manager.progress_end()
            self._progress_started = False
        if hasattr(self, "_render_display_type"):
            bpy.context.preferences.view.render_display_type = self._render_display_type
            del self._render_display_type
        try:
            _restore_render(self._scene, self._render_state)
        finally:
            _restore_visibility(self._visibility)
            self._settings.is_running = False
            if _ACTIVE_RENDER_TASK is self:
                _ACTIVE_RENDER_TASK = None

        if error is not None:
            self._settings.animation_status = f"Render failed: {error}"
            self.report({"ERROR"}, self._settings.animation_status)
        elif completed:
            self._settings.animation_progress = 100.0
            self._settings.animation_last_output = self._output_file
            self._settings.animation_status = f"Saved: {self._output_file}"
            self.report({"INFO"}, self._settings.animation_status)
        else:
            self._settings.animation_status = "Animation render cancelled"
            self.report({"WARNING"}, self._settings.animation_status)
        _redraw_animation_ui(self._window_manager)
        return {"FINISHED"} if completed else {"CANCELLED"}

    def _on_render_post(self, scene, *args):
        if scene == self._scene:
            self._frames_done = min(self._total_frames, self._frames_done + 1)

    def _on_render_complete(self, scene, *args):
        if scene == self._scene:
            self._frames_done = self._total_frames
            self._render_completed = True

    def _on_render_cancel(self, scene, *args):
        if scene == self._scene:
            self._render_cancelled = True

    def _refresh_progress(self):
        progress = 100.0 * self._frames_done / self._total_frames
        if progress != self._settings.animation_progress:
            self._settings.animation_progress = progress
            if not self._render_completed:
                self._settings.animation_status = (
                    f"Rendering frame {self._frames_done}/{self._total_frames}"
                )
            if self._progress_started:
                self._window_manager.progress_update(progress)
            _redraw_animation_ui(self._window_manager)

    def _watchdog(self):
        """Update the UI even when Blender's render window owns modal events."""
        if self._finished:
            return None
        self._refresh_progress()
        if self._render_completed or self._render_cancelled:
            self._finish(completed=self._render_completed)
            return None
        return 0.1

    def execute(self, context):
        """Keep scripted/background rendering synchronous."""
        if not self._begin(context):
            return {"CANCELLED"}
        try:
            result = bpy.ops.render.render(animation=True)
        except Exception as error:
            return self._finish(error=error)
        return self._finish(completed="FINISHED" in result)

    def invoke(self, context, event):
        global _ACTIVE_RENDER_TASK
        if bpy.app.background:
            return self.execute(context)
        if not self._begin(context):
            return {"CANCELLED"}
        try:
            self._area = context.area
            region = next((region for region in context.area.regions if region.type == "WINDOW"), None)
            self._mouse_x = event.mouse_x - region.x if region else 32
            self._mouse_y = event.mouse_y - region.y if region else 32
            self._render_display_type = context.preferences.view.render_display_type
            context.preferences.view.render_display_type = "NONE"
            self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                _draw_animation_cursor, (), "WINDOW", "POST_PIXEL",
            )
            self._handlers_registered = True
            for handlers, callback in (
                (bpy.app.handlers.render_post, self._on_render_post),
                (bpy.app.handlers.render_complete, self._on_render_complete),
                (bpy.app.handlers.render_cancel, self._on_render_cancel),
            ):
                handlers.append(callback)
            _ACTIVE_RENDER_TASK = self
            self._window_manager.progress_begin(0, 100)
            self._progress_started = True
            self._timer = self._window_manager.event_timer_add(0.1, window=context.window)
            self._window_manager.modal_handler_add(self)
            bpy.app.timers.register(self._watchdog, first_interval=0.1)
            _redraw_animation_ui(self._window_manager)
            result = bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        except Exception as error:
            return self._finish(error=error)
        if "RUNNING_MODAL" in result:
            return {"RUNNING_MODAL"}
        return self._finish(completed="FINISHED" in result)

    def modal(self, context, event):
        if self._finished:
            return {"FINISHED"}
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"} and context.area == self._area:
            region = next((region for region in self._area.regions if region.type == "WINDOW"), None)
            if region is not None:
                self._mouse_x = event.mouse_x - region.x
                self._mouse_y = event.mouse_y - region.y
                self._area.tag_redraw()
        # Blender events expose no timer handle. Progress refresh is idempotent,
        # so TIMER events from other modal tools can safely refresh it too.
        if event.type == "TIMER":
            self._refresh_progress()
            if self._render_completed or self._render_cancelled:
                return self._finish(completed=self._render_completed)
        return {"PASS_THROUGH"}
