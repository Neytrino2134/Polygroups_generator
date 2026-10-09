"""Real GUI/GPU validation in an isolated factory-startup Blender process.

Launch without --background. Captures the actual POST_PIXEL framebuffer.
"""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import tempfile
import bpy
import addon_utils
import gpu
bpy.context.preferences.use_preferences_save = False

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('AIRETOPO_UI_VALIDATION_OUTPUT',ROOT / 'docs' / 'custom_ui'))
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / 'gpu_test.log'
LOG.write_text('Starting\n')
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.custom_ui import lifecycle, renderer
prefs = bpy.context.preferences.addons[ROOT.name].preferences
prefs.enable_dev_mode = False
prefs.custom_ui_presentation = 'FLOATING'
prefs.ui_mode = 'CUSTOM'
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
state = {'step': 0, 'frames': 0, 'time': time.monotonic(), 'capture': None, 'results': []}


def snapshot():
    if bpy.context.area != area or bpy.context.region != region:
        return
    state['frames'] += 1
    if not state['capture']:
        return
    try:
        framebuffer = gpu.state.active_framebuffer_get()
        session = state['session']
        x,top,width,height = session.geometry(region)
        x,y,width,height = int(x),int(top-height),int(width),int(height)
        pixels = framebuffer.read_color(x, y, width, height, 4, 0, 'FLOAT')
        pixels.dimensions = width * height * 4
        image = bpy.data.images.new('Custom UI GPU Capture', width=width, height=height, alpha=True)
        image.pixels.foreach_set(pixels)
        image.filepath_raw = str(OUT / state['capture'])
        image.file_format = 'PNG'
        image.save()
        bpy.data.images.remove(image)
        LOG.write_text(LOG.read_text() + 'Captured '+state['capture']+'\n')
        state['capture'] = None
    except Exception:
        LOG.write_text(LOG.read_text() + traceback.format_exc())
        state['failed'] = True


handle = bpy.types.SpaceView3D.draw_handler_add(snapshot, (), 'WINDOW', 'POST_PIXEL')


def finish():
    bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
    addon_utils.disable(ROOT.name)
    bpy.ops.wm.quit_blender()


def step():
    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            if state.get('failed'):
                finish()
                return None
            if state['step'] == 0:
                session = lifecycle.SESSIONS.get(lifecycle.key_for(bpy.context))
                if not session:
                    if time.monotonic() - state['time'] > 10:
                        raise RuntimeError('Overlay failed to start')
                    return .5
                state['session'] = session
                state['step'] = 1
            s = state['session']
            if s.closed:
                raise RuntimeError('GPU renderer failed: '+s.note)
            if state['results'] and state['step']<=14:
                state['results'][-1]['draw_ms'] = getattr(s,'draw_ms',None)
                state['results'][-1]['capture_ms'] = getattr(s,'capture_ms',None)
            index = state['step']-1
            if index < 13:
                s.select(index)
                s.refresh(bpy.context)
                assert not s.model.errors, s.model.errors
                for node in lifecycle.walk(s.model.node):
                    if node['kind'] == 'group':
                        binding = s.model.bindings[node['id']]
                        setattr(binding[1], binding[2], True)
                s.refresh(bpy.context)
                before = time.perf_counter()
                renderer.height(s.model.node, 620, s.scale)
                state['results'].append({'section':index+1, 'layout_ms':(time.perf_counter()-before)*1000})
                if index in (0, 3, 9, 12):
                    state['capture'] = f'gpu_section_{index+1:02d}.png'
                state['step'] += 1
                area.tag_redraw()
                return .8
            if index == 13:
                prefs.custom_ui_scale = 1.5
                s.width = 520
                state['capture'] = 'gpu_narrow_scale_1_5.png'
                state['step'] += 1
                area.tag_redraw()
                return 1
            if index == 14:
                prefs.custom_ui_scale = 2
                state['capture'] = 'gpu_scale_2.png'
                state['step'] += 1
                area.tag_redraw()
                return 1
            if index == 15:
                state['idle_frames']=state['frames']
                state['step']+=1
                return 1.5
            idle=state['frames']-state['idle_frames']
            assert idle<=8, f'Unexpected continuous redraw: {idle} frames in 1.5 seconds'
            state['results'][-1]['idle_redraws_in_1_5_seconds']=idle
            assert state['frames'] > 10
            assert s.hits
            prefs.ui_mode = 'CLASSIC'
            lifecycle.cleanup()
            assert not lifecycle.SESSIONS
            (OUT / 'gpu_validation.json').write_text(json.dumps(state['results'], indent=2))
            LOG.write_text(LOG.read_text()+'CUSTOM_UI_GPU_TESTS_PASSED\n')
            finish()
            return None
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc())
        finish()
        return None


bpy.app.timers.register(step, first_interval=1)
