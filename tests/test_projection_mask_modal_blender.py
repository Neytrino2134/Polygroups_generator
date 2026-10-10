"""Factory GUI acceptance: actual async jobs, cancellation/reset and injected failure."""
from pathlib import Path
import json
import sys
import time
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
from polygroups_generator.operators import baking
from polygroups_generator.core.bake_projection import current_mask, META_PROP

mode = 'success'
stages = []
captured = []
real_step = baking.OBJECT_OT_polygroups_bake_task._step
def step(self, context):
    if not captured or captured[-1] != self:
        captured.append(self)
    stages.append(self.stage)
    if mode == 'failure' and self.stage == 'ARTIFACT_LAUNCH' and self.diagnostic_passes[0] == 'UV':
        self.projection.prepare('UV')
        raise RuntimeError('Injected failure after diagnostic material override')
    result = real_step(self, context)
    if mode == 'cancel' and self.stage == 'ARTIFACT_WAIT' and self.projection.kind == 'HIT':
        self.cancel_requested = True
        self.settings.bake_task_is_running = False  # Exercise Reset while OBJECT_BAKE is active.
    return result
baking.OBJECT_OT_polygroups_bake_task._step = step
addon_utils.enable(ROOT.name, default_set=False)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2)
low = bpy.context.object
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -.2))
high = bpy.context.object
high.rotation_euler.x = 3.141592653589793
mat = bpy.data.materials.new('Original modal source')
mat.use_nodes = True
high.data.materials.append(mat)
settings = bpy.context.scene.polygroups_baking_settings
settings.bake_resolution = 128
settings.bake_base_color = False
settings.bake_normal = True
settings.use_auto_cage = False
settings.autogenerate_smart_cage = False
settings.auto_pack_uv_before_bake = False
settings.disable_highpoly_after_bake = False
settings.auto_save_textures_after_bake = False
settings.cage_extrusion = .1
settings.ray_distance = 1
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
started = time.monotonic()
modes = ['success', 'autofill', 'cancel', 'failure']

def launch():
    global mode
    mode = modes.pop(0)
    high.rotation_euler.x = 0 if mode == 'autofill' else 3.141592653589793
    high.location.x = 2 if mode == 'autofill' else 0
    settings.bake_base_color = mode == 'autofill'
    baking._select_sources_and_target(bpy.context, [high], low)
    with bpy.context.temp_override(area=area, region=region):
        assert bpy.ops.object.polygroups_bake_task('INVOKE_DEFAULT', prepare_materials=True) == {'RUNNING_MODAL'}

def poll():
    try:
        assert time.monotonic() - started < 90, 'GUI bake timeout'
        expected = {'success': 'DONE', 'autofill': 'DONE', 'cancel': 'CANCELLED', 'failure': 'FAILED'}[mode]
        if settings.bake_task_stage != expected:
            return .15
        assert not bpy.app.is_job_running('OBJECT_BAKE')
        assert high.active_material == mat and high.material_slots[0].link == 'DATA'
        assert scene.render.bake.margin == settings.bake_margin
        assert not [i for i in bpy.data.images if i.name.startswith('Projection private')]
        normal = bpy.data.images[low[baking.BAKE_NORMAL_IMAGE_PROP]]
        mask = current_mask(low, normal)
        assert (mask is not None) == (mode in ('success', 'autofill'))
        if mode == 'autofill':
            textures = json.loads(mask[META_PROP])['autofill']['textures']
            for kind in ('normal', 'base_color'):
                assert textures[kind]['filled'] > 0 and textures[kind]['unfilled'] == 0
        assert not settings.bake_task_is_running
        print('PROJECTION_MODAL_CASE_OK', mode, flush=True)
        if modes:
            launch()
            return .15
        assert 'ARTIFACT_WAIT' in stages and 'ARTIFACT_CLASSIFY' in stages
        print('PROJECTION_MODAL_TESTS_OK', flush=True)
        bpy.ops.wm.quit_blender()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        import os
        os._exit(1)
    return None

def begin():
    launch()
    bpy.app.timers.register(poll, first_interval=.2)
    return None
bpy.app.timers.register(begin, first_interval=.5)
