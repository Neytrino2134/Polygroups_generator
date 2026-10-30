"""Exact datablock names and texture files: a re-created texture or material replaces the old one
instead of becoming T_..._BaseColor.001 / M_....001 (and T_..._BaseColor.001.png on disk)."""
import re
from pathlib import Path

import bpy

NUMBERED = re.compile(r'(?:\.\d{3})+$')


def take_name(collection, item, name, replace=False, aside=None):
    """Give ``item`` exactly ``name``.

    The local datablock that already holds the name is the stale previous version:
    with ``replace`` its users are remapped to ``item`` and it is removed; otherwise
    it is removed when unused, or renamed aside and appended to ``aside`` so the
    caller can drop it once its last users are gone (see ``drop_unused``).
    """
    other = collection.get(name)
    if other is not None and other != item and other.library is None:
        if replace:
            other.user_remap(item)
        if replace or other.users == 0:
            collection.remove(other)
        else:
            other.name = name + '_Old'
            if aside is not None:
                aside.append(other)
    item.name = name
    return item


def drop_unused(items):
    """Remove the aside datablocks that nothing uses any more (materials first frees their images)."""
    kinds = (bpy.types.Material, bpy.types.Image)
    for kind in kinds:
        for item in list(items):
            try:
                if isinstance(item, kind) and item.users == 0 and not item.use_fake_user:
                    (bpy.data.materials if kind is bpy.types.Material else bpy.data.images).remove(item)
                    items.remove(item)
            except ReferenceError:
                items.remove(item)


def remove_numbered_files(path):
    """Delete <stem>.001.png, <stem>.002.png ... beside ``path`` unless an image still reads them."""
    path = Path(path)
    if not path.parent.is_dir():
        return 0
    pattern = re.compile(re.escape(path.stem) + r'(?:\.\d{3})+' + re.escape(path.suffix) + '$', re.IGNORECASE)
    used = set()
    for image in bpy.data.images:
        if image.users and image.filepath and image.library is None:
            try:
                used.add(Path(bpy.path.abspath(image.filepath)).resolve())
            except (OSError, ValueError):
                pass
    removed = 0
    for sibling in path.parent.iterdir():
        if sibling.is_file() and pattern.match(sibling.name) and sibling.resolve() not in used:
            try:
                sibling.unlink()
                removed += 1
            except OSError:
                pass
    return removed
