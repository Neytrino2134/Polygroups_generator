"""Scan, check and clear temporary files in the final asset folder of the open blend file.

The final asset folder is the folder of the working blend, for example
``D:/Work/3D Stocks/3D Asset Packs/!NewAssetPack/08_Gray_Rocks_Ready``:

* the working blend itself and everything in ``!`` folders (``!Blend``, ``!Renders``, ``!Unity``, ``!Unreal``,
  ``!ZBrush``) stay; only backup saves (``.blend1`` / ``.blendN`` / ``.BlendAutosaveN``) may be deleted there;
* ``01_`` ... ``20_`` source folders and every ``Textures`` folder are never touched;
* other ``.blend`` files beside the working blend or in other folders (for example ``blender``) are temporary;
* the ``Bakes`` and ``batch_reports`` folders are temporary.
"""
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

BACKUP_SAVE = re.compile(r'\.(?:blend\d+|blendautosave\d*)$', re.IGNORECASE)
BLEND_FILE = re.compile(r'\.blend$', re.IGNORECASE)
SOURCE_FOLDER = re.compile(r'^\d{2}_')
TEMP_FOLDERS = ('bakes', 'batch_reports')
KEEP_FOLDERS = ('textures',)
FINAL_BLEND_FOLDER = '!blend'
GENERATED_BLEND = re.compile(r'^Generated\.\d+\.blend$', re.IGNORECASE)
HIGHPOLY = re.compile(r'^Highpoly_Generated(?:\.\d+)*$', re.IGNORECASE)
RESCULPTING = re.compile(r'^Resculpting_\d+_Highpoly_Generated(?:\.\d+)*$', re.IGNORECASE)
RETOPO = re.compile(r'^Retopo_\d+_Highpoly_Generated(?:\.\d+)*$', re.IGNORECASE)

CATEGORIES = (
    ('backup', 'Backup saves (.blend1 / .blendN / Autosave)'),
    ('blend_beside', 'Other .blend beside the working file'),
    ('blend_other', 'Other .blend in other folders'),
    ('temp_folder', 'Temporary folders (Bakes / batch_reports)'),
)


@dataclass
class Item:
    category: str
    path: Path
    size: int
    count: int = 1
    mtime: int = 0


@dataclass
class Scan:
    root: Path
    current: Path
    items: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def totals(self):
        """{category: (files, bytes)} for every category, including empty ones."""
        result = {key: (0, 0) for key, _label in CATEGORIES}
        for item in self.items:
            files, size = result[item.category]
            result[item.category] = (files + item.count, size + item.size)
        return result

    @property
    def file_count(self):
        return sum(item.count for item in self.items)

    @property
    def total_bytes(self):
        return sum(item.size for item in self.items)


def is_link(path):
    """Symlinks and junctions are never followed or deleted through."""
    if os.path.islink(path):
        return True
    junction = getattr(os.path, 'isjunction', None)
    return bool(junction and junction(path))


def check_root(root):
    root = Path(root)
    if len(root.parts) < 3 or root == Path(root.anchor):
        raise ValueError('Refusing to clean a drive or top-level folder')
    if not root.is_dir():
        raise ValueError('The working blend folder does not exist')
    return root


def folder_totals(folder):
    count = size = 0
    for current, directories, files in os.walk(folder):
        directories[:] = [name for name in directories if not is_link(os.path.join(current, name))]
        for name in files:
            try:
                size += os.path.getsize(os.path.join(current, name))
                count += 1
            except OSError:
                pass
    return count, size


