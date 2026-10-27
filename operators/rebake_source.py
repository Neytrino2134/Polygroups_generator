"""Temporarily append the numbered Resculpting source for a final rebake."""
from pathlib import Path
import re

import bpy

COLLECTION_PATTERN = re.compile(r'^Generated\.(\d+)$', re.IGNORECASE)
SOURCE_PATTERN = re.compile(r'^Resculpting_01_Highpoly_Generated(?:\.(\d+))?$', re.IGNORECASE)
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
            sources = [name for name in library.objects
                       if (match := SOURCE_PATTERN.fullmatch(name)) and int(match[1] or 0) == index]
            if len(sources) != 1:
                raise ValueError(f'{self.path.name}: expected one Resculpting_01_Highpoly_Generated.{index:03d} mesh')
            self.collection_name, self.source_name = collections[0], sources[0]

    def load(self, context):
        before = {kind: set(getattr(bpy.data, kind)) for kind in DATA_KINDS if hasattr(bpy.data, kind)}
        try:
            try:
                with bpy.data.libraries.load(str(self.path), link=False) as (_library, appended):
                    appended.collections = [self.collection_name]
                    # Request the object too, retaining a direct ID reference if
                    # Blender adds .001 because its name already exists elsewhere.
                    appended.objects = [self.source_name]
            finally:
                self.owned.update(item for kind, snapshot in before.items()
                                  for item in set(getattr(bpy.data, kind)) - snapshot)
            self.collection = appended.collections[0]
            self.source = appended.objects[0]
            if (self.collection is None or self.source is None or self.source.type != 'MESH'
                    or self.source.name not in self.collection.all_objects):
                raise ValueError(f'{self.path.name}: the Resculpting mesh is not in {self.collection_name}')
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
