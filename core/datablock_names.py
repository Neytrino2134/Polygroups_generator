"""Exact datablock names and texture files: a re-created texture or material permanently replaces
the old one. Nothing is kept as T_..._BaseColor.001 / _Old, in the blend or on disk."""
import re
from pathlib import Path

import bpy

# Stale copies of the toolkit's own final names: T_<asset>_<channel> / M_<asset> + .001 / _Old.
STALE = re.compile(r'^([TM]_.+?)(?:_Old|\.\d{3})+$')


def take_name(collection, item, name, replace=False, aside=None):
    """Give ``item`` exactly ``name``; the datablock that already holds it is the stale version.

    With ``replace`` (or when ``aside`` is None) its users are remapped to ``item`` and it is
    removed at once. With an ``aside`` list the remap is deferred (the caller may still be
    reading the old one): ``drop_unused(aside)`` remaps and removes it afterwards.
    """
    other = collection.get(name)
    if other is not None and other != item and other.library is None:
        if replace or aside is None:
            other.user_remap(item)
            collection.remove(other)
        else:
            other.name = name + '__stale'
            aside.append((collection, other, item))
    item.name = name
    return item


def drop_unused(aside):
    """Finish deferred take_name calls: every stale holder is remapped to its replacement and removed."""
    for collection, other, item in aside:
        try:
            other.user_remap(item)
            collection.remove(other)
        except ReferenceError:
            pass
    aside.clear()


def merge_stale_copies():
    """Fold leftover T_/M_ copies (.001, _Old) into the exact name: remap and remove, or rename back."""
    for collection in (bpy.data.materials, bpy.data.images):
        for item in sorted(collection, key=lambda item: item.name):
            match = STALE.match(item.name) if item.library is None else None
            if not match:
                continue
            base = collection.get(match.group(1))
            if base is None:
                item.name = match.group(1)
            elif base != item and base.library is None:
                item.user_remap(base)
                collection.remove(item)


def remove_numbered_files(path):
    """Delete <stem>.001.png, <stem>_Old.png ... beside ``path`` unless an image still reads them."""
    path = Path(path)
    if not path.parent.is_dir():
        return 0
    pattern = re.compile(re.escape(path.stem) + r'(?:_Old|\.\d{3})+' + re.escape(path.suffix) + '$', re.IGNORECASE)
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