def scan(root, current):
    """Find everything that Clear All Temp Files would delete."""
    root, current = check_root(root), Path(current)
    result = Scan(root, current)

    def add_file(category, path):
        try:
            stat = path.stat()
        except OSError as error:
            result.errors.append(f'{path.name}: {error}')
            return
        result.items.append(Item(category, path, stat.st_size, 1, stat.st_mtime_ns))

    for folder, directories, files in os.walk(root):
        folder_path = Path(folder)
        final_folder = folder_path != root and any(
            part.startswith('!') for part in folder_path.relative_to(root).parts)
        kept = []
        for name in directories:
            lowered = name.lower()
            path = folder_path / name
            if is_link(path) or lowered in KEEP_FOLDERS or SOURCE_FOLDER.match(name):
                continue
            if lowered in TEMP_FOLDERS and not final_folder and not name.startswith('!'):
                count, size = folder_totals(path)
                result.items.append(Item('temp_folder', path, size, count))
                continue
            kept.append(name)
        directories[:] = kept
        for name in files:
            path = folder_path / name
            if is_link(path):
                continue
            if BACKUP_SAVE.search(name):
                add_file('backup', path)
            elif BLEND_FILE.search(name) and not final_folder and not name.startswith('!') \
                    and path != current and path.parent != root:
                add_file('blend_other', path)
            elif BLEND_FILE.search(name) and path.parent == root and path != current:
                add_file('blend_beside', path)
    return result


def delete(result):
    """Delete the scanned items after checking that each one is unchanged; returns (files, bytes, errors)."""
    root = check_root(result.root)
    deleted_files = deleted_bytes = 0
    errors = list(result.errors)
    for item in result.items:
        try:
            path = item.path
            if is_link(path) or not path.resolve().is_relative_to(root.resolve()) or path == result.current:
                raise ValueError('path is not safe to delete')
            if item.category == 'temp_folder':
                if path.name.lower() not in TEMP_FOLDERS or not path.is_dir():
                    raise ValueError('not a temporary folder')
                shutil.rmtree(path)
            else:
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (item.size, item.mtime):
                    raise ValueError('file changed after scanning')
                path.unlink()
            deleted_files += item.count
            deleted_bytes += item.size
        except (ValueError, OSError) as error:
            errors.append(f'{item.path.name}: {error}')
    return deleted_files, deleted_bytes, errors


# Clear All Files: Start from Scratch (ALL) and Clear Phase 2 Files (PHASE2).
# Source folders (01_ ... 20_) and the working blend are never touched.
RESET_CATEGORIES = (
    ('final_folder', '! folders (!Blend, !Unreal, !Unity, !Renders, !ZBrush ...)'),
    ('textures', 'Textures folders'),
    ('temp_folder', 'Bakes / batch_reports folders'),
    ('blend_beside', 'Other .blend beside the working file'),
    ('blend_other', 'Other .blend in other folders'),
    ('backup', 'Backup saves (.blend1 / .blendN / Autosave)'),
)
RESET_KEEP = {'PHASE2': {'temp_folder', 'blend_beside', 'blend_other', 'backup'}, 'ALL': set()}


def reset_totals(result):
    totals = {key: (0, 0) for key, _label in RESET_CATEGORIES}
    for item in result.items:
        files, size = totals[item.category]
        totals[item.category] = (files + item.count, size + item.size)
    return totals


def scan_reset(root, current, mode):
    """Find what Start from Scratch (ALL) or Clear Phase 2 Files (PHASE2) would delete."""
    root, current = check_root(root), Path(current)
    skip = RESET_KEEP[mode]
    result = Scan(root, current)

    def add(category, path, folder=False):
        if category in skip:
            return
        try:
            if folder:
                count, size = folder_totals(path)
                result.items.append(Item(category, path, size, count))
            else:
                stat = path.stat()
                result.items.append(Item(category, path, stat.st_size, 1, stat.st_mtime_ns))
        except OSError as error:
            result.errors.append(f'{path.name}: {error}')

    for folder, directories, files in os.walk(root):
        folder_path = Path(folder)
        kept = []
        for name in directories:
            path = folder_path / name
            lowered = name.lower()
            if is_link(path) or SOURCE_FOLDER.match(name):
                continue
            if name.startswith('!'):
                add('final_folder', path, True)
            elif lowered in KEEP_FOLDERS:
                add('textures', path, True)
            elif lowered in TEMP_FOLDERS:
                if 'temp_folder' in skip:
                    continue  # kept whole, nothing inside is touched
                add('temp_folder', path, True)
            else:
                kept.append(name)
        directories[:] = kept
        for name in files:
            path = folder_path / name
            if is_link(path) or path == current:
                continue
            if BACKUP_SAVE.search(name):
                add('backup', path)
            elif BLEND_FILE.search(name):
                add('blend_beside' if path.parent == root else 'blend_other', path)
    return result


