"""Phase 2 asset-by-asset previews using the section 13 render operators."""
import json
import os
import re
import bpy
from mathutils import Vector
from . import render_queue as rq
from . import render_studio as studio
from .render_selected import selected_bounds, fit_camera
from .render_textures import texture_planes, collection_textures
from .sequential_jobs import SequentialJob

ASSET = re.compile(r'.+_\d+_\d+_Collection$', re.I)


def configure_auto_render(context):
    p = context.scene.polygroups_model_preparation_settings
    s = context.scene.polygroups_render_settings
    s.resolution_aspect_preset = 'WIDE'
    s.resolution_size_preset = '2K'
    s.resolution_x, s.resolution_y, s.resolution_scale = 2048, 1152, 100
    s.render_engine = 'EEVEE'
    s.image_format = 'PNG'
    s.texture_render_mode = 'COMBINED'
    if p.phase2_auto_selection:
        s.render_low = False
        s.render_mid, s.render_high = True, False
        s.render_lod_enabled = True
        s.render_lod_level = 'LOD0'
    s.freestyle_edges = p.phase2_auto_freestyle
    s.freestyle_as_render_pass = p.phase2_auto_freestyle_pass
    s.freestyle_line_color = p.phase2_auto_freestyle_color
    s.multiview_render = p.phase2_auto_multiview
    s.multiview_render_hero = p.phase2_auto_mv_hero
    s.multiview_offset = p.phase2_auto_mv_offset / max(context.scene.unit_settings.scale_length, 1e-8)
    s.multiview_angle = p.phase2_auto_mv_angle
    context.scene.render.resolution_x = s.resolution_x
    context.scene.render.resolution_y = s.resolution_y
    context.scene.render.resolution_percentage = s.resolution_scale
    rq._apply_render_engine(context.scene, s)


def asset_targets(context):
    settings = context.scene.polygroups_render_settings
    reachable = set(context.scene.collection.children_recursive)
    result = []
    for col in bpy.data.collections:
        if col not in reachable or not ASSET.fullmatch(col.name):
            continue
        sources = rq._find_asset_objects(col, rq._asset_name_from_collection(col), settings)
        if sources:
            result.append((col, sources))
    return sorted(result, key=lambda item: [int(part) if part.isdigit() else part.lower()
        for part in re.split(r'(\d+)', item[0].name)])


MANAGED_STUDIO = {
    'camera': ('studio_camera', 'CAMERA'), 'camera_aim': ('studio_camera_aim', 'EMPTY'),
    'backdrop': ('studio_backdrop', 'MESH'),
    **{role + '_position': ('studio_' + role + '_position', 'EMPTY') for role in ('camera', 'scene', 'light')},
    **{role: ('studio_' + role, 'LIGHT') for role in ('key', 'fill', 'rim')},
    **{role + '_aim': ('studio_' + role + '_aim', 'EMPTY') for role in ('key', 'fill', 'rim')},
}


def recover_managed_studio(context):
    """Reuse tagged studio objects even if their Scene RNA pointers were lost."""
    settings = context.scene.polygroups_render_settings
    for role, (prop, kind) in MANAGED_STUDIO.items():
        current = getattr(settings, prop)
        if current and current.name in context.scene.objects and current.get(studio.TAG) == role and current.type == kind:
            continue
        setattr(settings, prop, next((obj for obj in context.scene.objects
            if obj.get(studio.TAG) == role and obj.type == kind), None))


def replace_foreign_studio(context):
    """Remove foreign cameras/lights and explicit old studio collections, not assets."""
    roles = {role: kind for role, (prop, kind) in MANAGED_STUDIO.items()}
    support = {col for col in context.scene.collection.children_recursive
        if not ASSET.fullmatch(col.name) and (col.get(studio.TAG) in {'scene', 'camera', 'light'}
            or col.name.lower() in {'scene', 'camera', 'light', 'lights'}
            or col.name.lower().startswith(('scene_', 'camera_', 'light_')))}
    pending = list(support)
    while pending:
        for child in pending.pop().children:
            if child not in support and not ASSET.fullmatch(child.name):
                support.add(child)
                pending.append(child)
    old = {col for col in support if col.get(studio.TAG) not in {'scene', 'camera', 'light'}}
    doomed = set()
    for obj in context.scene.objects:
        role = obj.get(studio.TAG)
        if obj.type in {'CAMERA', 'LIGHT'} and roles.get(role) != obj.type:
            doomed.add(obj)
        elif role in roles and roles[role] != obj.type:
            doomed.add(obj)
        elif (obj.users_collection and set(obj.users_collection) <= support
                and roles.get(role) != obj.type):
            doomed.add(obj)
    for obj in doomed:
        if obj.library:
            raise ValueError('Cannot replace a linked foreign studio object: ' + obj.name)
        data, kind = obj.data, obj.type
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and data.users == 0:
            ids = {'MESH': bpy.data.meshes, 'CAMERA': bpy.data.cameras, 'LIGHT': bpy.data.lights}.get(kind)
            if ids is not None:
                ids.remove(data)
    for col in old:
        if not col.objects and not col.children:
            bpy.data.collections.remove(col)


