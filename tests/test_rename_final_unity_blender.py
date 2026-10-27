"""Unity per-level collections remain one asset during rename and JSON statistics."""
import json
from pathlib import Path
import sys
import tempfile
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
assert addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.services import fab_media
from polygroups_generator.custom_ui.schema import capture

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings
assert not p.phase2_show_rebake and not p.phase2_show_rename_final
panel = capture(ctx, 1)
assert not panel.errors, panel.errors
props = {binding[2] for binding in panel.bindings.values() if binding[0] == 'property'}
assert {'phase2_show_rebake', 'phase2_show_rename_final', 'phase2_rename_asset',
        'phase2_rename_name_index', 'phase2_rename_version_index', 'phase2_rename_json'} <= props
operators = {binding[1] for binding in panel.bindings.values() if binding[0] == 'operator'}
assert {'object.polygroups_rebake_final_mesh', 'object.polygroups_rename_final_meshes'} <= operators
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    cols, objects = [], []
    for level in range(3):
        col = bpy.data.collections.new(f'Old_01_01_LOD{level}_Collection')
        ctx.scene.collection.children.link(col)
        bpy.ops.mesh.primitive_cube_add()
        obj = ctx.object
        obj.name = 'Old_01_01' + (f'.LOD{level}' if level else '')
        obj['unity_prepared'] = True
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        col.objects.link(obj)
        objects.append(obj)
        cols.append(col)
    source = fab_media.inventory(ctx)
    assert len(source['assets']) == 1
    assert fab_media.measured_fields(source)['assetsQuantityLine2'] == '1 STATIC MESHES'
    p.phase2_run_engine = 'UNITY'
    p.phase2_rename_asset = 'Unity Renamed'
    p.phase2_rename_name_index = '02'
    p.phase2_rename_version_index = '03'
    p.phase2_rename_fbx = p.phase2_rename_blend = True
    assert bpy.ops.object.polygroups_rename_final_meshes() == {'FINISHED'}
    assert p.phase2_rename_status == 'Renamed 1 assets | UNITY', p.phase2_rename_status
    assert [col.name for col in cols] == [f'Unity_Renamed_02_03_LOD{i}_Collection' for i in range(3)]
    assert objects[0].name == 'Unity_Renamed_02_03' and objects[2].name == 'Unity_Renamed_02_03.LOD2'
    assert len(list((root / '!Unity').rglob('*.fbx'))) == 3
    info = json.loads((root / '!Unity/MeshInfo.json').read_text(encoding='utf-8'))
    assert len(info['assets']) == 1 and info['assets'][0]['name'] == 'Unity_Renamed_02_03'
    assert (root / '!Blend/Unity_Renamed_02_03.blend').is_file()
    assert len(fab_media.inventory(ctx)['assets']) == 1
print('RENAME_FINAL_UNITY_AND_FOLDS_PASSED')
