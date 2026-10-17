"""Stage material textures before replacing one asset's output directories."""
from array import array
from pathlib import Path
import os
import shutil
import tempfile
import bpy


def refresh_asset_textures(objects, asset_name, export_root):
    from .unity_preparation import texture_nodes
    from .mesh_export import _safe_path_token
    if not bpy.data.filepath:
        raise ValueError('Save the blend file before refreshing asset textures')
    name = _safe_path_token(asset_name)
    texture_root = Path(bpy.data.filepath).resolve().parent / 'Textures'
    export_root = Path(export_root).resolve()
    texture_dir = texture_root / name
    export_dir = export_root / name
    destinations = (texture_dir, export_dir)
    blend = Path(bpy.data.filepath).resolve()
    for folder, parent in zip(destinations, (texture_root, export_root)):
        resolved = folder.resolve()
        if folder.is_symlink() or folder.is_junction() or resolved.parent != parent.resolve() or resolved == blend or resolved in blend.parents:
            raise ValueError(f'Unsafe asset folder: {folder}')
        if folder.exists() and not folder.is_dir():
            raise ValueError(f'Asset destination is not a directory: {folder}')
    if texture_dir.resolve() == export_dir.resolve() or texture_dir.resolve() in export_dir.resolve().parents or export_dir.resolve() in texture_dir.resolve().parents:
        raise ValueError('Unity export and source texture asset folders must be separate')
    images = {node.image for obj in objects if obj.type == 'MESH'
              for mat in obj.data.materials if mat for node in texture_nodes(mat.node_tree)}
    originals = {image: (image.filepath_raw, image.source) for image in images}
    with tempfile.TemporaryDirectory(prefix='airetopo-unity-reexport-') as temporary:
        temporary = Path(temporary)
        staged = {}
        # No directories are changed until every connected/unconnected texture
        # (including service masks) has a complete independent on-disk snapshot.
        for index, image in enumerate(sorted(images, key=lambda item: item.name)):
            if image.source not in {'FILE', 'GENERATED'}:
                raise ValueError(f'Unsupported source texture: {image.name} ({image.source})')
            original_file = Path(bpy.path.abspath(image.filepath)) if image.filepath else None
            if image.source == 'FILE' and not image.is_dirty and original_file and original_file.is_file():
                extension = original_file.suffix or '.png'
                path = temporary / (f'{index:04d}' + extension)
                shutil.copy2(original_file, path)
                staged[image] = (path, _safe_path_token(image.name) + extension)
                continue
            if image.packed_file and not image.is_dirty:
                extension = original_file.suffix if original_file and original_file.suffix else '.png'
                path = temporary / (f'{index:04d}' + extension)
                path.write_bytes(bytes(image.packed_file.data))
                staged[image] = (path, _safe_path_token(image.name) + extension)
                continue
            pixels = array('f', [0.0]) * len(image.pixels)
            if not pixels:
                raise ValueError(f'Source texture has no loaded pixels: {image.name}')
            image.pixels.foreach_get(pixels)
            copy = bpy.data.images.new('__UnityTextureSnapshot', width=image.size[0], height=image.size[1],
                                       alpha=image.channels == 4, float_buffer=image.is_float)
            try:
                copy.colorspace_settings.name = image.colorspace_settings.name
                copy.alpha_mode = image.alpha_mode
                copy.pixels.foreach_set(pixels)
                copy.file_format = 'OPEN_EXR' if image.is_float else 'PNG'
                extension = '.exr' if image.is_float else '.png'
                path = temporary / (f'{index:04d}' + extension)
                copy.save(filepath=str(path))
                staged[image] = (path, _safe_path_token(image.name) + extension)
            finally:
                bpy.data.images.remove(copy)
        names = [name for _, name in staged.values()]
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError('Texture filenames conflict after filename normalization')
        backups = []
        for index, folder in enumerate(destinations):
            backup = temporary / f'backup-{index}'
            if folder.exists():
                shutil.copytree(folder, backup)
            backups.append(backup)
        try:
            for folder in destinations:
                if folder.exists():
                    shutil.rmtree(folder)
            texture_dir.mkdir(parents=True, exist_ok=True)
            for image, (source, filename) in staged.items():
                target = texture_dir / filename
                shutil.copy2(source, target)
            for image, (_, filename) in staged.items():
                target = texture_dir / filename
                image.filepath_raw = str(target)
                if image.source == 'GENERATED':
                    image.source = 'FILE'
        except Exception:
            for folder, backup in zip(destinations, backups):
                if folder.exists():
                    shutil.rmtree(folder)
                if backup.exists():
                    shutil.copytree(backup, folder)
            for image, (path, source) in originals.items():
                image.filepath_raw = path
                image.source = source
            raise
