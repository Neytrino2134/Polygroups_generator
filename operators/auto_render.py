"""Phase 2 asset-by-asset previews using the section 13 render operators."""
import json
import os
import re
import bpy
from mathutils import Vector
from . import render_queue as rq
from . import render_studio as studio
from .render_selected import fit_camera
from .render_textures import texture_planes, collection_textures
from .sequential_jobs import SequentialJob
from ..core.render_progress import RenderProgressPreview

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
    s.transparent_background = p.phase2_auto_transparent or p.phase2_auto_skip_scene
    s.scene_collection_prefix = p.phase2_auto_scene_prefix.strip() or 'Scene'
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
    try:
        result = bpy.ops.object.polygroups_scan_render_queue('EXEC_DEFAULT')
        if 'FINISHED' not in result:
            raise RuntimeError('Scan Queue failed')
        return [{**job, 'skip_scene_render': context.scene.polygroups_model_preparation_settings.phase2_auto_skip_scene
                 and not job.get('texture_kind')} for job in rq._load_queue(settings) if job['collection'] in names
                and (include_textures or not job.get('texture_kind'))]
    finally:
        settings.is_running = True


def render_asset_job(context, job, completed, total, preview, asset_label):
    """Run Start Render's preparation and backend, without refitting the camera."""
    settings = context.scene.polygroups_render_settings
    with rq.prepared_queue_job(context, settings, job):
        preview.show(completed, total, asset_label)
        # Leave the prepared objects visible for a UI frame before rendering.
        yield completed/max(1, total), f'Rendering {completed+1}/{total} | {asset_label}'
        if hasattr(preview, "render_steps"):
            yield from preview.render_steps(context, settings, job, completed, total)
        else:
            rq._render_current_job(context, settings, job)
        settings.queue_index = completed + 1
        rq._sync_progress(settings)
        preview.show(completed+1, total, asset_label)
        # Keep the scene visible between images, including the completion tick.
        yield (completed+1)/max(1, total), f'Auto Render {completed+1}/{total} | {asset_label}'


def silhouette_points(context, objects):
    """Actual evaluated geometry avoids empty corners of rotated mesh boxes."""
    depsgraph = context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if mesh is not None:
                points.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
        finally:
            evaluated.to_mesh_clear()
    return points


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
        self._preview = RenderProgressPreview(context)
        result = self.start_job(context, self.steps(context), modal=not bpy.app.background)
        if result == {'CANCELLED'}:
            self._preview.close()
        return result

    def finish_job(self, context, stopped=False, error=''):
        try:
            return super().finish_job(context, stopped=stopped, error=error)
        finally:
            if getattr(self, '_preview', None) is not None:
                self._preview.close()

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
            # Keep a working section-13 studio's tuned lights and settings.
            # Prepare Scene creates missing support and updates existing support.
            if 'FINISHED' not in bpy.ops.render.polygroups_prepare_studio('EXEC_DEFAULT'):
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
        freestyle_objects = []
        if s.freestyle_edges:
            freestyle_objects = [obj.name for col, sources in assets for obj in sources]
            rq._mark_freestyle_edges([obj for col, sources in assets for obj in sources], True)
        snapshot = rq._snapshot_visibility()
        done, history = 0, []
        completed = False
        try:
            s.is_running, s.stop_requested = True, False
            if p.phase2_auto_textures and p.phase2_auto_texture_prepare == 'ALL':
                prepare_textures(context, [col for col, sources in assets])
            # Exact expected count, including only available linked texture pairs.
            expected = sum(sum(2 if s.multiview_render_hero and
                (s.multiview_render or rq._prepared_multiview_views(source)) else 1 for source in sources)
                + int(p.phase2_auto_textures and collection_textures(col) is not None)
                for col, sources in assets)
            self._preview.total = expected
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
                # Use exactly Start Render's setup to measure the actual views.
                # No alternate copies, rotations, spacing or light placement.
                origin = sources[0].matrix_world.translation.copy()
                points = []
                for job in jobs:
                    if job.get('texture_kind') or job.get('view_mode') == 'Hero':
                        continue
                    with rq.prepared_queue_job(context, s, job) as objects:
                        source = bpy.data.objects[job['object']]
                        bounds = silhouette_points(context, objects)
                        offset = origin - source.matrix_world.translation
                        points.extend(point + offset for point in bounds)
                studio.position_studio_at_origin(context, origin)
                if p.phase2_auto_camera and points:
                    minimum = Vector(tuple(min(v[i] for v in points) for i in range(3)))
                    maximum = Vector(tuple(max(v[i] for v in points) for i in range(3)))
                    center = (minimum + maximum) * .5
                    fit_camera(context, context.scene.camera, points, center, maximum - minimum,
                               margin=.075, only_y=True)
                    context.view_layer.update()
                yield .02 + .98 * done/max(1, expected), f'{ordinal+1}/{len(assets)} | Camera ready: {col.name}'
                for job in jobs:
                    if s.stop_requested:
                        self.stop_requested = True
                        return
                    s.current_collection, s.current_object = col.name, job['object']
                    outputs = rq.job_output_paths(s, job)
                    s.last_output_path = outputs[0]
                    s.status = f'Rendering {job["object"]} / {job.get("view_mode") or job.get("texture_kind") or "Single"}'
                    skip = s.skip_existing and not s.overwrite_existing and all(os.path.exists(path) for path in outputs)
                    if not skip:
                        label = f'Asset {ordinal+1}/{len(assets)} | {col.name} | {job.get("view_mode") or job.get("texture_kind") or "Single"}'
                        yield from render_asset_job(context, job, done, expected, self._preview, label)
                    done += 1;s.queue_index = done;rq._sync_progress(s)
                    if skip:
                        self._preview.show(done, expected, f'Asset {ordinal+1}/{len(assets)} | Skipped existing')
                        yield done/max(1, expected), f'Auto Render {done}/{expected} | {col.name}'
                rq._set_asset_collection_enabled(col, False)
            completed = True
            s.status = f'Auto Render complete: {done} jobs / {len(assets)} assets'
        finally:
            rq._restore_visibility(snapshot)
            rq.clear_freestyle_after_render(s, freestyle_objects)
            if completed:
                studio.position_studio_at_origin(context, Vector((0, 0, 0)))
            s.is_running = False
            if not completed:
                s.status = f'Auto Render interrupted: {done} jobs completed'
            s.stop_requested = False
            rq._sync_progress(s)
