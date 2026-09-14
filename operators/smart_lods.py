"""Generate sequential triangle-budget LODs with two weighted Decimate passes."""

import bpy

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


class OBJECT_OT_polygroups_generate_smart_lods(bpy.types.Operator):
    bl_idname = "object.polygroups_generate_smart_lods"
    bl_label = "Generate Smart LODs"
    bl_description = "Generate sequential LOD meshes within triangle limits using gentle seam decimation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        source = context.active_object
        original_mode = source.mode
        selected = tuple(context.selected_objects)
        settings = context.scene.polygroups_mesh_finalization_settings
        targets = [getattr(settings, f"smart_lods_target_{i}") for i in range(1, settings.smart_lods_count + 1)]
        existing = [
            f"{source.name}.LOD.{index}"
            for index in range(1, len(targets) + 1)
            if f"{source.name}.LOD.{index}" in bpy.data.objects
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
            for index, target in enumerate(targets, 1):
                lod = _copy_into_source_collections(previous, f"{source.name}.LOD.{index}", context)
                generated.append(lod)
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
                actual = _triangle_count(lod, context.evaluated_depsgraph_get())
                if actual > target:
                    over_budget.append(f"LOD.{index}: {actual}/{target} tris")
                else:
                    suffix = f", final {final_ratio:.3f}" if final_ratio is not None else ""
                    self.report({"INFO"}, f"LOD.{index}: {actual}/{target} tris (body {body:.3f}, seams {seam:.3f}{suffix})")
                previous = lod
            success = True
            if over_budget:
                self.report({"WARNING"}, "Smart LODs generated; limits not reached: " + "; ".join(over_budget))
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, f"Smart LODs: {error}")
        finally:
            if not success:
                for lod in reversed(generated):
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
