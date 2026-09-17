"""Reusable studio rig and live cyclorama geometry."""
import math
import bpy

TAG = 'polygroups_studio_role'
CAMERA_POSITION = (0, -8, 0.5)
AIM_POSITION = (0, 0, 0.5)
LIGHT_DEFAULTS = (
    ('key', 'Key', (-2, -3, 3), 50, 2),
    ('fill', 'Fill', (2, -2, 1.8), 50, 2.5),
    ('rim', 'Rim', (0, 2, 2.8), 100, 1.5),
)


# Scene-linear RGB palettes, ordered as Key, Fill, Rim.
LIGHT_COLOR_PRESETS = {
    'NEUTRAL': ((1, 1, 1), (1, 1, 1), (1, 1, 1)),
    'WARM_COOL': ((1, 0.63, 0.35), (1, 0.82, 0.65), (0.35, 0.65, 1)),
    'COOL_WARM': ((0.45, 0.72, 1), (0.7, 0.85, 1), (1, 0.5, 0.2)),
    'SUNSET': ((1, 0.4, 0.16), (1, 0.65, 0.4), (1, 0.22, 0.38)),
    'CYAN_MAGENTA': ((0.16, 0.85, 1), (0.5, 0.8, 1), (1, 0.15, 0.55)),
    'GOLD_VIOLET': ((1, 0.7, 0.25), (1, 0.85, 0.6), (0.55, 0.25, 1)),
}


def update_backdrop(settings, context):
    obj = settings.studio_backdrop
    if obj is None or obj.type != 'MESH' or obj.get(TAG) != 'backdrop':
        return
    width = settings.studio_width
    radius = min(settings.studio_radius, settings.studio_height, settings.studio_depth + settings.studio_distance)
    back = settings.studio_distance
    profile = [(-settings.studio_depth, 0)]
    for index in range(33):
        angle = -math.pi / 2 + (math.pi / 2) * index / 32
        profile.append((back - radius + radius * math.cos(angle),
                        radius + radius * math.sin(angle)))
    profile.append((back, settings.studio_height))
    profile = [point for index, point in enumerate(profile)
               if index == 0 or math.dist(point, profile[index - 1]) > 1e-8]
    vertices = [(x, y, z) for y, z in profile for x in (-width / 2, width / 2)]
    faces = [(2*i, 2*i+1, 2*i+3, 2*i+2) for i in range(len(profile)-1)]
    mesh = obj.data
    mesh.clear_geometry()
    mesh.from_pydata(vertices, [], faces)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.update()
    material = mesh.materials[0] if mesh.materials else None
    if material is not None:
        material.diffuse_color = (*settings.studio_color, 1)
        bsdf = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None) if material.use_nodes and material.node_tree else None
        if bsdf:
            bsdf.inputs['Base Color'].default_value = (*settings.studio_color, 1)
            bsdf.inputs['Roughness'].default_value = 0.75


def studio_collection(scene, role):
    name = {'scene': 'Scene_Studio', 'camera': 'Camera_Studio', 'light': 'Light_Studio'}[role]
    collection = next((item for item in scene.collection.children if item.get(TAG) == role), None)
    if collection is None:
        collection = bpy.data.collections.new(name)
        collection[TAG] = role
        scene.collection.children.link(collection)
    collection.color_tag = scene.polygroups_render_settings.studio_collection_color_tag
    return collection


def update_studio_color_tag(settings, context):
    scene = settings.id_data
    for collection in scene.collection.children:
        if collection.get(TAG) in ('scene', 'camera', 'light'):
            collection.color_tag = settings.studio_collection_color_tag


def _layer_rows(layer, path=()):
    path = path + (layer.collection,)
    yield layer, path
    for child in layer.children:
        yield from _layer_rows(child, path)


