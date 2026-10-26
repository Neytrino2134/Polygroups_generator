"""GUI Blender: coordinator controls remain live through actual asynchronous rendering."""
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_pipeline as pipeline
from polygroups_generator.operators import auto_render as auto

OUT = Path(os.environ.get('AIRETOPO_UI_VALIDATION_OUTPUT', ROOT / 'user_data'))
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / 'phase2_pipeline_modal.log'
LOG.write_text('Starting\n')
directory = tempfile.TemporaryDirectory(dir=ROOT, prefix='test_pipeline_modal_')
root = Path(directory.name)
state = dict(started=time.monotonic(), launched=False, observed_render=False, paused=False, resumed=False)
real_configure = auto.configure_auto_render


def small_render(context):
    real_configure(context)
    context.scene.render.resolution_x = context.scene.render.resolution_y = 64
    context.scene.render.resolution_percentage = 100
    context.scene.cycles.device = 'CPU'
    context.scene.cycles.samples = 4


auto.configure_auto_render = small_render


def tick():
    try:
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            ctx = bpy.context
            p = ctx.scene.polygroups_model_preparation_settings
            if not state['launched']:
                bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
                for obj in list(bpy.data.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
                col = bpy.data.collections.new('Modal_01_01_Collection')
                ctx.scene.collection.children.link(col)
                bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
                obj = ctx.object; obj.name = 'SM_Modal_01_01_MID'
                for old in list(obj.users_collection): old.objects.unlink(obj)
                col.objects.link(obj)
                for key in ('restore', 'prepare', 'export', 'blend', 'zbrush', 'cleanup'):
                    setattr(p, 'phase2_run_' + key, False)
                p.phase2_run_render = True
                p.phase2_auto_textures = p.phase2_auto_multiview = p.phase2_auto_freestyle = False
                r = ctx.scene.polygroups_render_settings
                r.output_directory = str(root / 'Render')
                r.max_samples = 4; r.skip_existing = False; r.overwrite_existing = True
                assert bpy.ops.object.polygroups_start_phase2('EXEC_DEFAULT') == {'RUNNING_MODAL'}
                assert pipeline.ACTIVE_PIPELINE is not None
                state['launched'] = True
                return .1
            if bpy.app.is_job_running('RENDER'):
                state['observed_render'] = True
                if not state['paused']:
                    bpy.ops.object.polygroups_phase2_pipeline_control(action='PAUSE')
                    state['paused'] = True
            if p.phase2_pipeline_paused and not state['resumed']:
                assert not bpy.app.is_job_running('RENDER')
                bpy.ops.object.polygroups_phase2_pipeline_control(action='RESUME')
                state['resumed'] = True
            if p.phase2_pipeline_running:
                if time.monotonic() - state['started'] > 100:
                    raise TimeoutError(p.phase2_pipeline_status)
                return .1
            assert state['observed_render'] and state['paused'] and state['resumed'], state
            assert p.phase2_pipeline_state == 'COMPLETED', p.phase2_pipeline_status
            assert len(list((root / 'Render').rglob('*.png'))) >= 2
            assert pipeline.ACTIVE_PIPELINE is None
            assert not bpy.app.handlers.render_complete or not any(getattr(f, '__module__', '').endswith('phase2_pipeline_render') for f in bpy.app.handlers.render_complete)
            LOG.write_text('PHASE2_PIPELINE_MODAL_RENDER_PAUSE_RESUME_PASSED\n' + json.dumps(state))
        directory.cleanup()
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc())
        pipeline.stop_pipeline()
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1)
