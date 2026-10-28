"""Rank numbered Highpoly sources and temporarily append external collections."""
from pathlib import Path
import re

import bpy

COLLECTION_PATTERN = re.compile(r'^Generated\.(\d+)$', re.IGNORECASE)
SOURCE_PATTERN = re.compile(r'^(Resculpting_01_)?Highpoly_Generated(?:\.(\d+))?$', re.IGNORECASE)


def preferred_source_name(names, index, location):
    candidates = [(bool(match[1]), name) for name in names
                  if (match := SOURCE_PATTERN.fullmatch(name)) and int(match[2] or 0) == index]
    if not candidates:
        raise ValueError(f'{location}: no Highpoly_Generated.{index:03d} or Resculpting_01_Highpoly_Generated.{index:03d} mesh')
    rank = min(priority for priority, _ in candidates)
    preferred = [name for priority, name in candidates if priority == rank]
    if len(preferred) != 1:
        raise ValueError(f'{location}: ambiguous Highpoly sources: ' + ', '.join(sorted(preferred)))
    return preferred[0]
# Track append-owned IDs only; never purge pre-existing data by name or globally.
DATA_KINDS = ('collections', 'objects', 'meshes', 'curves', 'materials', 'images',
              'node_groups', 'textures', 'actions', 'armatures', 'cameras', 'lights',
              'shape_keys', 'worlds', 'libraries', 'cache_files', 'volumes',
              'hair_curves', 'pointclouds', 'lattices', 'fonts', 'movieclips', 'sounds',
              'scenes', 'texts', 'metaballs', 'speakers', 'lightprobes', 'particles',
              'grease_pencils', 'grease_pencils_v3')


def source_blend_path(index):
    if not bpy.data.filepath:
        raise ValueError('Save the working blend before loading a missing Highpoly from !Blend')
    current = Path(bpy.data.filepath).resolve()
    folder = current.parent if current.parent.name.casefold() == '!blend' else current.parent / '!Blend'
    expected = folder / f'Generated.{index:03d}.blend'
    if expected.is_file():
        result = expected
    else:
        candidates = [path for path in folder.glob('*.blend')
                      if (match := COLLECTION_PATTERN.fullmatch(path.stem)) and int(match[1]) == index]
        if len(candidates) != 1:
            raise ValueError(f'Missing Highpoly source file: {expected}' if not candidates else
                             f'Multiple Generated files match source index {index} in {folder}')
        result = candidates[0]
    if result.resolve() == current:
        raise ValueError('The Highpoly source file must differ from the open working blend')
    return result


class TemporaryRebakeSource:
    def __init__(self, index):
        self.path = source_blend_path(index)
        self.index = index
        self.owned = set()
        self.collection = None
        self.source = None
        with bpy.data.libraries.load(str(self.path), link=False) as (library, _unused):
            collections = [name for name in library.collections
                           if (match := COLLECTION_PATTERN.fullmatch(name)) and int(match[1]) == index]
            canonical = f'Generated.{index:03d}'
            if canonical in collections:
                collections = [canonical]
            if len(collections) != 1:
                raise ValueError(f'{self.path.name}: expected one Generated.{index:03d} collection')
            self.collection_name = collections[0]
            self.source_names = [name for name in library.objects
                                 if (match := SOURCE_PATTERN.fullmatch(name)) and int(match[2] or 0) == index]
            if not self.source_names:
                preferred_source_name([], index, self.path.name)

    def load(self, context):
        before = {kind: set(getattr(bpy.data, kind)) for kind in DATA_KINDS if hasattr(bpy.data, kind)}
        try:
            try:
                with bpy.data.libraries.load(str(self.path), link=False) as (_library, appended):
                    appended.collections = [self.collection_name]
                    # Direct references preserve file-name identity across ID
                    # collisions with pre-existing objects in another scene.
                    appended.objects = list(self.source_names)
            finally:
                self.owned.update(item for kind, snapshot in before.items()
                                  for item in set(getattr(bpy.data, kind)) - snapshot)
            self.collection = appended.collections[0]
            if self.collection is None:
                raise ValueError(f'{self.path.name}: could not load {self.collection_name}')
            members = {name: obj for name, obj in zip(self.source_names, appended.objects)
                       if obj is not None and obj.type == 'MESH' and obj.name in self.collection.all_objects}
            if not members:
                raise ValueError(f'{self.path.name}: Highpoly mesh is not in {self.collection_name}')
            self.source = members[preferred_source_name(members, self.index, self.collection_name)]
            if self.source.library:
                raise ValueError('The imported Highpoly must be a local appended object')
            if self.source.data.library or self.source.data.users != 1:
                self.source.data = self.source.data.copy()
                self.owned.add(self.source.data)
            context.scene.collection.children.link(self.collection)
            context.view_layer.update()
            return self.source
        except Exception:
            self.cleanup()
            raise

    def cleanup(self):
        if self.owned:
            # This exact append snapshot excludes all pre-existing scene IDs and
            # all materials/images subsequently produced by the rebake itself.
            bpy.data.batch_remove(ids=self.owned)
            self.owned.clear()
        self.collection = self.source = None
