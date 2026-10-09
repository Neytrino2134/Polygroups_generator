"""Explicitly launch test panels; production never opens unrelated editors."""
import bpy

def _open_now(floating=False):
    w=bpy.context.window_manager.windows[0]
    a=next(a for a in w.screen.areas if a.type=='VIEW_3D')
    r=next(r for r in a.regions if r.type=='WINDOW')
    with bpy.context.temp_override(window=w,area=a,region=r):
        bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
        if floating:
            bpy.ops.wm.airetopo_custom_placement(placement='FLOATING')


def open_panel(floating=False):
    bpy.app.timers.register(lambda: _open_now(floating), first_interval=.1)
