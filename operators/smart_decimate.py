import bpy
import re


SMART_DECIMATE_GROUP_NAME = "AI Retopo UV Seam Protect"
SMART_DECIMATE_MODIFIER_NAME = "Smart Decimate"
SEAMS_DECIMATE_MODIFIER_NAME = "Seams Decimate"
SMART_DECIMATE_DUPLICATE_SUFFIX = "_SmartDecimated"


def _clear_vertex_group(obj, group):
    vertex_indices = [vertex.index for vertex in obj.data.vertices]
    if not vertex_indices:
        return

    try:
        group.remove(vertex_indices)
    except RuntimeError:
        pass


def _select_seam_edges(obj):
    mesh = obj.data

    for vertex in mesh.vertices:
        vertex.select = False
    for edge in mesh.edges:
        edge.select = edge.use_seam
        if edge.use_seam:
            for vertex_index in edge.vertices:
                mesh.vertices[vertex_index].select = True
    for polygon in mesh.polygons:
        polygon.select = False

    mesh.update()


def _decimated_name(name):
    match = re.search(r"\.\d+$", name)
    if match:
        return f"{name[:match.start()]}{SMART_DECIMATE_DUPLICATE_SUFFIX}{match.group()}"
    return f"{name}{SMART_DECIMATE_DUPLICATE_SUFFIX}"


def _duplicate_mesh_object(context, obj):
    duplicate = obj.copy()
    duplicate.data = obj.data.copy()
    duplicate.animation_data_clear()
    duplicate["polygroups_smart_decimated"] = True
    duplicate.name = _decimated_name(obj.name)
    duplicate.data.name = _decimated_name(obj.data.name)

    for collection in obj.users_collection or (context.scene.collection,):
        collection.objects.link(duplicate)

    return duplicate


