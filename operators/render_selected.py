"""Temporary front-camera fitting for rendering the selected objects."""
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view


def selected_bounds(context, objects=None):
    depsgraph = context.evaluated_depsgraph_get()
    points = []
    for obj in (context.selected_objects if objects is None else objects):
        if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
    if not points:
        raise RuntimeError('Select objects with geometry')
    minimum = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    maximum = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    return points, (minimum + maximum) / 2, maximum - minimum


def fit_camera(context, camera, points, center, size, margin=.1, only_y=False):
    if camera.data.type not in {'PERSP', 'ORTHO'}:
        raise RuntimeError('Use a perspective or orthographic camera')
    camera.data.shift_x = camera.data.shift_y = 0
    span = max(max(size), .01)
    frame_center = center.copy()
    if only_y:
        # Preserve the configured studio height and horizontal position.
        position = camera.matrix_world.translation
        frame_center.x, frame_center.z = position.x, position.z
    # A very small near plane combined with a huge far plane loses Eevee
    # light-culling precision: Area lights disappear in the camera render.
    camera.data.clip_start = max(.00001, span * .0001)
    camera.rotation_euler = Vector((0, 1, 0)).to_track_quat('-Z', 'Y').to_euler()
    # Use world transforms, even when the camera has a parent.
    rotation = Vector((0, 1, 0)).to_track_quat('-Z', 'Y').to_matrix().to_4x4()

    def fits(value):
        matrix = rotation.copy()
        matrix.translation = frame_center + Vector((0, -(span * 2 if camera.data.type == 'ORTHO' else value), 0))
        camera.matrix_world = matrix
        if camera.data.type == 'ORTHO':
            camera.data.ortho_scale = value
        context.view_layer.update()
        projections = [world_to_camera_view(context.scene, camera, p) for p in points]
        return all(p.z > camera.data.clip_start and margin <= p.x <= 1-margin and margin <= p.y <= 1-margin for p in projections)

    if camera.data.type == 'PERSP':
        # Solve the perspective frustum inequalities directly. This permits
        # exact evaluated vertices rather than conservative box corners,
        # without projecting a dense mesh 48 times during binary search.
        frame = camera.data.view_frame(scene=context.scene)
        x_limit = max(abs(v.x / v.z) for v in frame) * (1 - 2 * margin)
        z_limit = max(abs(v.y / v.z) for v in frame) * (1 - 2 * margin)
        upper = max(.0001, max(max(abs(p.x-frame_center.x) / x_limit,
                                   abs(p.z-frame_center.z) / z_limit,
                                   camera.data.clip_start * 2) - (p.y-frame_center.y)
                               for p in points))
    else:
        upper = span
        for _ in range(40):
            if fits(upper):
                break
            upper *= 2
        else:
            raise RuntimeError('Unable to fit selection in camera')
        lower = .0001
        for _ in range(48):
            middle = (lower + upper) / 2
            if fits(middle):
                upper = middle
            else:
                lower = middle
    fits(upper * 1.0001)
    view = camera.matrix_world.inverted()
    depths = [-(view @ point).z for point in points]
    camera.data.clip_start = max(.00001, min(depths) * .01)
    camera.data.clip_end = max(max(depths) * 4, span * 10, camera.data.clip_start * 100)


def fit_render_aspect(context, camera, points, center, size, settings):
    """Use the longest configured image side and fit the projected silhouette."""
    longest = max(settings.resolution_x, settings.resolution_y)
    aspect = max(size.x, .001) / max(size.z, .001)
    for _ in range(4):
        width = longest if aspect >= 1 else max(4, round(longest * aspect))
        height = max(4, round(longest / aspect)) if aspect >= 1 else longest
        settings.resolution_x, settings.resolution_y = width, height
        context.scene.render.resolution_x, context.scene.render.resolution_y = width, height
        fit_camera(context, camera, points, center, size)
        projected = [world_to_camera_view(context.scene, camera, p) for p in points]
        w = max(p.x for p in projected) - min(p.x for p in projected)
        h = max(p.y for p in projected) - min(p.y for p in projected)
        if w < 1e-8 or h < 1e-8 or abs(w / h - 1) < .002:
            break
        aspect *= w / h


