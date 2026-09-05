import sys
from pathlib import Path
import bpy
import addon_utils
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
import polygroups_generator as addon
from polygroups_generator import custom_icons, tools
from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
for cycle in range(2):
    addon_utils.enable(root.name, default_set=False)
    assert len(custom_icons._handles) == 13
    previous_ids = dict(custom_icons._tool_icons)
    assert bpy.ops.wm.airetopo_update_icons() == {'FINISHED'}
    assert all(custom_icons._tool_icons[key] != value for key, value in previous_ids.items())
    for key in custom_icons._FILES:
        cls = getattr(tools, 'VIEW3D_WST_polygroups_' + key)
        value = ToolSelectPanelHelper._icon_value_from_icon_handle(cls.bl_icon)
        assert value > 0, (key, value)
        assert value == custom_icons._tool_icons[key]
        assert value != custom_icons.icon_kwargs(key)['icon_value']
    addon_utils.disable(root.name, default_set=False)
    assert not custom_icons._handles
    assert not custom_icons._tool_icons
    assert custom_icons._previews is None
print('CUSTOM ICONS PASS: 13 PNGs, toolbar resolution, two registration cycles')
bpy.ops.wm.quit_blender()
