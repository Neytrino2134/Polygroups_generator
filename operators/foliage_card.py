"""Foliage Cards: generate low-poly alpha cards from a volumetric leaf highpoly (07 Resculpting)."""
import json
import os
import time

import bpy
import numpy as np

from ..core import foliage_card as core
from .smart_decimate import _decimated_name

CARD_SOURCE_PROP = "polygroups_foliage_card_source"
CARD_FRAME_PROP = "polygroups_foliage_card_frame"
ALPHA_NODE = "Foliage Card AlphaMap"
CARD_SUFFIX = "_Card"
INTERIOR_GROUP = "Foliage Card Interior"


def _build_mesh(name, world, tris, uvs, matrix_world):
    local = core.to_local(world, matrix_world)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(local.tolist(), [], tris.tolist())
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    loop_vertices = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loop_vertices)
    uv_layer.data.foreach_set("uv", uvs[loop_vertices].astype(np.float32).ravel())
    edge_index = {edge.key: edge.index for edge in mesh.edges}
    face_count = np.zeros(len(mesh.edges), dtype=np.int64)
    for polygon in mesh.polygons:
        for key in polygon.edge_keys:
            face_count[edge_index[key]] += 1
    seams = (face_count == 1)
    mesh.edges.foreach_set("use_seam", seams)
    mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=bool))
    mesh.update()
    return mesh, seams


def _boundary_vertices(mesh, seams):
    verts = set()
    for edge, is_boundary in zip(mesh.edges, seams):
        if is_boundary:
            verts.update(edge.vertices)
    return verts


def _apply_interior_shrinkwrap(context, obj, source, seams, offset):
    """Shrinkwrap only interior vertices: boundary stays on the conservative outline."""
    boundary = _boundary_vertices(obj.data, seams)
    interior = [v.index for v in obj.data.vertices if v.index not in boundary]
    if not interior:
        return
    group = obj.vertex_groups.new(name=INTERIOR_GROUP)
    group.add(interior, 1.0, "REPLACE")
    modifier = obj.modifiers.new("Foliage Card Shrinkwrap", "SHRINKWRAP")
    modifier.target = source
    modifier.wrap_method = "NEAREST_SURFACEPOINT"
    modifier.wrap_mode = "ABOVE_SURFACE"
    modifier.offset = offset
    modifier.vertex_group = group.name
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(evaluated)
    old_mesh = obj.data
    obj.modifiers.remove(modifier)
    obj.data = new_mesh
    new_mesh.name = old_mesh.name
    bpy.data.meshes.remove(old_mesh)
    group = obj.vertex_groups.get(INTERIOR_GROUP)
    if group is not None:
        obj.vertex_groups.remove(group)


def _store_mask(name, mask):
    image = bpy.data.images.get(name)
    h, w = mask.shape
    if image is None or tuple(image.size) != (w, h):
        if image is not None:
            bpy.data.images.remove(image)
        image = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    pixels = np.repeat(mask.astype(np.float32).ravel(), 4)
    pixels[3::4] = 1.0
    image.pixels.foreach_set(pixels)
    image.update()
    return image


def _card_settings(settings):
    return dict(
        axis=settings.foliage_card_axis,
        side=settings.foliage_card_side,
        margin=settings.foliage_card_margin,
        resolution=int(settings.foliage_card_resolution),
        gap_close_px=settings.foliage_card_gap_close,
        min_island_area=settings.foliage_card_min_island,
        cut_holes=settings.foliage_card_cut_holes,
        min_hole_area=settings.foliage_card_min_hole,
        padding_px=settings.foliage_card_padding,
        triangle_limit=settings.foliage_card_triangle_limit,
        outline_tolerance=settings.foliage_card_outline_tolerance,
        depth_tolerance=settings.foliage_card_depth_tolerance,
        depth_smoothing=settings.foliage_card_depth_smoothing,
        surface_offset=settings.foliage_card_offset,
        depth_mode=settings.foliage_card_depth_mode,
    )