def studio_collections_first(context):
    scene = context.scene
    original = list(scene.collection.children)
    studio = [collection for role in ('scene', 'camera', 'light')
              for collection in original if collection.get(TAG) == role]
    ordered = studio + [collection for collection in original if collection not in studio]
    if original == ordered:
        return
    # Relinking roots reorders CollectionChildren but recreates view-layer bases.
    # Preserve per-layer exclusions, viewport hiding, selection and active IDs.
    states = []
    active_obj = context.object
    mode = active_obj.mode if active_obj else 'OBJECT'
    if mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for view_layer in scene.view_layers:
        states.append((view_layer,
                       {path: (layer.exclude, layer.hide_viewport, layer == view_layer.active_layer_collection)
                        for layer, path in _layer_rows(view_layer.layer_collection)},
                       [(obj, obj.hide_get(view_layer=view_layer), obj.select_get(view_layer=view_layer))
                        for obj in view_layer.objects], view_layer.objects.active))
    try:
        for collection in original:
            scene.collection.children.unlink(collection)
        for collection in ordered:
            scene.collection.children.link(collection)
    finally:
        for view_layer, layers, objects, active in states:
            view_layer.update()
            for layer, path in _layer_rows(view_layer.layer_collection):
                if path in layers:
                    excluded, hidden, was_active = layers[path]
                    layer.exclude = excluded
                    layer.hide_viewport = hidden
                    if was_active:
                        view_layer.active_layer_collection = layer
            view_layer.update()
            for obj, hidden, selected in objects:
                if obj.name in view_layer.objects:
                    obj.hide_set(hidden, view_layer=view_layer)
                    obj.select_set(selected, view_layer=view_layer)
            if active is not None and active.name in view_layer.objects:
                view_layer.objects.active = active
        if mode != 'OBJECT' and active_obj.name in context.view_layer.objects:
            bpy.ops.object.mode_set(mode=mode)


def arrange_studio_outliners(context):
    if bpy.app.background:
        return
    scene = context.scene
    depth = max((len(path) for _layer, path in _layer_rows(context.view_layer.layer_collection)), default=1)
    for window in context.window_manager.windows:
        if window.scene != scene:
            continue
        for area in window.screen.areas:
            if area.type != 'OUTLINER' or area.spaces.active.display_mode != 'VIEW_LAYER':
                continue
            # Alphabetic sorting would override the collection insertion order.
            area.spaces.active.use_sort_alpha = False
            region = next((region for region in area.regions if region.type == 'WINDOW'), None)
            if region is None:
                continue
            try:
                with context.temp_override(window=window, area=area, region=region):
                    if bpy.ops.outliner.show_one_level.poll():
                        for _ in range(depth + 8):
                            bpy.ops.outliner.show_one_level(open=False)
                        bpy.ops.outliner.show_one_level(open=True)
            except RuntimeError:
                pass
            area.tag_redraw()


def ensure_object(settings, scene, property_name, role, name, kind, collection, location):
    obj = getattr(settings, property_name)
    if obj is None or obj.get(TAG) != role or obj.type != kind:
        data = None
        if kind == 'CAMERA':
            data = bpy.data.cameras.new(name)
            data.lens = 85
            data.clip_start = 0.01
            data.clip_end = 200
        elif kind == 'LIGHT':
            data = bpy.data.lights.new(name, 'AREA')
        elif kind == 'MESH':
            data = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, data)
        obj[TAG] = role
        obj.location = location
        if kind == 'EMPTY':
            obj.empty_display_type = 'SPHERE'
            obj.empty_display_size = 0.1
        setattr(settings, property_name, obj)
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    for path in _collection_paths(scene, collection):
        path.exclude = False
        path.hide_viewport = False
    collection.hide_viewport = False
    collection.hide_render = False
    return obj


def _collection_paths(scene, collection):
    for layer in scene.view_layers:
        pending = [layer.layer_collection]
        while pending:
            item = pending.pop()
            if item.collection == collection:
                yield item
            pending.extend(item.children)


def aim_constraint(obj, target):
    constraint = obj.constraints.get('Studio Aim')
    if constraint is not None and constraint.type != 'TRACK_TO':
        obj.constraints.remove(constraint)
        constraint = None
    if constraint is None:
        constraint = obj.constraints.new('TRACK_TO')
        constraint.name = 'Studio Aim'
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'


