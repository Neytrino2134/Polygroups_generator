"""Final, complete mesh statistics and existing FAB Media refresh after ReLOD."""
import os
import tempfile
from pathlib import Path

import bpy


def gallery_document(context):
    from ..services import fab_media as media
    settings = context.scene.airetopo_fab_media_settings
    if settings.is_generating:
        raise ValueError('Wait for FAB JSON generation to finish')
    path = (Path(bpy.path.abspath(settings.saved_filepath)) if settings.saved_filepath
            else Path(bpy.data.filepath).parent / 'texflow-fab-media.json')
    if settings.result_text:
        return media.validate(settings.result_text.as_string()), path
    if path.is_file():
        return media.validate(path.read_text(encoding='utf-8')), path
    return None, path


def validate_json_update(context):
    if not bpy.data.filepath:
        raise ValueError('ReLOD JSON: save the working blend file first')
    gallery_document(context)


def update_json(context, plans):
    from ..core.lod_naming import lod_base
    from ..services import fab_media as media
    from .mesh_export import _evaluated_mesh_counts, _write_export_mesh_info, _safe_path_token
    from .unreal_lod_export import lod_identity
    from .smart_lods import LOD_INDEX
    root = Path(bpy.data.filepath).parent / '!Unreal'
    meshes = {obj for plan in plans for obj in [plan.source, *plan.generated]}
    families = {lod_base(plan.source.name, 'UNREAL').casefold() for plan in plans}
    meshes.update(obj for obj in context.scene.objects if obj.type == 'MESH'
                  and obj.name.upper().endswith(('_MID', '_HIGH'))
                  and lod_base(obj.name, 'UNREAL').casefold() in families)
    document, gallery_path = gallery_document(context)
    generated = {obj: (lod_identity(plan.source, 'Unreal')[0], 'LOD', obj[LOD_INDEX])
                 for plan in plans for obj in plan.generated}
    entries = []
    with media._evaluation_visibility(context):
        graph = context.evaluated_depsgraph_get()
        for obj in sorted(meshes, key=lambda item: media.natural(item.name)):
            base, role, index = generated[obj] if obj in generated else lod_identity(obj, 'Unreal')
            vertices, triangles = _evaluated_mesh_counts(obj, graph)
            entry = dict(name=obj.name, asset=base, role=role, lod_index=index,
                lod=f'LOD{index}' if role == 'LOD' else 'HIGH', vertices=vertices, triangles=triangles,
                collections=[collection.name for collection in obj.users_collection], files={})
            format_first = context.scene.polygroups_model_preparation_settings.phase2_export_sort == 'LODS_FORMAT'
            folder = root / 'FBX' if format_first else root / _safe_path_token(base) / 'FBX'
            path = folder / (_safe_path_token(obj.name) + '.fbx')
            if path.is_file():
                entry['file'] = entry['files']['FBX'] = path.relative_to(root).as_posix()
            entries.append(entry)
    if document is not None:
        measured = media.measured_fields(media.inventory(context))
        document['fields'].update(measured)
        gallery_content = media.dumps(document)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.relod-json-', dir=root) as temporary:
        _write_export_mesh_info(temporary, 'JSON', entries, 'Unreal')
        os.replace(Path(temporary) / 'MeshInfo.json', root / 'MeshInfo.json')
    if document is not None:
        gallery_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.relod-json-', dir=gallery_path.parent) as temporary:
            staged = Path(temporary) / gallery_path.name
            staged.write_text(gallery_content, encoding='utf-8')
            os.replace(staged, gallery_path)
        settings = context.scene.airetopo_fab_media_settings
        if settings.result_text is None:
            settings.result_text = bpy.data.texts.new('FAB Media JSON')
        settings.result_text.clear()
        settings.result_text.write(gallery_content)
        settings.saved_filepath = str(gallery_path)
        for key in measured:
            setattr(settings, key, document['fields'][key])
        settings.last_status = 'Updated after ReLOD'