def bake_alpha_map(context, card, source, resolution):
    """Ray-cast the highpoly silhouette over the card's stored frame: UV space 1:1, exact holes."""
    frame = core.frame_from_dict(json.loads(card[CARD_FRAME_PROP]))
    # Prepare And Bake may disable the highpoly afterwards; it must be evaluated for the BVH.
    hidden = source.hide_viewport, source.hide_get()
    source.hide_viewport = False
    source.hide_set(False)
    try:
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        mask, _depth = core.raycast_frame(source.evaluated_get(depsgraph), depsgraph, frame, resolution)
    finally:
        source.hide_viewport = hidden[0]
        source.hide_set(hidden[1])

    base_name = card.get("polygroups_bake_base_color_image")
    base_image = bpy.data.images.get(base_name) if base_name else None
    name = base_image.name.replace("BaseColor", "AlphaMap") if base_image and "BaseColor" in base_image.name \
        else f"{card.name}_AlphaMap"
    image = bpy.data.images.get(name)
    if image is not None and tuple(image.size) != (resolution, resolution):
        bpy.data.images.remove(image)
        image = None
    if image is None:
        image = bpy.data.images.new(name, resolution, resolution, alpha=False)
    image.colorspace_settings.name = "Non-Color"
    pixels = np.repeat(mask.astype(np.float32).ravel(), 4)
    pixels[3::4] = 1.0
    image.pixels.foreach_set(pixels)
    image.update()
    if base_image is not None and base_image.filepath_raw:
        base_path = bpy.path.abspath(base_image.filepath_raw)
        folder, filename = os.path.split(base_path)
        filename = filename.replace("BaseColor", "AlphaMap") if "BaseColor" in filename else f"{name}.png"
        image.filepath_raw = os.path.join(folder, filename)
        image.file_format = "PNG"
        image.save()
    card["polygroups_foliage_card_alpha_image"] = image.name

    material = card.active_material
    if material is not None and material.node_tree is not None:
        nodes, links = material.node_tree.nodes, material.node_tree.links
        bsdf = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
        node = nodes.get(ALPHA_NODE) or nodes.new("ShaderNodeTexImage")
        node.name = node.label = ALPHA_NODE
        node.image = image
        node.location = (-560, -560)
        if bsdf is not None:
            links.new(node.outputs["Color"], bsdf.inputs["Alpha"])
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
    return image, float(mask.mean())


def bake_card(context, card, source, settings, report):
    """Selected (highpoly) to active (card) through the addon's Prepare And Bake, then AlphaMap."""
    bake = context.scene.polygroups_baking_settings
    saved = (bake.auto_pack_uv_before_bake, bake.bake_resolution)
    bpy.ops.object.select_all(action="DESELECT")
    source.hide_viewport = False
    source.hide_set(False)
    source.select_set(True)
    card.select_set(True)
    context.view_layer.objects.active = card
    try:
        bake.auto_pack_uv_before_bake = settings.foliage_card_pack_islands
        bake.bake_resolution = settings.foliage_card_bake_resolution
        result = bpy.ops.object.polygroups_prepare_and_bake()
    except RuntimeError as error:
        report({"WARNING"}, f"Foliage card bake failed: {error}")
        return False
    finally:
        bake.auto_pack_uv_before_bake, bake.bake_resolution = saved
    if "FINISHED" not in result:
        return False
    if settings.foliage_card_alpha_map:
        if settings.foliage_card_pack_islands:
            report({"WARNING"}, "AlphaMap skipped: packed UVs no longer match the projection frame")
        elif card.get(CARD_FRAME_PROP):
            bake_alpha_map(context, card, source, settings.foliage_card_bake_resolution)
    return True


