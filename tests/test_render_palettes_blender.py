import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy
import addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core.render_palettes import ensure_libraries, library_data, srgb_to_linear
from polygroups_generator.core.render_palettes import color_icon, clear_swatches
ensure_libraries()
s=bpy.context.scene.polygroups_render_settings
assert len(s.palette_groups)==1
p=s.palette_groups[0].palettes[0]
assert p.name=='Primary Colors' and len(p.colors)==7
p.color_index=3
assert bpy.ops.render.polygroups_palette_edit(action='APPLY')=={'FINISHED'}
assert abs(s.freestyle_line_color[1]-srgb_to_linear(217/255))<1e-6
assert bpy.ops.render.polygroups_palette_quick_apply(group_index=0, palette_index=0, color_index=4)=={'FINISHED'}
assert tuple(s.freestyle_line_color)==tuple(p.colors[4].color)
for lineset in bpy.context.view_layer.freestyle_settings.linesets:
    assert tuple(lineset.linestyle.color)==tuple(p.colors[4].color[:3])
if not bpy.app.background:
    assert color_icon(p.colors[3].color)>0
    clear_swatches()
assert p.color_index==4
assert bpy.ops.render.polygroups_palette_edit(action='ADD_GROUP')=={'FINISHED'}
assert bpy.ops.render.polygroups_palette_edit(action='ADD_PALETTE')=={'FINISHED'}
assert bpy.ops.render.polygroups_palette_edit(action='CAPTURE')=={'FINISHED'}
with TemporaryDirectory() as tmp:
    path=str(Path(tmp)/'library.json')
    before=library_data(s)
    assert bpy.ops.render.polygroups_palette_export(filepath=path)=={'FINISHED'}
    s.palette_groups.clear()
    assert bpy.ops.render.polygroups_palette_import(filepath=path)=={'FINISHED'}
    assert library_data(s)==before
    blend=str(Path(tmp)/'palettes.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    bpy.ops.wm.open_mainfile(filepath=blend)
    s=bpy.context.scene.polygroups_render_settings
    assert library_data(s)==before
    assert bpy.ops.render.polygroups_palette_edit(action='REMOVE_COLOR')=={'FINISHED'}
    assert bpy.ops.render.polygroups_palette_edit(action='REMOVE_PALETTE')=={'FINISHED'}
    assert bpy.ops.render.polygroups_palette_edit(action='REMOVE_GROUP')=={'FINISHED'}
    ensure_libraries()
    assert len(s.palette_groups)==1
addon_utils.disable(ROOT.name,default_set=False)
print('RENDER_PALETTES_TEST_PASSED')
