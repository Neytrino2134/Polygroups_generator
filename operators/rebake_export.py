"""Manual ReBake follow-up: select the current asset and export FBX plus one blend."""
from pathlib import Path
import re

import bpy

from .phase2_blend_export import (asset_collections, blend_file_stem, BLEND_FOLDER,
    COLLECTION_SUFFIX, export_selected_collection_blend)
from .rename_objects import ensure_collection_visible_in_view_layer


def rebake_asset_collection(context, target):
    candidates = [col for col in asset_collections(context.scene) if target.name in col.all_objects]
    if not candidates:
        candidates = [col for col in target.users_collection
                      if col in context.scene.collection.children_recursive]
    if len(candidates) != 1:
        raise ValueError('ReBake export needs one unambiguous asset collection for ' + target.name)
    return candidates[0]


def export_rebaked_asset(context, target, generated, collection, engine, report):
    p = context.scene.polygroups_model_preparation_settings
    s = context.scene.polygroups_mesh_finalization_settings
    meshes = set(generated)
    for obj in collection.all_objects:
        if obj.type != 'MESH':
            continue
        # Unity stores its LODs in separate per-level collections. Include the
        # newly generated set, without mixing an older other-engine LOD set.
        tagged_engine = obj.get('polygroups_rebake_lod_engine')
        if tagged_engine and tagged_engine != engine:
            continue
        if obj != target and engine == 'UNREAL' and obj.get('unity_prepared'):
            continue
        if obj != target and engine == 'UNITY' and re.fullmatch(r'SM_.+_LOD\d+', obj.name) and not obj.get('unity_prepared'):
            continue
        if not obj.get('polygroups_render_multiview') and not obj.get('polygroups_texture_plane'):
            meshes.add(obj)
    meshes.add(target)
    meshes = sorted(meshes, key=lambda obj: obj.name.casefold())
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in meshes:
        for owner in obj.users_collection:
            if owner in context.scene.collection.children_recursive:
                ensure_collection_visible_in_view_layer(context, owner)
        obj.hide_viewport = obj.hide_select = False
        obj.hide_set(False)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    context.view_layer.objects.active = target
    context.view_layer.update()
    fields = dict(phase2_export_engine='UNITY' if engine == 'UNITY' else 'FAB',
                  phase2_export_fbx=True, phase2_export_glb=False, phase2_export_gltf=False)
    saved = {name: (getattr(p, name), p.is_property_set(name)) for name in fields}
    autosave = s.unity_export_autosave, s.is_property_set('unity_export_autosave')
    try:
        for name, value in fields.items():
            setattr(p, name, value)
        # Do not save the working scene with temporary FBX-only overrides.
        s.unity_export_autosave = False
        if 'FINISHED' not in bpy.ops.object.polygroups_phase2_export('EXEC_DEFAULT', selected_only=True):
            raise RuntimeError(p.phase2_export_status)
    finally:
        for name, (value, was_set) in saved.items():
            setattr(p, name, value) if was_set else p.property_unset(name)
        if autosave[1]:
            s.unity_export_autosave = autosave[0]
        else:
            s.property_unset('unity_export_autosave')
    destination = Path(bpy.data.filepath).parent / BLEND_FOLDER / (blend_file_stem(collection) + '.blend')
    # One blend for the current asset, including Unity LODs generated into
    # separate collections, with the same pack/reset-Y options as Export Selected Blend.
    export_selected_collection_blend(collection, meshes, destination, p.phase2_blend_export_pack,
        reset_y=p.phase2_blend_export_reset_y and collection.name.endswith(COLLECTION_SUFFIX))
    p.phase2_blend_export_status = f'Exported {len(meshes)} selected meshes to {destination.name}'
    report({'INFO'}, f'ReBake Final Mesh: exported {len(meshes)} meshes to FBX and {destination.name}')
