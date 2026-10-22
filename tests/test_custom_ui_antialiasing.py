"""Run in GUI Blender: verify fractional edge coverage on the real GPU."""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

import addon_utils
import bpy
import gpu
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('AIRETOPO_UI_VALIDATION_OUTPUT', tempfile.gettempdir()))
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / 'antialiasing_test.log'
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.custom_ui import icons, renderer


def validate():
    offscreen = None
    blend = gpu.state.blend_get()
    viewport = gpu.state.viewport_get()
    try:
        w, h = 640, 240
        offscreen = gpu.types.GPUOffScreen(w, h)
        with offscreen.bind(), gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.state.viewport_set(0, 0, w, h)
            gpu.matrix.load_matrix(Matrix.Identity(4))
            gpu.matrix.load_projection_matrix(Matrix((
                (2/w, 0, 0, -1), (0, 2/h, 0, -1),
                (0, 0, -1, 0), (0, 0, 0, 1))))
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(.08, .08, .08, 1))
            samples = []
            for row, scale in enumerate((.8, 1, 1.5, 2)):
                y = 12 + row * 56
                renderer.text(f'{scale:g}x', 12, y+12, 12)
                renderer.rect(60, y+5, 34*scale, 18*scale, (.55, .3, 1, 1), 9*scale)
                renderer.rect(60+17*scale, y+7*scale, 14*scale, 14*scale, (1, 1, 1, 1), 7*scale)
                for index, name in enumerate(('FILE_FOLDER', 'MOD_REMESH', 'MESH_CUBE',
                                              'CAMERA_DATA', 'TEXTURE', 'EDGE_SEAM', 'LOGO')):
                    x = 155 + index*65
                    size = 18*scale
                    icons.draw(name, x, y, size, (1, 1, 1, 1))
                    buf = fb.read_color(x-2, y-2, int(size+4), int(size+4), 4, 0, 'FLOAT')
                    buf.dimensions = int(size+4)**2*4
                    reds = list(buf)[::4]
                    assert min(reds) < .09 and max(reds) > .6, (scale, name)
                    assert any(.12 < red < .85 for red in reds), (scale, name, 'missing antialiasing')
                    samples.append((scale, name))
                # A circular thumb must have empty corners and a solid center.
                renderer.rect(604, y, 14*scale, 14*scale, (1, 1, 1, 1), 7*scale)
                size = int(14*scale)
                buf = fb.read_color(604, y, size, size, 4, 0, 'FLOAT')
                buf.dimensions = size*size*4
                pixels = list(buf)
                assert pixels[0] < .09
                assert pixels[((size//2)*size+size//2)*4] > .95
                assert any(.12 < red < .85 for red in pixels[::4])
            pixels = fb.read_color(0, 0, w, h, 4, 0, 'FLOAT')
            pixels.dimensions = w*h*4
            image = bpy.data.images.new('UI edge coverage', width=w, height=h, alpha=True)
            image.pixels.foreach_set(pixels)
            image.filepath_raw = str(OUT / 'antialiasing_samples.png')
            image.file_format = 'PNG'
            image.save()
            bpy.data.images.remove(image)
        LOG.write_text('ANTIALIASING_GPU_PASSED\n' + json.dumps(samples))
    except Exception:
        LOG.write_text(traceback.format_exc())
    finally:
        gpu.state.blend_set(blend)
        gpu.state.viewport_set(*viewport)
        if offscreen is not None:
            offscreen.free()
        renderer.clear()
        bpy.ops.wm.quit_blender()


bpy.app.timers.register(validate, first_interval=1)
