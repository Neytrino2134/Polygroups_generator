import sys,json
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from polygroups_generator.core import render_palettes as rp
with TemporaryDirectory() as tmp:
    rp.LIBRARY_PATH=Path(tmp)/'shared.json'
    addon_utils.enable(ROOT.name,default_set=False)
    rp.ensure_libraries()
    s=bpy.context.scene.polygroups_render_settings
    assert len(s.palette_groups)==1
    old=Path(tmp)/'old.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(old))
    assert bpy.ops.render.polygroups_palette_edit(action='ADD_GROUP')=={'FINISHED'}
    s.palette_groups[-1].name='Global Custom'
    rp.flush_library()
    assert json.loads(rp.LIBRARY_PATH.read_text())['groups'][-1]['name']=='Global Custom'
    # Opening the old file must load the updated external catalog.
    bpy.ops.wm.open_mainfile(filepath=str(old))
    s=bpy.context.scene.polygroups_render_settings
    assert s.palette_groups[-1].name=='Global Custom'
    s.palette_group_index=len(s.palette_groups)-1
    assert bpy.ops.render.polygroups_palette_edit(action='ADD_PALETTE')=={'FINISHED'}
    assert bpy.ops.render.polygroups_palette_edit(action='ADD_COLOR')=={'FINISHED'}
    g,p,c=rp.selected(s)
    c.color=(.25,.5,.75,1)
    c.name='Persistent Color'
    rp.flush_library()
    another=bpy.data.scenes.new('Other Scene')
    rp.ensure_libraries()
    assert rp.library_data(another.polygroups_render_settings)==rp.library_data(s)
    saved=json.loads(rp.LIBRARY_PATH.read_text())
    assert saved['groups'][-1]['palettes'][0]['colors'][0]['name']=='Persistent Color'
    addon_utils.disable(ROOT.name,default_set=False)
print('GLOBAL_PALETTE_LIBRARY_TEST_PASSED')