class OBJECT_OT_render_selected_auto(bpy.types.Operator):
    bl_idname = 'object.polygroups_render_selected_auto'
    bl_label = 'Auto Frame & Render Selected'
    bl_description = 'Temporarily frame selected objects with 10% margins, render, then restore the camera and aim'
    bl_options = {'REGISTER'}
    output_path: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'})
    fixed_resolution: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    fixed_camera: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return bool(context.scene.camera and context.selected_objects and not context.scene.polygroups_render_settings.is_running)

    def execute(self, context):
        steps = self._steps(context)
        try:
            next(steps)
        except StopIteration as finished:
            return finished.value
        finally:
            steps.close()

    def _steps(self, context, interactive=False, output_path=None, fixed_resolution=None, fixed_camera=None):
        from . import render_queue as rq
        settings = context.scene.polygroups_render_settings
        scene = context.scene
        camera = scene.camera
        if not camera:
            self.report({'ERROR'}, 'Set the scene camera first')
            return {'CANCELLED'}
        try:
            points, center, size = selected_bounds(context)
        except RuntimeError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        matrix = camera.matrix_world.copy()
        original_data = camera.data
        constraints = [(c, c.mute) for c in camera.constraints]
        aim = settings.studio_camera_aim if settings.studio_camera == camera else None
        aim_matrix = aim.matrix_world.copy() if aim else None
        rq.ensure_render_support_visible(context)
        snapshot = rq._snapshot_visibility()
        resolution = (scene.render.resolution_x, scene.render.resolution_y, scene.render.use_file_extension)
        settings_resolution = (settings.resolution_x, settings.resolution_y)
        pixel_aspect = (scene.render.pixel_aspect_x, scene.render.pixel_aspect_y)
        mesh_copies = []
        light_root, light_matrix = None, None
        temporary_data = original_data.copy()
        path = output_path or self.output_path or rq._current_state_render_path()
        fixed_resolution = self.fixed_resolution if fixed_resolution is None else fixed_resolution
        fixed_camera = self.fixed_camera if fixed_camera is None else fixed_camera
        job = {'output_path': path, 'transparent_output_path': rq._transparent_output_path(path),
               'freestyle_output_path': rq._freestyle_pass_path(path),
               'freestyle_overlay_path': rq._freestyle_overlay_path(path)}
        try:
            camera.data = temporary_data
            for constraint, mute in constraints:
                constraint.mute = True
            from .render_studio import position_lights
            light_center = center.copy()
            if fixed_camera:
                # Separate LOD renders retain the framing of LOD0: lights must
                # follow that camera's X/Z rather than each LOD's label bounds.
                light_center.x = camera.matrix_world.translation.x
                light_center.z = camera.matrix_world.translation.z
            light_root, light_matrix = position_lights(context, light_center)
            if aim:
                moved = aim_matrix.copy()
                moved.translation = center
                aim.matrix_world = moved
            scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
            if fixed_resolution:
                scene.render.resolution_x, scene.render.resolution_y = settings.resolution_x, settings.resolution_y
                if not fixed_camera:
                    fit_camera(context, camera, points, center, size)
                else:
                    camera.matrix_world = matrix
                    context.view_layer.update()
            else:
                fit_render_aspect(context, camera, points, center, size, settings)
            selected = set(context.selected_objects)
            if settings.freestyle_edges:
                # The queue marks all mesh edges before rendering; the selected
                # render needs the same preparation, without changing originals.
                for obj in selected:
                    if obj.type != 'MESH':
                        continue
                    original_mesh = obj.data
                    copy = original_mesh.copy()
                    mesh_copies.append((obj, original_mesh, copy))
                    obj.data = copy
                rq._mark_freestyle_edges([obj for obj, _, _ in mesh_copies], True)
            for obj in scene.objects:
                if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}:
                    continue
                is_backdrop = obj.get('polygroups_studio_role') == 'backdrop' or any(rq._scene_collection_matches(c, settings) for c in obj.users_collection)
                obj.hide_render = obj not in selected and not is_backdrop
            if interactive:
                yield from rq._render_current_job_steps(context, settings, job)
            else:
                rq._render_current_job(context, settings, job)
            settings.last_output_path = path
            settings.status = 'Rendered selected objects'
        except Exception as error:
            self.report({'ERROR'}, f'Render selected failed: {error}')
            return {'CANCELLED'}
        finally:
            if light_root:
                light_root.matrix_world = light_matrix
            for obj, original_mesh, copy in mesh_copies:
                obj.data = original_mesh
                bpy.data.meshes.remove(copy)
            camera.data = original_data
            camera.matrix_world = matrix
            if aim:
                aim.matrix_world = aim_matrix
            for constraint, mute in constraints:
                constraint.mute = mute
            bpy.data.cameras.remove(temporary_data)
            rq._restore_visibility(snapshot)
            scene.render.resolution_x, scene.render.resolution_y, scene.render.use_file_extension = resolution
            settings.resolution_x, settings.resolution_y = settings_resolution
            scene.render.pixel_aspect_x, scene.render.pixel_aspect_y = pixel_aspect
            context.view_layer.update()
        self.report({'INFO'}, f'Rendered selected objects: {path}')
        return {'FINISHED'}


CLASSES = (OBJECT_OT_render_selected_auto,)
