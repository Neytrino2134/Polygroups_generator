"""Phase 2 sequential LOD generation and engine-specific asset preparation."""
import re
import bpy
from ..core.asset_names import asset_name
from ..core.lod_naming import lod_name
from .sequential_jobs import SequentialJob
from .smart_lods import OBJECT_OT_polygroups_generate_smart_lods, LOD_SOURCE, _world_x_bounds


class LODWorker:
    source_steps = OBJECT_OT_polygroups_generate_smart_lods.source_steps


def finalization_packs(context):
    from .phase2_processing import LOW, HIGH
    scene_objects = set(context.scene.objects)
    packs = []
    for col in bpy.data.collections:
        if not re.fullmatch(r'Generated(?:\.\d+)*', col.name, re.I):
            continue
        meshes = [obj for obj in col.all_objects if obj in scene_objects and obj.type == 'MESH'
                  and not HIGH.fullmatch(obj.name) and not obj.name.lower().startswith(('backup_retopo_', 'backup_resculpting_'))]
        lows = [(int(match.group(1)), obj) for obj in meshes if (match := LOW.fullmatch(obj.name))]
        if lows:
            packs.append((col, max(lows, key=lambda item: item[0])[1], meshes))
    if packs:
        def natural(item):
            return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', item[0].name)]
        return sorted(packs, key=natural)
    # Explicit selection also supports manually prepared collections.
    from .unreal_lod_rename import collection_packs, lod_order
    if not any(obj.type == 'MESH' for obj in context.selected_objects):
        raise ValueError('No Generated Retopo collections or selected mesh packs found')
    depsgraph = context.evaluated_depsgraph_get()
    for col, objects in collection_packs(context):
        meshes = list(objects)
        source = min(meshes, key=lambda obj: lod_order(obj, depsgraph))
        packs.append((col, source, meshes))
    return packs


def layer_tree(root):
    yield root
    for child in root.children:
        yield from layer_tree(child)


def remove_completed_generated(collection):
    """Remove an old Generated.N shell and its exclusive leftovers only."""
    if not re.fullmatch(r'Generated(?:\.\d+)+', collection.name, re.I):
        return
    # Prepared objects have already been moved to their final collections.
    # Shared objects and child collections remain linked wherever else used.
    for obj in list(collection.objects):
        if len(obj.users_collection) == 1:
            bpy.data.objects.remove(obj, do_unlink=True)
    for child in list(collection.children):
        # Keep child data reachable after removing the processing shell.
        for scene in bpy.data.scenes:
            if collection in scene.collection.children_recursive and child.name not in scene.collection.children:
                scene.collection.children.link(child)
    bpy.data.collections.remove(collection)


