"""Unity Prepare puts every LOD of an asset into one AssetName_Index_VersionIndex_Collection."""
import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)

scene = bpy.context.scene
settings = scene.polygroups_mesh_finalization_settings
settings.unity_copy_textures = False
settings.unity_generate_text_labels = False
settings.unity_asset_name, settings.unity_name_index, settings.unity_asset_index = 'Stone', '00', '01'

for stale in list(bpy.data.objects):
    bpy.data.objects.remove(stale)
meshes = []
for count in (3, 2, 1):
    mesh = bpy.data.meshes.new(f'M{count}')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)] * count)
    obj = bpy.data.objects.new(f'Src{count}', mesh)
    scene.collection.objects.link(obj)
    obj.select_set(True)
    meshes.append(obj)
bpy.context.view_layer.objects.active = meshes[0]
assert bpy.ops.object.polygroups_prepare_unity(auto_lods=True) == {'FINISHED'}
names = {c.name for obj in meshes for c in obj.users_collection}
assert len(names) == 1 and next(iter(names)).endswith('_Collection') and '_LOD' not in next(iter(names)), names
collection = bpy.data.collections[next(iter(names))]
assert len(collection.objects) == 3 and collection.name == 'Stone_00_01_Collection', collection.name

# Rename Meshes with a new index renames the shared collection once; legacy per-LOD ones keep LOD.
with tempfile.TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'a.blend'))
    settings.unity_asset_index = '05'
    for obj in meshes:
        obj.select_set(True)
    assert bpy.ops.object.polygroups_rename_unity_meshes() == {'FINISHED'}
    assert collection.name == 'Stone_00_05_Collection', (collection.name, [o.name for o in meshes])
print('unity single collection ok')


