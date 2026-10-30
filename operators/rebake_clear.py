"""Clear Before ReBake: wipe the final materials, textures and texture folders of the
rebaked assets so ReBake writes everything from scratch (no stale copies anywhere)."""
import shutil
from pathlib import Path

import bpy

from .rebake_final import final_asset_name

EXPORT_ROOTS = ('!Unreal',)


def _image_nodes(tree, seen):
    if tree is None or tree in seen:
        return
    seen.add(tree)
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            yield node.image
        elif node.type == 'GROUP':
            yield from _image_nodes(node.node_tree, seen)


def material_images(materials):
    return {image for material in materials if material
            for image in _image_nodes(material.node_tree, set())}


def asset_meshes(context, target):
    """The rebaked SM_<asset>_MID and its SM_<asset>_HIGH, when present."""
    asset = final_asset_name(target)[0]
    high = f'SM_{asset}_HIGH'.casefold()
    return [target] + [obj for obj in context.scene.objects
                       if obj.type == 'MESH' and obj != target and obj.name.casefold() == high]


def texture_folders(target):
    """Textures/<asset> beside the blend, and per-asset texture folders / files in the exports."""
    if not bpy.data.filepath:
        return [], []
    asset = final_asset_name(target)[0]
    names = {asset.casefold(), f'SM_{asset}'.casefold(), target.name.casefold()}
    root = Path(bpy.data.filepath).parent
    folders = [path for path in (root / 'Textures').glob('*')
               if path.is_dir() and not path.is_symlink() and path.name.casefold() in names]
    files = []
    prefix = f'T_{asset}_'.casefold()
    for export in EXPORT_ROOTS:
        for textures in (root / export).rglob('Textures') if (root / export).is_dir() else ():
            if not textures.is_dir() or textures.is_symlink():
                continue
            if textures.parent.name.casefold() in names:
                folders.append(textures)  # asset-first layout: !Unreal/<asset>/Textures
                continue
            for path in textures.iterdir():
                if path.is_dir() and path.name.casefold() in names:
                    folders.append(path)
                elif path.is_file() and path.stem.casefold().startswith(prefix):
                    files.append(path)  # format-first layout shares one Textures folder
    return folders, files


def clear_before_rebake(context, targets):
    """Remove materials (with their own textures) of every MID/HIGH, the asset texture folders and
    files, then purge unused data. Returns a short summary."""
    meshes = [obj for target in targets for obj in asset_meshes(context, target)]
    materials = {material for obj in meshes for material in obj.data.materials
                 if material and material.library is None}
    images = material_images(materials)
    # Textures that other materials (Highpoly sources, other assets) still read stay.
    images -= material_images(set(bpy.data.materials) - materials)
    images = {image for image in images if image.library is None}
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.polygons.foreach_set('material_index', [0] * len(obj.data.polygons))
    bpy.data.batch_remove(materials | images)
    folders, files = set(), set()
    for target in targets:
        found_folders, found_files = texture_folders(target)
        folders.update(found_folders)
        files.update(found_files)
    errors = []
    for folder in folders:
        try:
            shutil.rmtree(folder)
        except OSError as error:
            errors.append(f'{folder.name}: {error}')
    for path in files:
        try:
            path.unlink()
        except OSError as error:
            errors.append(f'{path.name}: {error}')
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    return dict(meshes=len(meshes), materials=len(materials), images=len(images),
                folders=len(folders), files=len(files), errors=errors)
