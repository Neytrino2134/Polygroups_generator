"""Foreground clipboard and native-panel validation using the production draw code."""
import sys, runpy, traceback
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]

class VIEW3D_PT_text_generation_test(bpy.types.Panel):
    bl_label='AI Generation | Text Generation'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Item'
    def draw(self,context):
        from polygroups_generator.ui_panels.ai import VIEW3D_PT_airetopo_ai_generation
        for provider in ('OPENAI','GOOGLE'):
            VIEW3D_PT_airetopo_ai_generation.draw_text_generation(self,context,self.layout,provider)

def finish():
    path=ROOT/'user_data/render_diagnostics/ai_text_generation.png'
    path.parent.mkdir(parents=True,exist_ok=True)
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        bpy.ops.screen.screenshot(filepath=str(path))
    print('AI_TEXT_NATIVE_UI_AND_CLIPBOARD_PASSED',flush=True)
    bpy.ops.wm.quit_blender()

def start():
    try:
        runpy.run_path(str(ROOT/'tests/test_ai_text_blender.py'),run_name='__main__')
        bpy.utils.register_class(VIEW3D_PT_text_generation_test)
        scene=bpy.context.scene
        scene.airetopo_openai_text_settings.model='gpt-6-luna'
        scene.airetopo_google_text_settings.model='gemini-3.5-flash-lite'
        for area in bpy.context.window_manager.windows[0].screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.show_region_ui=True
                area.spaces.active.region_quadviews
                area.spaces.active.show_region_toolbar=False
                area.spaces.active.region_3d.view_distance=10
                area.tag_redraw()
        bpy.app.timers.register(finish,first_interval=1)
    except Exception:
        print('AI_TEXT_UI_FAILED',traceback.format_exc(),flush=True)
        bpy.ops.wm.quit_blender()
bpy.app.timers.register(start,first_interval=.7)
