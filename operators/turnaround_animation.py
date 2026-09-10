import os
from math import tau

import bpy
from mathutils import Vector


TURNAROUND_COLLECTION_PROP = "polygroups_turnaround_collection"
TURNAROUND_SOURCE_PROP = "polygroups_turnaround_source"
TURNAROUND_EMPTY_PROP = "polygroups_turnaround_empty"


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


def _isolate_turnaround(scene, collection):
    snapshot = _visibility_snapshot(scene)
    keep = set(collection.objects)
    support = {obj for obj in scene.objects if obj.type in {"CAMERA", "LIGHT"}}

    def subtree_is_needed(candidate):
        if candidate == collection or any(obj in support for obj in candidate.objects):
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
        "filepath": render.filepath,
        "use_file_extension": render.use_file_extension,
        "use_overwrite": render.use_overwrite,
        "save_output": render.save_output,
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
    render.filepath = snapshot["filepath"]
    render.use_file_extension = snapshot["use_file_extension"]
    render.use_overwrite = snapshot["use_overwrite"]
    render.save_output = snapshot["save_output"]
    render.image_settings.file_format = snapshot["file_format"]
    render.image_settings.color_mode = snapshot["color_mode"]
    render.image_settings.color_depth = snapshot["color_depth"]
    render.ffmpeg.format = snapshot["ffmpeg_format"]
    render.ffmpeg.codec = snapshot["ffmpeg_codec"]
    render.ffmpeg.constant_rate_factor = snapshot["ffmpeg_constant_rate_factor"]


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

        center = _object_world_center(source)
        empty = bpy.data.objects.new(f"{source.name}_Turnaround_Root", None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = max(max(source.dimensions) * 0.6, 0.1)
        empty.location = center
        empty.rotation_mode = "XYZ"
        collection.objects.link(empty)

        world_matrix = duplicate.matrix_world.copy()
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
        settings.animation_collection_name = collection.name
        settings.animation_object_name = duplicate.name
        settings.animation_status = f"Ready: {collection.name}, frames {frame_start}-{frame_end}"

        for obj in context.selected_objects:
            obj.select_set(False)
        duplicate.select_set(True)
        context.view_layer.objects.active = duplicate
        self.report({"INFO"}, settings.animation_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_render_turnaround_animation(bpy.types.Operator):
    bl_idname = "object.polygroups_render_turnaround_animation"
    bl_label = "Render Animation"
    bl_description = "Render the prepared turnaround as an MP4 while temporarily isolating its geometry"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.polygroups_render_settings
        return bool(settings.animation_collection_name) and not settings.is_running

    def execute(self, context):
        scene = context.scene
        settings = scene.polygroups_render_settings
        collection = bpy.data.collections.get(settings.animation_collection_name)
        if collection is None or not collection.get(TURNAROUND_COLLECTION_PROP):
            self.report({"ERROR"}, "Prepare a turnaround animation first")
            return {"CANCELLED"}
        if scene.camera is None:
            self.report({"ERROR"}, "The scene needs an active camera")
            return {"CANCELLED"}

        base_directory = bpy.path.abspath(settings.output_directory)
        output_directory = os.path.join(base_directory, "Render Animation")
        try:
            os.makedirs(output_directory, exist_ok=True)
        except OSError as error:
            self.report({"ERROR"}, f"Cannot create output folder: {error}")
            return {"CANCELLED"}

        name = bpy.path.clean_name(settings.animation_object_name or collection.name)
        output_base = os.path.join(output_directory, name)
        output_file = f"{output_base}.mp4"
        visibility = _isolate_turnaround(scene, collection)
        render_state = _render_snapshot(scene)
        settings.is_running = True
        settings.animation_status = "Rendering animation..."
        result = {"CANCELLED"}
        try:
            scene.frame_start = 1
            scene.frame_end = max(2, int(settings.animation_frame_count))
            scene.render.fps = settings.animation_fps
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
            scene.render.filepath = output_base
            scene.render.use_file_extension = True
            scene.render.use_overwrite = settings.overwrite_existing
            scene.render.save_output = True
            scene.render.image_settings.color_mode = "RGB"
            scene.render.image_settings.color_depth = "8"
            try:
                scene.render.image_settings.file_format = "FFMPEG"
            except TypeError as error:
                formats = tuple(
                    item.identifier
                    for item in scene.render.image_settings.bl_rna.properties["file_format"].enum_items
                )
                raise RuntimeError(
                    f"FFmpeg output is unavailable for {scene.render.engine}; formats: {formats}"
                ) from error
            scene.render.ffmpeg.format = "MPEG4"
            scene.render.ffmpeg.codec = "H264"
            scene.render.ffmpeg.constant_rate_factor = settings.animation_quality
            result = bpy.ops.render.render(animation=True)
        except Exception as error:
            settings.animation_status = f"Render failed: {error}"
            self.report({"ERROR"}, settings.animation_status)
        finally:
            _restore_render(scene, render_state)
            _restore_visibility(visibility)
            settings.is_running = False

        if "FINISHED" not in result:
            if not settings.animation_status.startswith("Render failed"):
                settings.animation_status = "Animation render cancelled"
            return {"CANCELLED"}
        settings.animation_last_output = output_file
        settings.animation_status = f"Saved: {output_file}"
        self.report({"INFO"}, settings.animation_status)
        return {"FINISHED"}