class OBJECT_OT_polygroups_smart_decimate(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_decimate"
    bl_label = "Smart Decimate"
    bl_description = "Decimate seam vertices and non-seam areas with separate ratios"
    bl_options = {"REGISTER", "UNDO"}

    triangle_limit: bpy.props.IntProperty(
        name="Triangle Limit",
        description="Automatically fit decimate ratios to this triangle budget; 0 uses manual ratios",
        default=0,
        min=0,
    )
    ratio: bpy.props.FloatProperty(
        name="Ratio",
        description="Decimate ratio for non-seam areas",
        default=0.4,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    seams_ratio: bpy.props.FloatProperty(
        name="Seams Decimate Ratio",
        description="Decimate ratio for seam vertices",
        default=0.9,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    duplicate_and_apply: bpy.props.BoolProperty(
        name="Duplicate And Apply Decimate",
        description="Duplicate the active object, add Smart Decimate to the duplicate, and apply it",
        default=False,
    )

    hide_source: bpy.props.BoolProperty(
        name="Hide LOW After Decimate", default=False,
        description="Disable the original LOW object in the viewport after successful decimation",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        source_obj = context.active_object
        original_mode = source_obj.mode

        context.view_layer.objects.active = source_obj
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        obj = _duplicate_mesh_object(context, source_obj) if self.duplicate_and_apply else source_obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj

        seam_edges = [edge for edge in obj.data.edges if edge.use_seam]
        if not seam_edges:
            if self.duplicate_and_apply:
                bpy.data.objects.remove(obj, do_unlink=True)
                context.view_layer.objects.active = source_obj
                source_obj.select_set(True)
            self.report({"WARNING"}, "Active mesh has no UV seam edges")
            return {"CANCELLED"}

        seam_vertex_indices = sorted(
            {
                vertex_index
                for edge in seam_edges
                for vertex_index in edge.vertices
            }
        )

        group = obj.vertex_groups.get(SMART_DECIMATE_GROUP_NAME)
        if group is None:
            group = obj.vertex_groups.new(name=SMART_DECIMATE_GROUP_NAME)
        else:
            _clear_vertex_group(obj, group)
        group.add(seam_vertex_indices, 1.0, "REPLACE")
        obj.vertex_groups.active_index = group.index

        seams_modifier = obj.modifiers.get(SEAMS_DECIMATE_MODIFIER_NAME)
        if seams_modifier is None or seams_modifier.type != "DECIMATE":
            seams_modifier = obj.modifiers.new(SEAMS_DECIMATE_MODIFIER_NAME, "DECIMATE")
        seams_modifier.decimate_type = "COLLAPSE"
        seams_modifier.ratio = self.seams_ratio
        seams_modifier.vertex_group = group.name
        seams_modifier.invert_vertex_group = False
        seams_modifier.vertex_group_factor = 1.0

        modifier = obj.modifiers.get(SMART_DECIMATE_MODIFIER_NAME)
        if modifier is None or modifier.type != "DECIMATE":
            modifier = obj.modifiers.new(SMART_DECIMATE_MODIFIER_NAME, "DECIMATE")

        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = self.ratio
        modifier.vertex_group = group.name
        modifier.invert_vertex_group = True
        modifier.vertex_group_factor = 1.0

        # Keep the seam pass before the non-seam pass, including on repeated runs.
        while obj.modifiers.find(seams_modifier.name) > obj.modifiers.find(modifier.name):
            bpy.ops.object.modifier_move_up(modifier=seams_modifier.name)

        _select_seam_edges(obj)

        budget_suffix = ""
        budget_unreached = False
        if self.triangle_limit > 0:
            from .smart_lods import _fit_ratios

            triangles, body_ratio, seam_ratio = _fit_ratios(
                obj, seams_modifier, modifier, self.triangle_limit,
                context.evaluated_depsgraph_get(),
            )
            budget_unreached = triangles > self.triangle_limit
            budget_suffix = (
                f", {triangles}/{self.triangle_limit} tris "
                f"(body {body_ratio:.3f}, seams {seam_ratio:.3f})"
            )
            if budget_unreached:
                budget_suffix += "; triangle limit could not be reached"

        applied_suffix = ""
        if self.duplicate_and_apply:
            try:
                bpy.ops.object.modifier_apply(modifier=seams_modifier.name)
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                applied_suffix = ", applied to duplicate"
            except RuntimeError as error:
                self.report({"WARNING"}, f"{obj.name}: {error}")

        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        self.report(
            {"WARNING"} if budget_unreached else {"INFO"},
            (
                f"Seams Decimate and Smart Decimate added: {len(seam_vertex_indices)} seam "
                f"vertex/vertices from {len(seam_edges)} seam edge(s){applied_suffix}{budget_suffix}"
            ),
        )
        if self.hide_source:
            source_obj.hide_viewport = True
        return {"FINISHED"}


def latest_generated_retopo(collection):
    """Choose the latest original Retopo, excluding LODs and decimated copies."""
    match = re.fullmatch(r"Generated\.(\d+)", collection.name)
    if match is None:
        return None
    candidates = []
    for obj in collection.all_objects:
        name = re.fullmatch(r"Retopo_(?:(\d+)_)?Highpoly_Generated\.(\d+)", obj.name)
        if obj.type == 'MESH' and name and int(name.group(2)) == int(match.group(1)):
            candidates.append((int(name.group(1) or 1), obj.name, obj))
    return max(candidates, key=lambda item: item[:2])[2] if candidates else None


def generated_retopo_targets(scene):
    pending = list(scene.collection.children)
    collections = set()
    while pending:
        collection = pending.pop()
        if collection not in collections:
            collections.add(collection)
            pending.extend(collection.children)
    return {obj for collection in collections
            if (obj := latest_generated_retopo(collection)) is not None}


class OBJECT_OT_polygroups_smart_decimate_all_generated(bpy.types.Operator):
    bl_idname = 'object.polygroups_smart_decimate_all_generated'
    bl_label = 'Smart Decimate All Generated'
    bl_description = 'Smart Decimate the highest numbered Retopo in each Generated.N collection using this section settings'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and not context.scene.polygroups_model_preparation_settings.batch_is_running)

    def execute(self, context):
        from .rename_objects import layer_collection_paths
        settings = context.scene.polygroups_mesh_finalization_settings
        targets = generated_retopo_targets(context.scene)
        if not targets:
            self.report({'WARNING'}, 'No matching Retopo meshes in Generated.N collections')
            return {'CANCELLED'}
        selected = list(context.selected_objects)
        active = context.view_layer.objects.active
        original_mode = active.mode if active else 'OBJECT'
        successful, failed = 0, []
        try:
            if active is not None and active.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for obj in sorted(targets, key=lambda item: item.name):
                layers, collection_flags = {}, {}
                pending_layers = [context.view_layer.layer_collection]
                while pending_layers:
                    layer = pending_layers.pop()
                    layers[layer] = (layer.exclude, layer.hide_viewport)
                    pending_layers.extend(reversed(list(layer.children)))
                reveal_layers = set()
                processed = False
                object_hidden = obj.hide_viewport, obj.hide_get()
                try:
                    for owner in obj.users_collection:
                        for path in layer_collection_paths(context.view_layer.layer_collection, owner):
                            for layer in path:
                                reveal_layers.add(layer)
                                collection_flags.setdefault(layer.collection, layer.collection.hide_viewport)
                    for layer in reveal_layers:
                        layer.exclude = False
                        layer.hide_viewport = False
                        layer.collection.hide_viewport = False
                    context.view_layer.update()
                    obj.hide_viewport = False
                    obj.hide_set(False)
                    for item in context.selected_objects:
                        item.select_set(False)
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
                    result = bpy.ops.object.polygroups_smart_decimate(
                        triangle_limit=settings.smart_decimate_triangle_limit,
                        ratio=settings.smart_decimate_ratio,
                        seams_ratio=settings.smart_decimate_seams_ratio,
                        duplicate_and_apply=settings.smart_decimate_duplicate_and_apply,
                        hide_source=settings.smart_decimate_hide_source,
                    )
                    if 'FINISHED' not in result:
                        raise RuntimeError('Smart Decimate cancelled; check UV seam edges')
                    processed = True
                    successful += 1
                except RuntimeError as error:
                    failed.append(f'{obj.name}: {error}')
                finally:
                    obj.hide_viewport = True if processed and settings.smart_decimate_hide_source else object_hidden[0]
                    hidden = object_hidden[1]
                    obj.hide_set(hidden)
                    for collection, hidden in collection_flags.items():
                        collection.hide_viewport = hidden
                    for layer, (excluded, hidden) in layers.items():
                        layer.hide_viewport = hidden
                        layer.exclude = excluded
                    context.view_layer.update()
        finally:
            for item in context.selected_objects:
                item.select_set(False)
            for item in selected:
                item.select_set(True)
            context.view_layer.objects.active = active
            if active is not None and original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)
        for message in failed:
            self.report({'WARNING'}, message)
        self.report({'INFO'}, f'Smart Decimate: {successful}/{len(targets)} Generated collections processed')
        return {'FINISHED'} if successful else {'CANCELLED'}


class OBJECT_OT_polygroups_delete_all_decimated(bpy.types.Operator):
    bl_idname = 'object.polygroups_delete_all_decimated'
    bl_label = 'Delete All Decimated'
    bl_description = 'Delete all SmartDecimated mesh copies and clean their unused mesh data'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.polygroups_model_preparation_settings.batch_is_running

    def execute(self, context):
        objects = [obj for obj in bpy.data.objects if obj.type == 'MESH'
                   and (obj.get('polygroups_smart_decimated') or SMART_DECIMATE_DUPLICATE_SUFFIX in obj.name)]
        if context.object is not None and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        meshes = {obj.data for obj in objects}
        count = len(objects)
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        self.report({'INFO'}, f'Deleted {count} SmartDecimated copies')
        return {'FINISHED'}


class OBJECT_OT_polygroups_show_all_low(bpy.types.Operator):
    bl_idname = 'object.polygroups_show_all_low'
    bl_label = 'Show All LOW'
    bl_description = 'Enable viewport display of the highest numbered original Retopo in each Generated.N collection'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.polygroups_model_preparation_settings.batch_is_running

    def execute(self, context):
        from .rename_objects import layer_collection_paths
        targets = generated_retopo_targets(context.scene)
        reveal = set()
        for obj in targets:
            for owner in obj.users_collection:
                for path in layer_collection_paths(context.view_layer.layer_collection, owner):
                    reveal.update(path)
        # Setting exclude on an ancestor also affects its descendants. Snapshot
        # the complete layer tree first and restore unrelated branches afterward.
        pending = [context.view_layer.layer_collection]
        layers = []
        while pending:
            layer = pending.pop()
            layers.append((layer, layer.exclude, layer.hide_viewport))
            pending.extend(reversed(list(layer.children)))
        for layer, excluded, hidden in layers:
            layer.exclude = False if layer in reveal else excluded
            layer.hide_viewport = False if layer in reveal else hidden
            if layer in reveal:
                layer.collection.hide_viewport = False
        context.view_layer.update()
        for obj in targets:
            obj.hide_viewport = False
            obj.hide_set(False)
        context.view_layer.update()
        self.report({'INFO'}, f'Showing {len(targets)} latest LOW meshes')
        return {'FINISHED'}