class OBJECT_OT_polygroups_generate_foliage_card(bpy.types.Operator):
    bl_idname = "object.polygroups_generate_foliage_card"
    bl_label = "Generate Foliage Card"
    bl_description = ("Build a low-poly alpha card from the active highpoly leaf: ray-cast silhouette, "
                      "simplified outline with seams, depth-following triangles, front-view UVs")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and not obj.get(CARD_SOURCE_PROP)

    def execute(self, context):
        settings = context.scene.polygroups_resculpting_settings
        source = context.active_object
        if source.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        started = time.perf_counter()
        depsgraph = context.evaluated_depsgraph_get()
        try:
            result = core.build_card(source.evaluated_get(depsgraph), depsgraph,
                                     camera=context.scene.camera, **_card_settings(settings))
        except core.CardError as error:
            self.report({"WARNING"}, f"{source.name}: {error}")
            return {"CANCELLED"}
        if not result["components"]:
            self.report({"WARNING"}, f"{source.name}: no card geometry produced")
            return {"CANCELLED"}

        parts = result["components"]
        if settings.foliage_card_islands == "JOIN":
            worlds, tris_all, uvs_all, offset = [], [], [], 0
            for world, tris, uvs in parts:
                worlds.append(world)
                tris_all.append(tris + offset)
                uvs_all.append(uvs)
                offset += len(world)
            parts = [(np.vstack(worlds), np.vstack(tris_all), np.vstack(uvs_all))]

        # Regenerating replaces every card made from this source.
        for old in [o for o in bpy.data.objects if o.get(CARD_SOURCE_PROP) == source.name]:
            old_mesh = old.data
            bpy.data.objects.remove(old, do_unlink=True)
            if old_mesh is not None and old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
        collection = source.users_collection[0] if source.users_collection else context.scene.collection
        frame_json = json.dumps(core.frame_to_dict(result["frame"]))
        cards = []
        for index, (world, tris, uvs) in enumerate(parts):
            # Keep the trailing .NNN last: Generated.N collections enforce it on bake.
            suffix = CARD_SUFFIX + (f"_{index + 1:02d}" if len(parts) > 1 else "")
            name = _decimated_name(source.name, suffix)
            mesh, seams = _build_mesh(name, world, tris, uvs, source.matrix_world)
            card = bpy.data.objects.new(name, mesh)
            card.matrix_world = source.matrix_world.copy()
            card[CARD_SOURCE_PROP] = source.name
            card[CARD_FRAME_PROP] = frame_json
            collection.objects.link(card)
            if settings.foliage_card_depth_mode == "SHRINKWRAP":
                _apply_interior_shrinkwrap(context, card, source, seams, settings.foliage_card_offset)
            cards.append(card)

        if settings.foliage_card_keep_mask:
            _store_mask(f"{source.name}_CardMask", result["hit"])

        bpy.ops.object.select_all(action="DESELECT")
        for card in cards:
            card.select_set(True)
        context.view_layer.objects.active = cards[0]

        stats = result["stats"]
        message = (f"Foliage Card: {stats['triangles']} tris, {stats['islands']} island(s), "
                   f"outline {stats['tolerance_px']:.2f}px, uncovered {stats['uncovered_fraction'] * 100:.2f}%, "
                   f"{time.perf_counter() - started:.1f}s")
        limit = settings.foliage_card_triangle_limit
        over = limit > 0 and stats["triangles"] > limit
        if over:
            message += f"; over the {limit} budget"
        settings.foliage_card_status = message

        if settings.foliage_card_auto_bake:
            if len(cards) > 1:
                self.report({"WARNING"}, "Auto Bake runs only for One Object cards; bake each card manually")
            elif not bake_card(context, cards[0], source, settings, self.report):
                self.report({"WARNING"}, message + "; bake did not finish")
                return {"FINISHED"}
        if settings.foliage_card_hide_source:
            source.hide_set(True)
        self.report({"WARNING"} if over else {"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_bake_foliage_card(bpy.types.Operator):
    bl_idname = "object.polygroups_bake_foliage_card"
    bl_label = "Bake Foliage Card"
    bl_description = "Bake the active foliage card from the highpoly it was generated from"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and bool(obj.get(CARD_SOURCE_PROP))

    def execute(self, context):
        card = context.active_object
        source = bpy.data.objects.get(card[CARD_SOURCE_PROP])
        if source is None or source.type != "MESH":
            self.report({"WARNING"}, f"Source highpoly '{card[CARD_SOURCE_PROP]}' not found")
            return {"CANCELLED"}
        settings = context.scene.polygroups_resculpting_settings
        if not bake_card(context, card, source, settings, self.report):
            return {"CANCELLED"}
        if settings.foliage_card_hide_source:
            source.hide_set(True)
        self.report({"INFO"}, f"{card.name}: baked from {source.name}")
        return {"FINISHED"}