class OBJECT_OT_polygroups_batch_finalization(SequentialJob, bpy.types.Operator):
    bl_idname = 'object.polygroups_batch_finalization'
    bl_label = 'Batch Finalization'
    bl_description = 'Generate LODs and rename each Generated asset sequentially using Mesh Finalization settings'
    bl_options = {'REGISTER', 'UNDO'}
    phase2_job = True

    asset: bpy.props.StringProperty(name='Asset Name', default='Asset')
    name_index: bpy.props.StringProperty(name='Name Index', default='00')
    version_index: bpy.props.StringProperty(name='Version Index', default='01')

    @classmethod
    def poll(cls, context):
        from .phase2_processing import available
        return context.mode == 'OBJECT' and available(context)

    def invoke(self, context, event):
        s = context.scene.polygroups_mesh_finalization_settings
        p = context.scene.polygroups_model_preparation_settings
        unity = p.phase2_final_rename_engine == 'UNITY'
        self.asset = s.unity_asset_name if unity else s.unreal_lod_asset_name
        self.name_index = s.unity_name_index if unity else s.unreal_lod_name_index
        self.version_index = s.unity_asset_index if unity else s.unreal_lod_version_index
        from .asset_translation import bind_dialog
        self._translation_dialog = bind_dialog(self)
        return context.window_manager.invoke_props_dialog(self, width=400, confirm_text='Start')

    def draw(self, context):
        from .asset_translation import draw_asset_name
        draw_asset_name(self.layout, context, self, 'asset', dialog=getattr(self, '_translation_dialog', ''))
        for key in ('name_index', 'version_index'):
            self.layout.prop(self, key)
        self.layout.label(text='Preview: ' + asset_name(self.asset))

    def cancel(self, context):
        from .asset_translation import release_dialog
        release_dialog(getattr(self, '_translation_dialog', ''))

    def execute(self, context):
        self.cancel(context)
        self.asset = asset_name(self.asset)
        if not self.asset or not self.name_index.isdigit() or not self.version_index.isdigit():
            self.report({'ERROR'}, 'Enter an asset name and numeric indices')
            return {'CANCELLED'}
        return self.start_job(context, self.steps(context), modal=not bpy.app.background)

    def steps(self, context):
        from .phase2_processing import LOW
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_mesh_finalization_settings
        if not p.phase2_final_lods and not p.phase2_final_rename:
            raise ValueError('Enable Prepare LODs or Rename')
        packs = finalization_packs(context)
        if len({source for col, source, meshes in packs}) != len(packs):
            raise ValueError('A source mesh belongs to multiple Generated collections')
        if p.phase2_final_lods:
            for col, source, meshes in packs:
                for index in range(s.smart_lods_count):
                    name = lod_name(source.name, index, p.phase2_final_lod_engine)
                    if bpy.data.objects.get(name):
                        raise ValueError('LOD already exists: ' + name)
        names = ('smart_lods_prepare_mode', 'unreal_lod_asset_name', 'unreal_lod_name_index',
            'unreal_lod_version_index', 'unity_asset_name', 'unity_name_index', 'unity_asset_index')
        saved = {name: getattr(s, name) for name in names}
        selected, active = list(context.selected_objects), context.active_object
        layers = [(layer, layer.exclude, layer.hide_viewport) for layer in layer_tree(context.view_layer.layer_collection)]
        collections = [(col, col.hide_viewport, col.hide_render) for col in bpy.data.collections]
        visibility = [(source, source.hide_viewport, source.hide_render, source.hide_select, source.hide_get())
            for col, source, meshes in packs]
        worker = LODWorker()
        worker.report = self.report
        completed_collections = []
        try:
            # Reveal source collection paths, including previously completed Phase 2 items.
            def reveal(layer):
                needed = any(source.name in layer.collection.all_objects for col, source, meshes in packs)
                if needed:
                    layer.exclude = layer.hide_viewport = False
                    layer.collection.hide_viewport = layer.collection.hide_render = False
                for child in layer.children:
                    reveal(child)
            reveal(context.view_layer.layer_collection)
            context.view_layer.update()
            for col, source, meshes in packs:
                source.hide_viewport = source.hide_render = source.hide_select = False
                source.hide_set(False)
            sources = [source for col, source, meshes in packs]
            if p.phase2_final_lods and s.smart_lods_auto_arrange and s.smart_lods_smart_arrange:
                from ..core.smart_arrange import SmartArrangeGrid
                worker._smart_grid = SmartArrangeGrid(context, sources, s.smart_lods_spacing)
                worker._smart_grid.arrange_sources(context)
            elif p.phase2_final_lods and s.smart_lods_auto_arrange:
                from .batch_import import arrange_objects_zx
                arrange_objects_zx(sources, mode='GRID', rows=len(sources), plane='XY', spacing=.1,
                    secondary_spacing=s.smart_lods_spacing, alignment='ORIGIN', preserve_order=True)
            worker._lod_x_step = max((_world_x_bounds(obj)[1]-_world_x_bounds(obj)[0] for obj in sources), default=0)+.1
            yield .02, f'Arrange completed | {len(packs)} assets'
            for ordinal, (col, source, meshes) in enumerate(packs):
                bpy.ops.object.select_all(action='DESELECT')
                source.select_set(True)
                context.view_layer.objects.active = source
                s.smart_lods_prepare_mode = p.phase2_final_lod_engine
                if p.phase2_final_lods:
                    for done in worker.source_steps(context):
                        yield .02 + .98 * (ordinal + .8 * done/s.smart_lods_count)/len(packs), f'{ordinal+1}/{len(packs)} | {source.name} | LOD{done-1}'
                    generated = [bpy.data.objects[lod_name(source.name, i, s.smart_lods_prepare_mode)]
                                 for i in range(s.smart_lods_count)]
                else:
                    generated = [obj for obj in meshes if not LOW.fullmatch(obj.name)]
                    if not generated:
                        generated = list(meshes)
                if p.phase2_final_rename:
                    version = str(int(self.version_index) + ordinal).zfill(max(2, len(self.version_index)))
                    fab = p.phase2_final_rename_engine == 'FAB'
                    targets = list(generated)
                    if fab and p.phase2_final_lods and s.unreal_lod_keep_high:
                        targets.insert(0, source)
                    bpy.ops.object.select_all(action='DESELECT')
                    for obj in targets:
                        obj.hide_viewport = obj.hide_render = obj.hide_select = False
                        obj.hide_set(False)
                        obj.select_set(True)
                    context.view_layer.objects.active = targets[0]
                    if fab:
                        s.unreal_lod_asset_name = self.asset
                        s.unreal_lod_name_index = self.name_index
                        s.unreal_lod_version_index = version
                        result = bpy.ops.object.polygroups_unreal_lod_rename('EXEC_DEFAULT')
                    else:
                        s.unity_asset_name = self.asset
                        s.unity_name_index = self.name_index
                        s.unity_asset_index = version
                        result = bpy.ops.object.polygroups_prepare_unity('EXEC_DEFAULT', auto_lods=True)
                    if 'FINISHED' not in result:
                        raise RuntimeError(f'Rename failed for asset {ordinal+1}')
                    for obj in generated:
                        obj[LOD_SOURCE] = source.name
                    completed_collections.append(col)
                yield .02 + .98*(ordinal+1)/len(packs), f'{ordinal+1}/{len(packs)} assets completed'
        finally:
            for name, value in saved.items():
                setattr(s, name, value)
            # Retain the user's entered identity as the next dialog default.
            if p.phase2_final_rename_engine == 'FAB':
                s.unreal_lod_asset_name, s.unreal_lod_name_index, s.unreal_lod_version_index = self.asset, self.name_index, self.version_index
            else:
                s.unity_asset_name, s.unity_name_index, s.unity_asset_index = self.asset, self.name_index, self.version_index
            bpy.ops.object.select_all(action='DESELECT')
            for obj, viewport, render, lock, hidden in visibility:
                obj.hide_viewport, obj.hide_render, obj.hide_select = viewport, render, lock
                if obj.name in context.view_layer.objects:
                    obj.hide_set(hidden)
            for col, viewport, render in collections:
                col.hide_viewport, col.hide_render = viewport, render
            for layer, excluded, hidden in layers:
                layer.exclude, layer.hide_viewport = excluded, hidden
            context.view_layer.update()
            for obj in selected:
                if obj.name in context.view_layer.objects:
                    obj.select_set(True)
            if active and active.name in context.view_layer.objects:
                context.view_layer.objects.active = active
            if p.phase2_final_cleanup_generated:
                for collection in completed_collections:
                    remove_completed_generated(collection)