def prepare_textures(context, collections):
    settings = context.scene.polygroups_render_settings
    settings.is_running = False
    try:
        result = bpy.ops.object.polygroups_prepare_render_textures('EXEC_DEFAULT',
            collections_json=json.dumps([col.name for col in collections]))
        if 'FINISHED' not in result:
            raise RuntimeError('Prepare Textures failed')
    finally:
        settings.is_running = True


def scan_jobs(context, collections, include_textures):
    """Use the existing Scan Queue operator, restricted to this auto-render batch."""
    settings = context.scene.polygroups_render_settings
    names = {col.name for col in collections}
    settings.is_running = False
    prepared = [(obj, obj.get(rq.MULTIVIEW_PREPARED_PROP)) for obj in context.scene.objects
                if obj.get(rq.MULTIVIEW_PREPARED_PROP)]
    try:
        # Explicit Auto Render toggles override legacy prepared multiview geometry.
        for obj, flag in prepared:
            obj[rq.MULTIVIEW_PREPARED_PROP] = False
        result = bpy.ops.object.polygroups_scan_render_queue('EXEC_DEFAULT')
        if 'FINISHED' not in result:
            raise RuntimeError('Scan Queue failed')
        return [job for job in rq._load_queue(settings) if job['collection'] in names
                and (include_textures or not job.get('texture_kind'))]
    finally:
        for obj, flag in prepared:
            obj[rq.MULTIVIEW_PREPARED_PROP] = flag
        settings.is_running = True


def frame_asset(context, objects, origin):
    """One perspective frame, shared by every variant and Hero of this asset."""
    settings = context.scene.polygroups_render_settings
    camera = context.scene.camera
    if camera is None:
        raise ValueError('Enable Scene and Camera Setup or provide an active camera')
    points, center, size = selected_bounds(context, objects)
    if settings.studio_camera_aim and camera == settings.studio_camera:
        aim = settings.studio_camera_aim
        matrix = aim.matrix_world.copy()
        matrix.translation = center
        aim.matrix_world = matrix
    fit_camera(context, camera, points, center, size)
    context.view_layer.update()
    return points


def render_asset_job(context, job, views, origin):
    """Same rendering backend as Render Queue, without moving/refitting the camera."""
    if not rq._prepare_scene_for_job(job):
        raise RuntimeError('Missing render job: ' + job['object'])
    source = bpy.data.objects.get(job['object'])
    matrices = []
    if not job.get('texture_kind'):
        current_views = views.get(source, [])
        if current_views:
            source.hide_render = source.hide_viewport = True
            for obj in current_views:
                show = job.get('view_mode') != 'Hero' or rq._base_name(obj.name).endswith('_MV_Front')
                obj.hide_render = obj.hide_viewport = not show
                for col in obj.users_collection:
                    rq._set_collection_enabled(col, True)
        else:
            matrices.append((source, source.matrix_world.copy()))
            matrix = source.matrix_world.copy()
            matrix.translation = origin
            source.matrix_world = matrix
    context.view_layer.update()
    try:
        rq._render_current_job(context, context.scene.polygroups_render_settings, job)
    finally:
        for obj, matrix in matrices:
            obj.matrix_world = matrix
        context.view_layer.update()


