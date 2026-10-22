"""Generate sequential triangle-budget LODs with two weighted Decimate passes."""

import bpy
import bmesh
import re
from ..core.lod_naming import lod_base, lod_name, lod_index
from mathutils import Vector
from ..core.mesh_fold_repair import repair_local_folds

from .smart_decimate import (
    SEAMS_DECIMATE_MODIFIER_NAME,
    SMART_DECIMATE_GROUP_NAME,
    SMART_DECIMATE_MODIFIER_NAME,
)


def _triangle_count(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return len(mesh.loop_triangles)
    finally:
        evaluated.to_mesh_clear()


def _clean_zero_area_lod(obj):
    """Clean the generated datablock only, after all topology modifiers."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)

        def zero_triangles():
            return [tri for tri in bm.calc_loop_triangles() if
                    (tri[1].vert.co - tri[0].vert.co).cross(
                        tri[2].vert.co - tri[0].vert.co).length == 0.0]

        detected = len(zero_triangles())
        if not detected:
            return 0
        # Preserve seam/pin flags and all surviving corner UVs where a safe
        # exact-vertex contraction can remove the degenerate triangles.
        repair_local_folds(bm, fix_folds=False, fix_degenerate=False, fix_zero_area=True)
        # Collinear triangles with three distinct endpoints cannot be welded.
        # Tessellate only affected n-gons, preserving the other polygons.
        ngons = {tri[0].face for tri in zero_triangles() if len(tri[0].face.verts) > 3}
        if ngons:
            bmesh.ops.triangulate(bm, faces=list(ngons))
        faces = {tri[0].face for tri in zero_triangles()}
        if faces:
            bmesh.ops.delete(bm, geom=list(faces), context='FACES')
        if zero_triangles():
            raise ValueError('Zero-area triangles remain after LOD cleanup')
        bm.to_mesh(obj.data)
        obj.data.update()
        return detected
    finally:
        bm.free()


def _configure_pass(obj):
    indices = sorted({index for edge in obj.data.edges if edge.use_seam for index in edge.vertices})
    group = obj.vertex_groups.get(SMART_DECIMATE_GROUP_NAME)
    if group is not None:
        obj.vertex_groups.remove(group)
    if indices:
        group = obj.vertex_groups.new(name=SMART_DECIMATE_GROUP_NAME)
        group.add(indices, 1.0, "REPLACE")
        seam_mod = obj.modifiers.new(SEAMS_DECIMATE_MODIFIER_NAME, "DECIMATE")
        seam_mod.decimate_type = "COLLAPSE"
        seam_mod.vertex_group = group.name
        seam_mod.vertex_group_factor = 1.0
    else:
        seam_mod = None
    body_mod = obj.modifiers.new(SMART_DECIMATE_MODIFIER_NAME, "DECIMATE")
    body_mod.decimate_type = "COLLAPSE"
    if indices:
        body_mod.vertex_group = group.name
        body_mod.invert_vertex_group = True
        body_mod.vertex_group_factor = 1.0
    return seam_mod, body_mod


def _fit_ratios(obj, seam_mod, body_mod, target, depsgraph):
    """Fit the budget, or return the smallest mesh Blender can produce."""
    def measure(body, seam):
        body_mod.ratio = body
        if seam_mod is not None:
            seam_mod.ratio = seam
        obj.update_tag(refresh={'OBJECT', 'DATA', 'TIME'})
        depsgraph.update()
        return _triangle_count(obj, depsgraph)

    original = measure(1.0, 1.0)
    if original <= target:
        return original, 1.0, 1.0

    # For each 10% reduction of the main pass, reduce seams by only 2%.
    low, high = 0.0, 1.0
    best = None
    for _ in range(20):
        body = (low + high) / 2
        seam = 0.8 + 0.2 * body if seam_mod is not None else 1.0
        tris = measure(body, seam)
        if tris <= target:
            best = (tris, body, seam)
            low = body
        else:
            high = body
    if best is None:
        tris = measure(0.0, 0.8 if seam_mod is not None else 1.0)
        if tris <= target:
            best = (tris, 0.0, 0.8 if seam_mod is not None else 1.0)

    if best is None and seam_mod is not None:
        # The main pass is exhausted; allow stronger seam reduction if needed.
        low, high = 0.0, 0.8
        for _ in range(20):
            seam = (low + high) / 2
            tris = measure(0.0, seam)
            if tris <= target:
                best = (tris, 0.0, seam)
                low = seam
            else:
                high = seam
        if best is None:
            tris = measure(0.0, 0.0)
            if tris <= target:
                best = (tris, 0.0, 0.0)

    if best is None:
        best = (measure(0.0, 0.0), 0.0, 0.0)
    tris, body, seam = best
    measure(body, seam)
    return tris, body, seam


def _fit_final_decimate(obj, target, depsgraph):
    """Fit an unrestricted final pass; leave it at its minimum if still above budget."""
    modifier = obj.modifiers.new("Final Decimate", "DECIMATE")
    modifier.decimate_type = "COLLAPSE"

    def measure(ratio):
        modifier.ratio = ratio
        obj.update_tag(refresh={'OBJECT', 'DATA', 'TIME'})
        depsgraph.update()
        return _triangle_count(obj, depsgraph)

    low_count = measure(0.0)
    if low_count > target:
        return modifier, low_count, 0.0

    low, high = 0.0, 1.0
    best = (low_count, 0.0)
    for _ in range(20):
        ratio = (low + high) / 2
        tris = measure(ratio)
        if tris <= target:
            best = (tris, ratio)
            low = ratio
        else:
            high = ratio
    tris, ratio = best
    measure(ratio)
    return modifier, tris, ratio


def _copy_into_source_collections(source, name, context):
    duplicate = source.copy()
    duplicate.data = source.data.copy()
    duplicate.animation_data_clear()
    duplicate.name = name
    duplicate.data.name = name
    for collection in source.users_collection or (context.scene.collection,):
        collection.objects.link(duplicate)
    context.view_layer.objects.active = duplicate
    bpy.ops.object.select_all(action="DESELECT")
    duplicate.select_set(True)
    return duplicate


def _world_x_bounds(obj):
    if not obj.data.vertices:
        x = obj.matrix_world.translation.x
        return x, x
    values = [(obj.matrix_world @ Vector(corner)).x for corner in obj.bound_box]
    return min(values), max(values)


def _arrange_after_previous(context, obj, previous, spacing, alignment='BOUNDS'):
    context.view_layer.update()
    if alignment == 'ORIGIN':
        transform = obj.matrix_world.copy()
        transform.translation = previous.matrix_world.translation + Vector((spacing, 0, 0))
        obj.matrix_world = transform
        context.view_layer.update()
        return
    previous_max = _world_x_bounds(previous)[1]
    current_min = _world_x_bounds(obj)[0]
    shift = max(0.0, previous_max + spacing - current_min)
    transform = obj.matrix_world.copy()
    transform.translation.x += shift
    obj.matrix_world = transform
    context.view_layer.update()



LOD_SOURCE = "polygroups_lod_source"
LOD_INDEX = "polygroups_lod_index"
LOD_LABEL = "polygroups_lod_label"


def ensure_lod_label(context, lod, source_name, index, label_tag=LOD_LABEL, text_size=None):
    label = next((obj for obj in bpy.data.objects if obj.type == 'FONT' and (obj.get(label_tag) == lod.name or (obj.get(label_tag) and obj.parent == lod))), None)
    if label is None:
        curve = bpy.data.curves.new(lod.name + "_Label", 'FONT')
        label = bpy.data.objects.new(lod.name + "_Label", curve)
        for collection in lod.users_collection:
            collection.objects.link(label)
        label[label_tag] = lod.name
        label.parent = lod
        material = next((m for m in bpy.data.materials if m.get('polygroups_lod_label_material')), None)
        if material is None:
            material = bpy.data.materials.new('Smart LOD Label')
            material['polygroups_lod_label_material'] = True
            material.use_nodes = True
            material.node_tree.nodes.clear()
            output = material.node_tree.nodes.new('ShaderNodeOutputMaterial')
            emission = material.node_tree.nodes.new('ShaderNodeEmission')
            emission.inputs['Color'].default_value = (1, 1, 1, 1)
            material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
        curve.materials.append(material)
    label[label_tag] = lod.name
    for collection in lod.users_collection:
        if label.name not in collection.objects:
            collection.objects.link(label)
    for collection in list(label.users_collection):
        if collection not in lod.users_collection:
            collection.objects.unlink(label)
    tris = _triangle_count(lod, context.evaluated_depsgraph_get())
    label.data.body = f"{source_name} | LOD {index}\n{tris:,} tris"
    label.data.align_x = 'CENTER'
    label.data.align_y = 'BOTTOM_BASELINE'
    label.data.size = text_size if text_size is not None else context.scene.polygroups_mesh_finalization_settings.smart_lods_text_size
    corners = [lod.matrix_world @ Vector(c) for c in lod.bound_box]
    minimum = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    maximum = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    from math import radians
    from mathutils import Matrix
    matrix = Matrix.Rotation(radians(90), 4, 'X')
    matrix.translation = Vector(((minimum.x + maximum.x) / 2, minimum.y - .02, maximum.z + .1))
    label.matrix_world = matrix
    label.hide_render = False
    label.hide_viewport = False
    context.view_layer.update()
    width = max(maximum.x - minimum.x, .1)
    if label.dimensions.x > width:
        label.data.size *= width / label.dimensions.x
    context.view_layer.update()
    return label


class OBJECT_OT_polygroups_render_smart_lods(bpy.types.Operator):
    bl_idname = "object.polygroups_render_smart_lods"
    bl_label = "Auto Frame & Render LODs"
    bl_description = "Render generated LODs and labels with automatic framing and optional Freestyle"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.scene.camera is not None and not context.scene.polygroups_render_settings.is_running

    def execute(self, context):
        import re
        settings = context.scene.polygroups_mesh_finalization_settings
        render_settings = context.scene.polygroups_render_settings
        active = context.active_object
        source_name = active.get(LOD_SOURCE) or lod_base(active.name, settings.smart_lods_prepare_mode)
        if any(obj.type == 'MESH' and obj.get(LOD_SOURCE) == active.name for obj in context.scene.objects):
            source_name = active.name
        lods = sorted((obj for obj in context.scene.objects if obj.type == 'MESH' and (
            obj.get(LOD_SOURCE) == source_name or lod_base(obj.name, settings.smart_lods_prepare_mode) == lod_base(source_name, settings.smart_lods_prepare_mode) and re.search(r"[._]LOD[._]?\d+$", obj.name))),
            key=lod_index)
        if not lods:
            self.report({'ERROR'}, "No generated LODs for the active mesh")
            return {'CANCELLED'}
        selected = list(context.selected_objects)
        mode = active.mode
        freestyle = (render_settings.freestyle_edges, render_settings.freestyle_as_render_pass)
        visibility = [(obj, obj.hide_viewport, obj.hide_render, obj.hide_get()) for obj in lods]
        resolution = (render_settings.resolution_x, render_settings.resolution_y, render_settings.resolution_scale)
        try:
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            render_mode = settings.smart_lods_render_mode
            targets = lods if render_mode != 'SELECTED' else [lod for lod in lods if lod.select_get()]
            if not targets:
                self.report({'ERROR'}, "Select at least one generated LOD")
                return {'CANCELLED'}
            if settings.smart_lods_render_freestyle:
                render_settings.freestyle_edges = True
            render_settings.freestyle_as_render_pass = False
            if render_mode in {'ALL', 'INDIVIDUAL'}:
                # Auto Frame retains this longest side and adapts the other
                # dimension to the objects' proportions.
                render_settings.resolution_x = render_settings.resolution_y = 2048 if render_mode == 'INDIVIDUAL' else 4096
                render_settings.resolution_scale = 100
            import os
            from .render_queue import _current_state_render_path, image_extension
            from .mesh_export import _safe_path_token
            seed_path = _current_state_render_path()
            directory = os.path.join(os.path.dirname(seed_path), 'Render LODS')
            os.makedirs(directory, exist_ok=True)
            stamp = os.path.splitext(os.path.basename(seed_path))[0]
            batches = [[lod] for lod in targets] if render_mode == 'INDIVIDUAL' else [targets]
            for batch in batches:
                for obj in context.selected_objects:
                    obj.select_set(False)
                for lod in batch:
                    lod.hide_set(False)
                    lod.hide_viewport = False
                    lod.select_set(True)
                    if settings.smart_lods_render_text:
                        index = lod_index(lod)
                        ensure_lod_label(context, lod, source_name, index).select_set(True)
                context.view_layer.objects.active = batch[0]
                suffix = f"LOD_{lod_index(batch[0]):02d}" if render_mode == 'INDIVIDUAL' else 'All_LODs'
                filepath = os.path.join(directory, f"{_safe_path_token(source_name)}_{suffix}_{stamp}{image_extension(render_settings.image_format)}")
                result = bpy.ops.object.polygroups_render_selected_auto(output_path=filepath)
                if 'FINISHED' not in result:
                    return {'CANCELLED'}
            return {'FINISHED'}
        finally:
            for obj, viewport, render, hidden in visibility:
                obj.hide_viewport = viewport
                obj.hide_render = render
                obj.hide_set(hidden)
            render_settings.resolution_x, render_settings.resolution_y, render_settings.resolution_scale = resolution
            render_settings.freestyle_edges, render_settings.freestyle_as_render_pass = freestyle
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in selected:
                obj.select_set(True)
            context.view_layer.objects.active = active
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=mode)

class OBJECT_OT_polygroups_generate_smart_lods(bpy.types.Operator):
    bl_idname = "object.polygroups_generate_smart_lods"
    bl_label = "Generate Smart LODs"
    bl_description = "Generate a separate sequential LOD set for each selected mesh using the configured triangle limits"
    bl_options = {"REGISTER", "UNDO"}

    active_only: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'},
        description='Generate only from the active mesh for the combined preparation workflow')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        active = context.active_object
        selected = tuple(context.selected_objects)
        mode = active.mode
        sources = [active] if self.active_only else sorted(
            (obj for obj in selected if obj.type == 'MESH'), key=lambda obj: obj.name.casefold())
        if not sources:
            sources = [active]
        settings = context.scene.polygroups_mesh_finalization_settings
        # Validate every source before creating anything: one colliding pack
        # must not leave an accidental partial batch on an ordinary rerun.
        planned_names = [lod_name(source.name, index, settings.smart_lods_prepare_mode)
                         for source in sources for index in range(settings.smart_lods_count)]
        if len(set(planned_names)) != len(planned_names):
            self.report({'WARNING'}, 'Select one source mesh per asset LOD pack')
            return {'CANCELLED'}
        collisions = [name for name in planned_names if bpy.data.objects.get(name)]
        if settings.smart_lods_prepare_mode == 'UNITY':
            collisions.extend(obj.name for source in sources for obj in bpy.data.objects
                              if re.fullmatch(re.escape(source.name) + r'\.LOD\.\d+', obj.name))
        if collisions:
            self.report({'WARNING'}, 'Smart LODs already exist: ' + ', '.join(collisions))
            return {'CANCELLED'}
        completed = 0
        try:
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for source in sources:
                bpy.ops.object.select_all(action='DESELECT')
                source.select_set(True)
                context.view_layer.objects.active = source
                if self._generate_for_source(context) != {'FINISHED'}:
                    break
                completed += 1
            if completed and settings.smart_lods_auto_arrange:
                from .batch_import import arrange_objects_zx
                objects = [obj for source in sources[:completed]
                           for obj in [source] + [bpy.data.objects[lod_name(source.name, i, settings.smart_lods_prepare_mode)]
                                                 for i in range(settings.smart_lods_count)]]
                arrange_objects_zx(objects, spacing=0.1, mode='GRID', rows=completed,
                                   plane='XY', alignment='ORIGIN',
                                   secondary_spacing=settings.smart_lods_spacing, preserve_order=True)
                context.view_layer.update()
        finally:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in selected:
                if obj.name in context.view_layer.objects:
                    obj.select_set(True)
            context.view_layer.objects.active = active
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=mode)
        if completed:
            self.report({'INFO'}, f'Generated Smart LOD packs: {completed}/{len(sources)}')
        return {'FINISHED'} if completed else {'CANCELLED'}

    def _generate_for_source(self, context):
        source = context.active_object
        original_mode = source.mode
        selected = tuple(context.selected_objects)
        settings = context.scene.polygroups_mesh_finalization_settings
        targets = [getattr(settings, f"smart_lods_target_{i}") for i in range(1, settings.smart_lods_count + 1)]
        existing = [
            lod_name(source.name, index, settings.smart_lods_prepare_mode)
            for index in range(len(targets))
            if lod_name(source.name, index, settings.smart_lods_prepare_mode) in bpy.data.objects
        ]
        if existing:
            self.report({"WARNING"}, f"Smart LODs already exist: {', '.join(existing)}")
            return {"CANCELLED"}
        generated = []
        over_budget = []
        success = False
        try:
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            previous = source
            for index, target in enumerate(targets):
                lod = _copy_into_source_collections(previous, lod_name(source.name, index, settings.smart_lods_prepare_mode), context)
                generated.append(lod)
                lod[LOD_SOURCE] = source.name
                lod[LOD_INDEX] = index
                # Bake inherited modifiers before fitting so each new LOD starts
                # from the actual mesh produced by the previous stage.
                for modifier in tuple(lod.modifiers):
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
                seam_mod, body_mod = _configure_pass(lod)
                depsgraph = context.evaluated_depsgraph_get()
                tris, body, seam = _fit_ratios(lod, seam_mod, body_mod, target, depsgraph)
                final_mod = None
                final_ratio = None
                if tris > target and settings.smart_lods_final_decimate:
                    final_mod, tris, final_ratio = _fit_final_decimate(lod, target, depsgraph)
                if seam_mod is not None:
                    bpy.ops.object.modifier_apply(modifier=seam_mod.name)
                bpy.ops.object.modifier_apply(modifier=body_mod.name)
                if final_mod is not None:
                    bpy.ops.object.modifier_apply(modifier=final_mod.name)
                if settings.smart_lods_triangulate_all:
                    triangulate = lod.modifiers.new("LOD Triangulate", "TRIANGULATE")
                    bpy.ops.object.modifier_apply(modifier=triangulate.name)
                if settings.smart_lods_remove_zero_area:
                    removed = _clean_zero_area_lod(lod)
                    if removed:
                        self.report({'INFO'}, f'LOD{index}: removed {removed} zero-area triangles')
                actual = _triangle_count(lod, context.evaluated_depsgraph_get())
                if actual > target:
                    over_budget.append(f"LOD{index}: {actual}/{target} tris")
                else:
                    suffix = f", final {final_ratio:.3f}" if final_ratio is not None else ""
                    self.report({"INFO"}, f"LOD{index}: {actual}/{target} tris (body {body:.3f}, seams {seam:.3f}{suffix})")
                if settings.smart_lods_create_text:
                    ensure_lod_label(context, lod, source.name, index)
                previous = lod
            success = True
            if over_budget:
                self.report({"WARNING"}, "Smart LODs generated; limits not reached: " + "; ".join(over_budget))
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, f"Smart LODs: {error}")
        finally:
            if not success:
                for lod in reversed(generated):
                    for label in list(bpy.data.objects):
                        if label.get(LOD_LABEL) == lod.name:
                            curve = label.data
                            bpy.data.objects.remove(label, do_unlink=True)
                            if curve.users == 0:
                                bpy.data.curves.remove(curve)
                    mesh = lod.data
                    bpy.data.objects.remove(lod, do_unlink=True)
                    if mesh.users == 0:
                        bpy.data.meshes.remove(mesh)
            bpy.ops.object.select_all(action="DESELECT")
            for obj in selected:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            context.view_layer.objects.active = source
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=original_mode)
        return {"FINISHED"} if success else {"CANCELLED"}


class OBJECT_OT_polygroups_smart_lods_prepare(bpy.types.Operator):
    bl_idname = "object.polygroups_smart_lods_prepare"
    bl_label = "Smart LODs + Prepare Assets"
    bl_description = "Generate LODs, then prepare only generated meshes for Unity or Unreal"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        source = context.active_object
        engine = settings.smart_lods_prepare_mode
        copy_textures = (settings.unity_copy_textures if engine == 'UNITY' else
                         settings.unreal_lod_prepare_materials and settings.unreal_lod_copy_textures)
        if copy_textures and not bpy.data.filepath:
            self.report({'ERROR'}, 'Save the blend file before copying textures')
            return {'CANCELLED'}
        if engine == 'UNITY' and not settings.unity_name_index.isdigit():
            self.report({'ERROR'}, 'Name Index must be numeric')
            return {'CANCELLED'}
        identity = re.fullmatch(r'SM_(.+)_(\d+)_(\d+)', lod_base(source.name, 'UNREAL'))
        if engine == 'UNREAL' and identity is None:
            from .mesh_export import _safe_path_token
            asset = settings.unreal_lod_asset_name.strip()
            if (not asset or _safe_path_token(asset) != asset
                    or not settings.unreal_lod_name_index.isdigit()
                    or not settings.unreal_lod_version_index.isdigit()):
                self.report({'ERROR'}, 'Enter a valid Unreal asset name and numeric indices')
                return {'CANCELLED'}
        before = set(bpy.data.objects)
        result = bpy.ops.object.polygroups_generate_smart_lods(active_only=True)
        if 'FINISHED' not in result:
            return {'CANCELLED'}
        lods = sorted((obj for obj in bpy.data.objects if obj not in before and obj.type == 'MESH'
                       and obj.get(LOD_SOURCE) == source.name), key=lambda obj: obj.get(LOD_INDEX, 0))
        if not lods:
            return {'CANCELLED'}
        bpy.ops.object.select_all(action='DESELECT')
        for obj in lods:
            obj.select_set(True)
        context.view_layer.objects.active = lods[0]
        if settings.smart_lods_prepare_mode == 'UNITY':
            result = bpy.ops.object.polygroups_prepare_unity(auto_lods=True)
        else:
            names = ('unreal_lod_asset_name', 'unreal_lod_name_index',
                     'unreal_lod_version_index', 'unreal_lod_keep_high')
            saved = {name: getattr(settings, name) for name in names}
            try:
                # Re-preparing an already named asset keeps its identity.
                if identity:
                    settings.unreal_lod_asset_name = identity.group(1)
                    settings.unreal_lod_name_index = identity.group(2)
                    settings.unreal_lod_version_index = identity.group(3)
                settings.unreal_lod_keep_high = False
                result = bpy.ops.object.polygroups_unreal_lod_rename('EXEC_DEFAULT')
            finally:
                for name, value in saved.items():
                    setattr(settings, name, value)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in lods:
            obj.select_set(True)
        context.view_layer.objects.active = lods[0]
        return result
