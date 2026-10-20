"""Export independent Unreal LOD assets with multiple file formats."""
from contextlib import ExitStack
from pathlib import Path
import re
import bpy
from .mesh_export import (
    _selected_mesh_objects, _export_root_directory, _safe_path_token,
    _copy_export_textures, _detach_export_alpha_maps, _restore_export_alpha_maps,
    _export_at_world_origin, _export_selected_object, _export_gltf_asset,
    _evaluated_mesh_counts, _write_export_mesh_info, enabled_mesh_export_formats,
)


def lod_identity(obj):
    match = re.fullmatch(r'SM_(.+)_LOD(\d+)', obj.name, re.IGNORECASE)
    if match:
        return match[1], 'LOD', int(match[2])
    base = obj.get('unreal_lod_asset')
    if base and obj.get('unreal_lod_index') == -1:
        return base, 'HIGH', None
    match = re.fullmatch(r'SM_(.+)_High', obj.name, re.IGNORECASE)
    if match:
        return match[1], 'HIGH', None
    raise ValueError(f'Use Unreal LOD Rename first: {obj.name}')


def export_lods(context, settings, report):
    formats = enabled_mesh_export_formats(settings)
    root = _export_root_directory(settings)
    if not formats or root is None:
        report({'ERROR'}, 'Enable an export format and save the blend file before exporting')
        return {'CANCELLED'}
    root = Path(root)
    meshes = _selected_mesh_objects(context)
    groups = {}
    records = {}
    try:
        tokens = {}
        for obj in meshes:
            base, role, index = lod_identity(obj)
            token = _safe_path_token(base)
            if token.casefold() in tokens and tokens[token.casefold()] != base:
                raise ValueError(f'Asset folder names conflict: {base}')
            tokens[token.casefold()] = base
            group = groups.setdefault(base, [])
            if any(records[item]['role'] == role and records[item]['lod_index'] == index for item in group):
                raise ValueError(f'Duplicate {role} index in {base}')
            group.append(obj)
            vertices, triangles = _evaluated_mesh_counts(obj, context.evaluated_depsgraph_get())
            records[obj] = dict(name=obj.name, asset=base, role=role, lod_index=index,
                lod=f'LOD{index}' if role == 'LOD' else 'HIGH',
                collections=[collection.name for collection in obj.users_collection],
                vertices=vertices, triangles=triangles, files={})
        tasks = []
        for base in sorted(groups, key=str.casefold):
            objects = groups[base]
            objects.sort(key=lambda obj: -1 if records[obj]['role'] == 'HIGH' else records[obj]['lod_index'])
            for format in formats:
                folder = root / _safe_path_token(base) / format
                if format == 'GLTF' and settings.unreal_gltf_mode == 'COMBINED':
                    lods = [obj for obj in objects if records[obj]['role'] == 'LOD']
                    if lods:
                        tasks.append((base, lods, folder / (_safe_path_token(base) + '.gltf'), format, True))
                    objects_to_write = [obj for obj in objects if records[obj]['role'] == 'HIGH']
                else:
                    objects_to_write = objects
                for obj in objects_to_write:
                    path = folder / (_safe_path_token(obj.name) + '.' + format.lower())
                    tasks.append((base, [obj], path, format, False))
        paths = [str(path).casefold() for _, _, path, _, _ in tasks]
        if len(paths) != len(set(paths)):
            raise ValueError('Export filenames conflict after filename normalization')
    except (ValueError, RuntimeError) as error:
        report({'ERROR'}, str(error))
        return {'CANCELLED'}
    selected = tuple(context.selected_objects)
    active = context.view_layer.objects.active
    mode = active.mode if active else 'OBJECT'
    detached = {}
    count = 0
    try:
        if mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        root.mkdir(parents=True, exist_ok=True)
        detached = _detach_export_alpha_maps(meshes)
        for base in sorted(groups, key=str.casefold):
            asset_folder = root / _safe_path_token(base)
            original_paths = _copy_export_textures(groups[base], str(asset_folder))
            try:
                for task_base, objects, path, format, combined in tasks:
                    if task_base != base:
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    bpy.ops.object.select_all(action='DESELECT')
                    for obj in objects:
                        obj.select_set(True)
                    context.view_layer.objects.active = objects[0]
                    with ExitStack() as stack:
                        for obj in objects:
                            stack.enter_context(_export_at_world_origin(obj, context.view_layer))
                        if format == 'GLTF':
                            result = _export_gltf_asset(str(path), combined)
                        else:
                            result = _export_selected_object(str(path), format)
                    if 'FINISHED' not in result:
                        raise RuntimeError(f'Unreal export did not finish: {path.name}')
                    count += 1
                    for obj in objects:
                        relative = path.relative_to(root).as_posix()
                        records[obj]['files'][format] = relative
                        records[obj].setdefault('file', relative)
            finally:
                for image, (filepath, raw) in original_paths.items():
                    image.filepath = filepath
                    image.filepath_raw = raw
            local_entries = []
            for obj in groups[base]:
                record = dict(records[obj])
                record['files'] = {format: Path(path).relative_to(_safe_path_token(base)).as_posix()
                                   for format, path in record['files'].items()}
                record['file'] = Path(record['file']).relative_to(_safe_path_token(base)).as_posix()
                local_entries.append(record)
            _write_export_mesh_info(str(asset_folder), settings.mesh_export_info_format, local_entries)
        _write_export_mesh_info(str(root), settings.mesh_export_info_format,
                                [records[obj] for base in sorted(groups, key=str.casefold) for obj in groups[base]])
    except (ValueError, RuntimeError, OSError) as error:
        report({'ERROR'}, str(error))
        return {'CANCELLED'}
    finally:
        _restore_export_alpha_maps(detached)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            obj.select_set(True)
        context.view_layer.objects.active = active
        if mode != 'OBJECT' and active:
            bpy.ops.object.mode_set(mode=mode)
    report({'INFO'}, f'Exported {len(groups)} Unreal assets, {len(meshes)} meshes, {count} files')
    return {'FINISHED'}
