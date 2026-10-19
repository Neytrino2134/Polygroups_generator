"""Material Settings binds the active material's native camera culling flag."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.custom_ui.schema import capture, walk
from polygroups_generator import ui

section = ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_render)
obj = bpy.data.objects['Cube']
obj.data.materials.clear()
materials = [bpy.data.materials.new('FrontOnly'), bpy.data.materials.new('DoubleSided')]
for material in materials:
    obj.data.materials.append(material)

def model():
    result = capture(bpy.context, section)
    assert not result.errors, result.errors
    return result

for slot in (0, 1):
    obj.active_material_index = slot
    result = model()
    groups = [n['id'] for n in walk(result.node) if n['kind'] == 'group']
    scene = next(i for i, key in enumerate(groups) if key.endswith('.topic_render_6'))
    material_group = next(i for i, key in enumerate(groups) if key.endswith('.topic_render_10'))
    arrange = next(i for i, key in enumerate(groups) if key.endswith('.topic_render_7'))
    assert scene < material_group < arrange
    binding = next(b for b in result.bindings.values() if b[0] == 'property' and b[2] == 'use_backface_culling')
    assert binding[1] == materials[slot]
    setattr(binding[1], binding[2], slot == 0)
assert materials[0].use_backface_culling and not materials[1].use_backface_culling
# No active material and no selected mesh must remain valid panel states.
obj.data.materials.clear()
assert not any(b[0] == 'property' and b[2] == 'use_backface_culling' for b in model().bindings.values())
bpy.ops.object.select_all(action='DESELECT')
model()
with TemporaryDirectory() as temp:
    path = Path(temp) / 'MaterialSettings.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    # Keep unused test materials in the saved file.
    for material in materials:
        material.use_fake_user = True
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))
    assert bpy.data.materials['FrontOnly'].use_backface_culling
    assert not bpy.data.materials['DoubleSided'].use_backface_culling
print('RENDER_MATERIAL_SETTINGS_PASSED')
