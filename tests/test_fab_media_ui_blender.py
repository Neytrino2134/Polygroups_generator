"""Native FAB JSON panel draw smoke test; run in a factory-startup GUI process."""
from pathlib import Path
import sys
import traceback
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
assert addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.ui_panels.ai import VIEW3D_PT_airetopo_ai_generation
from polygroups_generator.services import fab_media as media

draws = []


class VIEW3D_PT_fab_json_test(bpy.types.Panel):
    bl_label = '11 | JSON generation · FAB Media Gallery'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'

    def draw(self, context):
        try:
            VIEW3D_PT_airetopo_ai_generation.draw_json_generation(self, context, self.layout)
            draws.append(True)
        except Exception:
            print('FAB_JSON_UI_DRAW_FAILED', traceback.format_exc(), flush=True)
            draws.append(False)


def finish():
    output = ROOT / 'user_data/render_diagnostics/fab_json_generation.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.screen.screenshot(filepath=str(output))
    print('FAB_JSON_NATIVE_UI_PASSED' if draws and all(draws) else 'FAB_JSON_NATIVE_UI_FAILED', flush=True)
    bpy.ops.wm.quit_blender()


def start():
    bpy.utils.register_class(VIEW3D_PT_fab_json_test)
    s = bpy.context.scene.airetopo_fab_media_settings
    s.seriesName = 'Halloween series'
    s.mainHeadline1, s.mainHeadline2 = 'Tomb', 'Stones'
    s.assetHeadline = 'GraveStone'
    s.assetsQuantityLine1, s.assetsQuantityLine2 = '12 UNIQUE ASSETS', '24 STATIC MESHES'
    s.averagePolycountLow, s.averagePolycountMid = '~ 2K', '~ 3.8K'
    s.minMaxPolycountLow, s.minMaxPolycountMid = '~ 2K–2K', '~ 2.8K–7.9K'
    s.last_status = 'JSON ready | gpt-6.1-terra (UI preview)'
    s.result_text = bpy.data.texts.new('FAB JSON UI Preview')
    s.result_text.write(media.dumps(media.template()))
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            area.tag_redraw()
    bpy.app.timers.register(finish, first_interval=1.5)


bpy.app.timers.register(start, first_interval=.5)
