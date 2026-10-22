"""Launch GUI Blender: two real, sequential Phase 2 Cycles bakes."""
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators import phase2_processing as phase2

OUT = Path(os.environ.get('AIRETOPO_UI_VALIDATION_OUTPUT', tempfile.gettempdir()))
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / 'phase2_modal_test.log'
LOG.write_text('Starting\n')
directory = tempfile.TemporaryDirectory()
root = Path(directory.name)
state = {'started': time.monotonic(), 'launched': False}


def tick():
    try:
        window = bpy.context.window_manager.windows[0]
        area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
        region = next(region for region in area.regions if region.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            scene = bpy.context.scene
            settings = scene.polygroups_model_preparation_settings
            bake = scene.polygroups_baking_settings
            if not state['launched']:
                with LOG.open('a') as log:
                    log.write('Preparing fixture\n')
                bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
                for index in (7, 9):
                    col = bpy.data.collections.new(f'Generated.{index:03d}')
                    scene.collection.children.link(col)
                    for name, z in ((f'Highpoly_Generated.{index:03d}', .05),
                                    (f'Retopo_02_Highpoly_Generated.{index:03d}', 0),
                                    (f'Retopo_11_Highpoly_Generated.{index:03d}', 0)):
                        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, z))
                        obj = bpy.context.object
                        obj.name = name
                        for old in tuple(obj.users_collection):
                            old.objects.unlink(obj)
                        col.objects.link(obj)
                    bpy.data.libraries.write(str(root / f'Working_Generated_{index:03d}.blend'), {col})
                with LOG.open('a') as log:
                    log.write('Fixture saved\n')
                phase2.clear_generated_collections()
                bake.bake_resolution = 32
                bake.bake_base_color = False
                bake.bake_normal = True
                bake.auto_pack_uv_before_bake = False
                bake.use_smart_cage = bake.autogenerate_smart_cage = False
                bake.bake_artifact_mask = bake.bake_artifact_autofill = False
                scene.render.engine = 'CYCLES'
                scene.cycles.device = 'CPU'
                scene.cycles.samples = 1
                settings.phase2_auto_bake = settings.phase2_repair_artifacts = True
                settings.phase2_clear_generated = False
                assert bpy.ops.object.polygroups_phase2_restore('EXEC_DEFAULT') == {'RUNNING_MODAL'}
                with LOG.open('a') as log:
                    log.write('Phase 2 launched\n')
                state['launched'] = True
                return .2
            if settings.phase2_is_running:
                current = settings.phase2_status + ' / ' + bake.bake_task_stage
                if current != state.get('status'):
                    state['status'] = current
                    with LOG.open('a') as log:
                        log.write(current + '\n')
                if time.monotonic() - state['started'] > 90:
                    raise TimeoutError(settings.phase2_status)
                return .2
            assert phase2.ACTIVE_PHASE2 is None
            assert settings.phase2_done_count == 2 and settings.phase2_failed_count == 0, settings.phase2_status
            assert not bake.bake_artifact_mask and not bake.bake_artifact_autofill
            assert not bake.bake_task_is_running
            assert all(bpy.data.collections[f'Generated.{index:03d}'].color_tag == 'COLOR_02' for index in (1, 2))
            assert len(list(root.rglob('*_Normal.png'))) == 2
            assert len(list(root.rglob('*_Bake_ArtifactMask.png'))) == 2
            LOG.write_text('PHASE2_MODAL_PASSED\n' + settings.phase2_status)
        directory.cleanup()
        bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(traceback.format_exc())
        phase2.stop_phase2()
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1)
