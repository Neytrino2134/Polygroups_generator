"""Reload All Textures re-reads file images from disk and tolerates missing files."""
import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)

with tempfile.TemporaryDirectory() as folder:
    path = str(Path(folder) / 'tex.png')
    first = bpy.data.images.new('first', 4, 4)
    first.pixels = [1.0, 0.0, 0.0, 1.0] * 16
    first.filepath_raw, first.file_format = path, 'PNG'
    first.save()
    image = bpy.data.images.load(path)
    assert round(image.pixels[0], 2) == 1.0
    # The file changes on disk; the loaded image still holds the old pixels until it is reloaded.
    first.pixels = [0.0, 1.0, 0.0, 1.0] * 16
    first.save()
    bpy.data.images.new('generated', 4, 4)
    gone = bpy.data.images.load(path)
    gone.filepath = str(Path(folder) / 'missing.png')
    assert round(image.pixels[0], 2) == 1.0
    assert bpy.ops.object.polygroups_reload_all_textures() == {'FINISHED'}
    assert round(image.pixels[1], 2) == 1.0 and round(image.pixels[0], 2) == 0.0
print('reload all textures ok')