def prepare_studio(context, scope='ALL'):
    scene = context.scene
    previous_roots = set(scene.collection.children)
    settings = scene.polygroups_render_settings
    if scope in ('ALL', 'SCENE'):
        collection = studio_collection(scene, 'scene')
        backdrop = ensure_object(settings, scene, 'studio_backdrop', 'backdrop', 'Studio Backdrop',
                                 'MESH', collection, (0, 0, 0))
        if not backdrop.data.materials:
            material = bpy.data.materials.new('Studio Background')
            material.use_nodes = True
            backdrop.data.materials.append(material)
        update_backdrop(settings, context)
    if scope in ('ALL', 'CAMERA'):
        collection = studio_collection(scene, 'camera')
        camera = ensure_object(settings, scene, 'studio_camera', 'camera', 'Studio Camera',
                               'CAMERA', collection, CAMERA_POSITION)
        target = ensure_object(settings, scene, 'studio_camera_aim', 'camera_aim', 'Studio Camera Aim',
                               'EMPTY', collection, AIM_POSITION)
        aim_constraint(camera, target)
        scene.camera = camera
    for role, label, position, energy, size in LIGHT_DEFAULTS:
        if scope not in ('ALL', 'LIGHTS', role.upper()):
            continue
        collection = studio_collection(scene, 'light')
        previous = getattr(settings, 'studio_' + role)
        light = ensure_object(settings, scene, 'studio_' + role, role, 'Studio ' + label,
                              'LIGHT', collection, position)
        if light != previous:
            light.data.energy = energy
            light.data.shape = 'DISK'
            light.data.size = size
        target = ensure_object(settings, scene, 'studio_' + role + '_aim', role + '_aim',
                               'Studio ' + label + ' Aim', 'EMPTY', collection, AIM_POSITION)
        aim_constraint(light, target)
    context.view_layer.update()
    studio_collections_first(context)
    if any(collection not in previous_roots for collection in scene.collection.children):
        arrange_studio_outliners(context)


def reset_transform(obj, position):
    obj.parent = None
    obj.location = position
    obj.rotation_mode = 'XYZ'
    obj.rotation_euler = (0, 0, 0)
    obj.scale = (1, 1, 1)
    obj.delta_location = (0, 0, 0)
    obj.delta_rotation_euler = (0, 0, 0)
    obj.delta_rotation_quaternion = (1, 0, 0, 0)
    obj.delta_scale = (1, 1, 1)
    obj.hide_viewport = False
    obj.hide_render = False
    obj.hide_set(False)
    constraint = obj.constraints.get('Studio Aim')
    if constraint:
        constraint.influence = 1
        constraint.mute = False


def reset_studio(context, scope):
    prepare_studio(context, scope)
    settings = context.scene.polygroups_render_settings
    if scope == 'ALL':
        settings.property_unset('studio_move_step')
        settings.property_unset('studio_collection_color_tag')
        update_studio_color_tag(settings, context)
    if scope in ('ALL', 'CAMERA'):
        reset_transform(settings.studio_camera, CAMERA_POSITION)
        reset_transform(settings.studio_camera_aim, AIM_POSITION)
        camera = settings.studio_camera.data
        camera.type = 'PERSP'
        camera.lens = 85
        camera.ortho_scale = 6
        camera.clip_start = 0.01
        camera.clip_end = 200
    for role, _label, position, energy, size in LIGHT_DEFAULTS:
        if scope not in ('ALL', 'LIGHTS', role.upper()):
            continue
        light = getattr(settings, 'studio_' + role)
        reset_transform(light, position)
        reset_transform(getattr(settings, 'studio_' + role + '_aim'), AIM_POSITION)
        light.data.type = 'AREA'
        light.data.shape = 'DISK'
        light.data.energy = energy
        light.data.color = (1, 1, 1)
        light.data.size = size
    if scope in ('ALL', 'SCENE'):
        for prop in ('color', 'width', 'depth', 'height', 'distance', 'radius'):
            settings.property_unset('studio_' + prop)
        reset_transform(settings.studio_backdrop, (0, 0, 0))
        update_backdrop(settings, context)
    context.view_layer.update()


class RENDER_OT_polygroups_prepare_studio(bpy.types.Operator):
    bl_idname = 'render.polygroups_prepare_studio'
    bl_label = 'Prepare Scene'
    bl_description = 'Create a curved backdrop, three-point lighting, camera and aim controls'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        prepare_studio(context)
        return {'FINISHED'}