def delete_reset(result):
    """Delete a scan_reset result after re-checking every path; returns (files, bytes, errors)."""
    root = check_root(result.root).resolve()
    folders = {'final_folder': lambda name: name.startswith('!'),
               'textures': lambda name: name.lower() in KEEP_FOLDERS,
               'temp_folder': lambda name: name.lower() in TEMP_FOLDERS}
    deleted_files = deleted_bytes = 0
    errors = list(result.errors)
    for item in result.items:
        path = item.path
        try:
            if is_link(path) or path == result.current or not path.resolve().is_relative_to(root) \
                    or path.resolve() == root:
                raise ValueError('path is not safe to delete')
            if item.category in folders:
                if not folders[item.category](path.name) or not path.is_dir():
                    raise ValueError('unexpected folder')
                shutil.rmtree(path)
            else:
                if not (BACKUP_SAVE.search(path.name) or BLEND_FILE.search(path.name)):
                    raise ValueError('unexpected file')
                path.unlink()
            deleted_files += item.count
            deleted_bytes += item.size
        except (ValueError, OSError) as error:
            errors.append(f'{path.name}: {error}')
    return deleted_files, deleted_bytes, errors


@dataclass
class GeneratedFile:
    name: str
    highpoly: list = field(default_factory=list)
    resculpting: list = field(default_factory=list)
    retopo: list = field(default_factory=list)
    error: str = ''

    @property
    def ok(self):
        """Highpoly_Generated.N plus Resculpting_NN_ or Retopo_NN_Highpoly_Generated.N."""
        return not self.error and bool(self.highpoly) and bool(self.resculpting or self.retopo)

    def summary(self):
        if self.error:
            return self.error
        parts = [('Highpoly', self.highpoly), ('Resculpting', self.resculpting), ('Retopo', self.retopo)]
        return ' | '.join(f'{label} {len(names)}' for label, names in parts if names) or 'no highpoly meshes'


@dataclass
class Check:
    folder: Path = None
    blend_count: int = 0
    generated: list = field(default_factory=list)

    @property
    def all_ok(self):
        return bool(self.generated) and all(item.ok for item in self.generated)


def object_names(path):
    """Object names in a blend file without loading any data."""
    import bpy
    with bpy.data.libraries.load(str(path)) as (source, _target):
        return list(source.objects)


def classify(name, names):
    item = GeneratedFile(name)
    for object_name in names:
        for pattern, bucket in ((HIGHPOLY, item.highpoly), (RESCULPTING, item.resculpting), (RETOPO, item.retopo)):
            if pattern.match(object_name):
                bucket.append(object_name)
    return item


def check(root, read_names=object_names):
    """Count the files in !Blend and verify the highpoly meshes of every Generated.N file."""
    root = Path(root)
    result = Check()
    folder = next((path for path in root.iterdir() if path.is_dir() and path.name.lower() == FINAL_BLEND_FOLDER), None) \
        if root.is_dir() else None
    if folder is None:
        return result
    result.folder = folder
    blends = sorted((path for path in folder.iterdir() if path.is_file() and BLEND_FILE.search(path.name)),
                    key=lambda path: path.name.lower())
    result.blend_count = len(blends)
    for path in blends:
        if not GENERATED_BLEND.match(path.name):
            continue
        name = path.name[:-len('.blend')]
        try:
            result.generated.append(classify(name, read_names(path)))
        except Exception as error:
            result.generated.append(GeneratedFile(name, error=f'cannot read: {error}'))
    return result


def megabytes(size):
    return f'{size / (1024 * 1024):.1f} MB'
