"""Export independent Unreal LOD assets with multiple file formats."""
from contextlib import ExitStack
from pathlib import Path
import re
import bpy
from .mesh_export import (
    _selected_mesh_objects, _export_root_directory, _safe_path_token,
    _detach_export_alpha_maps, _restore_export_alpha_maps,
    _export_at_world_origin, _export_selected_object, _export_gltf_asset,
    _evaluated_mesh_counts, _write_export_mesh_info, _write_fab_format_mesh_info, enabled_mesh_export_formats,
)
from .unreal_export_textures import export_texture_scope
from .fab_mesh_details import collect_mesh_details


def lod_identity(obj, engine='Unreal'):
    if engine == 'Unity' and obj.get('unity_prepared'):
        match = re.fullmatch(r'(.+)\.LOD(\d+)', obj.name, re.IGNORECASE)
        return (match[1], 'LOD', int(match[2])) if match else (obj.name, 'LOD', 0)
    match = re.fullmatch(r'SM_(.+)_LOD(\d+)', obj.name, re.IGNORECASE)
    if match:
        return match[1], 'LOD', int(match[2])
    match = re.fullmatch(r'SM_(.+)_LOW', obj.name, re.IGNORECASE)
    if match:
        return match[1], 'LOD', 0
    base = obj.get('unreal_lod_asset')
    if base and obj.get('unreal_lod_index') == -1:
        return base, 'HIGH', None
    match = re.fullmatch(r'(?:SM_)?(.+)_(?:High|MID)', obj.name, re.IGNORECASE)
    if match:
        return match[1], 'HIGH', None
    raise ValueError(f'Use Unreal LOD Rename first: {obj.name}')


def export_lods(context, settings, report, engine='Unreal', output_root=None, overwrite=True):
    formats = enabled_mesh_export_formats(settings)
    root = output_root or _export_root_directory(settings)
    if not formats or root is None:
        report({'ERROR'}, 'Enable an export format and save the blend file before exporting')
        return {'CANCELLED'}
    root = Path(root)
    format_first = settings.mesh_export_sort == 'LODS_FORMAT'
    meshes = _selected_mesh_objects(context)
    groups = {}
    records = {}
    try:
        tokens = {}
        for obj in meshes:
            base, role, index = lod_identity(obj, engine)
            token = _safe_path_token(base)
            if token.casefold() in tokens and tokens[token.casefold()] != base:
                raise ValueError(f'Asset folder names conflict: {base}')
            tokens[token.casefold()] = base
            group = groups.setdefault(base, [])
            if any(records[item]['role'] == role and records[item]['lod_index'] == index for item in group):
                raise ValueError(f'Duplicate {role} index in {base}')
            group.append(obj)
            graph = context.evaluated_depsgraph_get()
            details = None
            if engine == 'Unreal' and settings.mesh_export_info_format == 'JSON':
                vertices, triangles, details = collect_mesh_details(obj, graph, context.scene.unit_settings.scale_length)
            else:
                vertices, triangles = _evaluated_mesh_counts(obj, graph)
            records[obj] = dict(name=obj.name, asset=base, role=role, lod_index=index,
                lod=f'LOD{index}' if role == 'LOD' else 'HIGH',
                collections=[collection.name for collection in obj.users_collection],
                vertices=vertices, triangles=triangles, files={})
            if details is not None:
                records[obj]['_fab_details'] = details
        tasks = []
        for base in sorted(groups, key=str.casefold):
            objects = groups[base]
            objects.sort(key=lambda obj: -1 if records[obj]['role'] == 'HIGH' else records[obj]['lod_index'])
            for format in formats:
                folder = root / format if format_first else root / _safe_path_token(base) / format
                combine = ((format == 'GLTF' and settings.unreal_gltf_mode in {'AUTO', 'COMBINED'})
                           or (format == 'GLB' and settings.unreal_glb_mode in {'AUTO', 'COMBINED'}))
                if combine:
                    lods = [obj for obj in objects if records[obj]['role'] == 'LOD']
                    if lods:
                        tasks.append((base, lods, folder / (_safe_path_token(base) + '.' + format.lower()), format, True))
                    objects_to_write = [obj for obj in objects if records[obj]['role'] == 'HIGH']
                else:
                    objects_to_write = objects
                for obj in objects_to_write:
                    path = folder / (_safe_path_token(obj.name) + '.' + format.lower())
                    tasks.append((base, [obj], path, format, False))
        paths = [str(path).casefold() for _, _, path, _, _ in tasks]
        if len(paths) != len(set(paths)):
            raise ValueError('Export filenames conflict after filename normalization')
        if not overwrite and any(path.exists() for _, _, path, _, _ in tasks):
            raise ValueError('Export files already exist; enable Unity Overwrite Existing')
    except (ValueError, RuntimeError) as error:
        report({'ERROR'}, str(error))
        return {'CANCELLED'}
    selected = tuple(context.selected_objects)
    active = context.view_layer.objects.active
    mode = active.mode if active else 'OBJECT'
    detached = {}
    count = 0
    normal_mode = (context.scene.polygroups_mesh_finalization_settings.unreal_fbx_normal_maps
                   if engine == 'Unreal' else None)
    try:
        if mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        root.mkdir(parents=True, exist_ok=True)
        detached = _detach_export_alpha_maps(meshes)
        scopes = ([(root / format, meshes, format) for format in formats] if format_first else
                  [(root / _safe_path_token(base), groups[base], base) for base in sorted(groups, key=str.casefold)])
        for scope_folder, scope_objects, scope_key in scopes:
            scope_folder.mkdir(parents=True, exist_ok=True)
            scope_formats = [scope_key] if format_first else formats
            with export_texture_scope(scope_objects, scope_folder, scope_formats, normal_mode) as (bind, manifest):
                for task_base, objects, path, format, combined in tasks:
                    if (format if format_first else task_base) != scope_key:
                        continue
                    bind(format)
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
                        if format == 'FBX' and normal_mode:
                            records[obj]['textures'] = manifest(obj)
            if format_first and engine == 'Unreal' and settings.mesh_export_info_format == 'JSON':
                continue
            local_entries = []
            scope_prefix = scope_folder.relative_to(root)
            for obj in scope_objects:
                record = dict(records[obj])
                record['files'] = {format: Path(path).relative_to(scope_prefix).as_posix()
                                   for format, path in record['files'].items()
                                   if not format_first or format == scope_key}
                record['file'] = next(iter(record['files'].values()))
                if 'FBX' not in record['files']:
                    record.pop('textures', None)
                local_entries.append(record)
            _write_export_mesh_info(str(scope_folder), settings.mesh_export_info_format, local_entries, engine=engine)
        entries = [records[obj] for base in sorted(groups, key=str.casefold) for obj in groups[base]]
        _write_export_mesh_info(str(root), settings.mesh_export_info_format, entries, engine=engine)
        if engine == 'Unreal' and settings.mesh_export_info_format == 'JSON':
            _write_fab_format_mesh_info(root, entries)
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
    report({'INFO'}, f'Exported {len(groups)} {engine} assets, {len(meshes)} meshes, {count} files')
    return {'FINISHED'}