class RENDER_OT_polygroups_move_studio(bpy.types.Operator):
    bl_idname = 'render.polygroups_move_studio'
    bl_label = 'Move Studio Control'
    bl_description = 'Move along the selected world axis by the shared movement step'
    bl_options = {'REGISTER', 'UNDO'}

    target: bpy.props.EnumProperty(items=[(role, role.replace('_', ' ').title(), '') for role in (
        'camera', 'camera_aim', 'key', 'key_aim', 'fill', 'fill_aim', 'rim', 'rim_aim')])
    axis: bpy.props.EnumProperty(items=[(axis, axis, '') for axis in ('X', 'Y', 'Z')])
    direction: bpy.props.EnumProperty(items=[('NEGATIVE', 'Decrease', ''), ('POSITIVE', 'Increase', '')])

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        obj = getattr(settings, 'studio_' + self.target)
        if obj is None or (self.target in ('camera', 'camera_aim') and self.axis == 'X'):
            return {'CANCELLED'}
        scale = context.scene.unit_settings.scale_length
        delta = settings.studio_move_step / scale * (-1 if self.direction == 'NEGATIVE' else 1)
        matrix = obj.matrix_world.copy()
        matrix.translation['XYZ'.index(self.axis)] += delta
        obj.matrix_world = matrix
        context.view_layer.update()
        return {'FINISHED'}


class RENDER_OT_polygroups_reset_studio(bpy.types.Operator):
    bl_idname = 'render.polygroups_reset_studio'
    bl_label = 'Reset Studio Defaults'
    bl_description = 'Restore default positions, Aim points and settings for the selected studio section'
    bl_options = {'REGISTER', 'UNDO'}

    scope: bpy.props.EnumProperty(items=[
        ('ALL', 'Entire Studio', ''), ('CAMERA', 'Camera', ''),
        ('LIGHTS', 'All Lights', ''), ('SCENE', 'Backdrop', ''),
        ('KEY', 'Key Light', ''), ('FILL', 'Fill Light', ''), ('RIM', 'Rim Light', ''),
    ], default='ALL')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        reset_studio(context, self.scope)
        return {'FINISHED'}


class RENDER_OT_polygroups_studio_light_colors(bpy.types.Operator):
    bl_idname = 'render.polygroups_studio_light_colors'
    bl_label = 'Apply Light Color Preset'
    bl_description = 'Apply colors to Key, Fill and Rim without changing their power or position'
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.EnumProperty(items=[(key, key.replace('_', ' ').title(), '')
                                         for key in LIGHT_COLOR_PRESETS])

    @classmethod
    def poll(cls, context):
        if context.scene is None:
            return False
        settings = context.scene.polygroups_render_settings
        return not settings.is_running and all(
            obj is not None and obj.type == 'LIGHT'
            for obj in (settings.studio_key, settings.studio_fill, settings.studio_rim))

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        for role, color in zip(('key', 'fill', 'rim'), LIGHT_COLOR_PRESETS[self.preset]):
            getattr(settings, 'studio_' + role).data.color = color
        return {'FINISHED'}


class RENDER_OT_polygroups_delete_studio_scenes(bpy.types.Operator):
    bl_idname = 'render.polygroups_delete_studio_scenes'
    bl_label = 'Delete All Scenes'
    bl_description = 'Delete all Scene_, Camera_ and Light_ collections and their nested hierarchy; objects also linked outside this hierarchy are preserved'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        pending = [collection for collection in bpy.data.collections
                   if collection.name.startswith(('Scene_', 'Camera_', 'Light_'))]
        collections = set()
        while pending:
            collection = pending.pop()
            if collection not in collections:
                collections.add(collection)
                pending.extend(collection.children)
        objects = {obj for collection in collections for obj in collection.objects}
        removed_objects = 0
        orphan_candidates = set()
        for obj in objects:
            if all(owner in collections for owner in obj.users_collection):
                if obj.type in ('MESH', 'CAMERA', 'LIGHT'):
                    orphan_candidates.add((obj.type, obj.data))
                bpy.data.objects.remove(obj, do_unlink=True)
                removed_objects += 1
        count = len(collections)
        for collection in collections:
            bpy.data.collections.remove(collection, do_unlink=True)
        for kind, data in orphan_candidates:
            if data.users == 0:
                getattr(bpy.data, {'MESH': 'meshes', 'CAMERA': 'cameras', 'LIGHT': 'lights'}[kind]).remove(data)
        context.view_layer.update()
        self.report({'INFO'}, f'Deleted {count} scene collections and {removed_objects} objects')
        return {'FINISHED'}