class OBJECT_OT_polygroups_phase2_auto_render(SequentialJob, bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_auto_render'
    bl_label = 'Start Auto Render'
    bl_description = 'Scan prepared MID/LOD0 assets, configure section 13 and render each asset with one fixed camera frame'
    bl_options = {'REGISTER', 'UNDO'}
    phase2_job = True
    phase2_running_property = 'phase2_auto_render_running'

    @classmethod
    def poll(cls, context):
        from .phase2_processing import available
        return context.mode == 'OBJECT' and available(context)

    def execute(self, context):
        return self.start_job(context, self.steps(context), modal=not bpy.app.background)

    def steps(self, context):
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_render_settings
        configure_auto_render(context)
        assets = asset_targets(context)
        if not assets:
            raise ValueError('No MID/LOD0 meshes in Asset_NameIndex_VersionIndex_Collection assets')
        if p.phase2_auto_scene:
            replace_foreign_studio(context)
            recover_managed_studio(context)
            if 'FINISHED' not in bpy.ops.render.polygroups_reset_studio('EXEC_DEFAULT', scope='ALL'):
                raise RuntimeError('Scene Setup failed')
        if context.scene.camera is None:
            raise ValueError('The scene needs an active camera')
        from .rename_objects import ensure_collection_visible_in_view_layer
        for col, sources in assets:
            if not ensure_collection_visible_in_view_layer(context, col):
                raise ValueError('Cannot enable ' + col.name)
        rq.ensure_render_support_visible(context)
        bpy.ops.object.select_all(action='DESELECT')
        for col, sources in assets:
            for obj in sources:
                obj.hide_viewport = obj.hide_render = obj.hide_select = False
                obj.hide_set(False)
                obj.select_set(True)
        if s.freestyle_edges:
            rq._mark_freestyle_edges([obj for col, sources in assets for obj in sources], True)
        snapshot = rq._snapshot_visibility()
        all_views, done, history = [], 0, []
        completed = False
        try:
            s.is_running, s.stop_requested = True, False
            if p.phase2_auto_textures and p.phase2_auto_texture_prepare == 'ALL':
                prepare_textures(context, [col for col, sources in assets])
            # Exact expected count, including only available linked texture pairs.
            expected = sum(len(sources) * (2 if s.multiview_render and s.multiview_render_hero else 1)
                + int(p.phase2_auto_textures and collection_textures(col) is not None)
                for col, sources in assets)
            yield .02, f'Auto Render: {len(assets)} assets | 2048 x 1152 | Eevee'
            for ordinal, (col, sources) in enumerate(assets):
                rq._set_asset_collection_enabled(col, True)
                if p.phase2_auto_textures and p.phase2_auto_texture_prepare == 'EACH':
                    prepare_textures(context, [col])
                jobs = scan_jobs(context, [col], p.phase2_auto_textures)
                history.extend(jobs)
                s.queue_data = json.dumps(history)
                s.total_count, s.collection_count = expected, len(assets)
                s.queue_scanned = True
                s.queue_index = done
                # MID and LOD0 variants share an origin in the preview, without
                # changing the saved arrangement of the original meshes.
                origin = sources[0].matrix_world.translation.copy()
                studio.position_studio_at_origin(context, origin)
                views, frame_objects = {}, []
                for source in sources:
                    if s.multiview_render:
                        generated = rq._multiview_views(source, col, rq._asset_name_from_collection(col), s)
                        offset = origin - source.matrix_world.translation
                        for obj in generated:
                            matrix = obj.matrix_world.copy()
                            matrix.translation += offset
                            obj.matrix_world = matrix
                        views[source] = generated
                        all_views.extend(generated)
                        frame_objects.extend(generated)
                    else:
                        # Virtual points use the same aligned origin as the render.
                        frame_objects.append(source)
                planes = texture_planes(col) if p.phase2_auto_textures else []
                for plane in planes:
                    plane.location = origin + Vector((-.7 if plane.get('polygroups_texture_plane') == 'BaseColor' else .7, 0, .5))
                frame_objects.extend(planes)
                context.view_layer.update()
                if p.phase2_auto_scene and p.phase2_auto_camera:
                    virtual_matrices = []
                    try:
                        if not s.multiview_render:
                            for source in sources:
                                virtual_matrices.append((source, source.matrix_world.copy()))
                                matrix = source.matrix_world.copy();matrix.translation = origin
                                source.matrix_world = matrix
                        context.view_layer.update()
                        frame_asset(context, frame_objects, origin)
                    finally:
                        for source, matrix in virtual_matrices:
                            source.matrix_world = matrix
                    # Place the studio floor under the lowest view, using its root.
                    points, center, size = selected_bounds(context, frame_objects)
                    root = s.studio_scene_position
                    if root:
                        matrix = root.matrix_world.copy();matrix.translation.z = min(point.z for point in points)
                        root.matrix_world = matrix
                    s.studio_width = max(6, size.x * 2)
                    s.studio_height = max(4, size.z * 2)
                    studio.update_backdrop(s, context)
                yield .02 + .98 * done/max(1, expected), f'{ordinal+1}/{len(assets)} | Camera ready: {col.name}'
                for job in jobs:
                    if s.stop_requested:
                        self.stop_requested = True
                        return
                    s.current_collection, s.current_object = col.name, job['object']
                    s.last_output_path = job['output_path']
                    s.status = f'Rendering {job["object"]} / {job.get("view_mode") or job.get("texture_kind") or "Single"}'
                    outputs = [job['output_path']]
                    if s.freestyle_edges and s.freestyle_as_render_pass and not job.get('texture_kind'):
                        outputs += [job['freestyle_output_path'], job['freestyle_overlay_path']]
                    skip = s.skip_existing and not s.overwrite_existing and all(os.path.exists(path) for path in outputs)
                    if not skip:
                        render_asset_job(context, job, views, origin)
                    done += 1;s.queue_index = done;rq._sync_progress(s)
                    yield .02 + .98 * done/max(1, expected), f'Auto Render {done}/{expected} | {col.name}'
                rq._remove_multiview_objects([obj for group in views.values() for obj in group])
                all_views.clear()
                rq._set_asset_collection_enabled(col, False)
            completed = True
            s.status = f'Auto Render complete: {done} jobs / {len(assets)} assets'
        finally:
            rq._remove_multiview_objects(all_views)
            rq._restore_visibility(snapshot)
            s.is_running = False
            if not completed:
                s.status = f'Auto Render interrupted: {done} jobs completed'
            s.stop_requested = False
            rq._sync_progress(s)
