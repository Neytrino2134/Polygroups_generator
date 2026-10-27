"""Native draw smoke test for the new Start Phase 2 folds."""
from pathlib import Path
import sys
import traceback
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
assert addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core.phase2_progress import draw_start

draws = {}
errors = []
phase = 0


class VIEW3D_PT_rename_final_test(bpy.types.Panel):
    bl_label = 'Phase 2 / Start Phase 2'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'

    def draw(self, context):
        try:
            draw_start(self.layout, context, context.scene.polygroups_model_preparation_settings)
            draws[phase] = draws.get(phase, 0) + 1
        except Exception:
            errors.append(traceback.format_exc())


def advance():
    global phase
    p = bpy.context.scene.polygroups_model_preparation_settings
    if phase == 3:
        print('RENAME_FINAL_NATIVE_UI_PASSED' if all(draws.get(i) for i in range(1, 4)) and not errors
              else 'RENAME_FINAL_NATIVE_UI_FAILED ' + str(errors), flush=True)
        bpy.ops.wm.quit_blender()
        return
    phase += 1
    p.phase2_show_rebake = phase in {2, 3}
    p.phase2_show_rename_final = phase == 3
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            area.tag_redraw()
    return .5


bpy.utils.register_class(VIEW3D_PT_rename_final_test)
bpy.app.timers.register(advance, first_interval=.5)
