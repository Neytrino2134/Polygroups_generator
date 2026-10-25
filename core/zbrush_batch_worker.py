"""Background Blender worker: export the multires meshes of one blend file for ZBrush.

Usage: blender -b file.blend --python zbrush_batch_worker.py -- <addon package> <addons folder> <output root> <part json>
Writes the exported asset records to <part json>; the main session merges the parts into one manifest."""
import importlib
import json
import sys

import addon_utils
import bpy


def main():
    addon, addons_folder, root, part = sys.argv[sys.argv.index('--') + 1:][:4]
    if addons_folder not in sys.path:
        sys.path.insert(0, addons_folder)
    bpy.context.preferences.use_preferences_save = False
    addon_utils.enable(addon, default_set=False)
    module = importlib.import_module(f'{addon}.operators.phase2_zbrush_export')
    candidates = module.batch_candidates(bpy.context.scene)
    assets = module.export_candidates(bpy.context, candidates, root)
    with open(part, 'w', encoding='utf-8') as handle:
        json.dump({'assets': assets, 'blend': bpy.data.filepath}, handle, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
