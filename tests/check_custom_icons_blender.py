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
    previous_ids = dict(custom_icons._tool_icons)
    assert bpy.ops.wm.airetopo_update_icons() == {'FINISHED'}
    assert len(custom_icons._handles) == len(custom_icons._FILES) == 21
    assert all(custom_icons._tool_icons[key] != value for key, value in previous_ids.items())
    for key in custom_icons._FILES:
        value = ToolSelectPanelHelper._icon_value_from_icon_handle(custom_icons.tool_icon(key, ""))
        assert value > 0, (key, value)
        assert value == custom_icons._tool_icons[key]
        assert value != custom_icons.icon_kwargs(key)['icon_value']
    settings = bpy.context.scene.polygroups_seam_preparation_settings
    settings.seam_path_pin = True
    settings.seam_eraser_clear_mode = 'PINNED'
    settings.smart_seam_pin_generated = True
    assert tools.VIEW3D_WST_polygroups_connect_vertex_seam._bl_tool.icon == custom_icons.tool_icon('connect_vertex_seam_pin', '')
    assert tools.VIEW3D_WST_polygroups_edge_seam_path._bl_tool.icon == custom_icons.tool_icon('edge_seam_path_pin', '')
    assert tools.VIEW3D_WST_polygroups_seam_eraser._bl_tool.icon == custom_icons.tool_icon('seam_eraser_pin', '')
    assert tools.VIEW3D_WST_polygroups_edge_seam_eraser._bl_tool.icon == custom_icons.tool_icon('edge_seam_eraser_pin', '')
    assert tools.VIEW3D_WST_polygroups_smart_seams_generator._bl_tool.icon == custom_icons.tool_icon('smart_seams_generator_pin', '')
    addon_utils.disable(root.name, default_set=False)
    assert not custom_icons._handles
    assert not custom_icons._tool_icons
    assert custom_icons._previews is None
print('CUSTOM ICONS PASS: 21 PNGs, dynamic pin variants, two registration cycles')
bpy.ops.wm.quit_blender()
