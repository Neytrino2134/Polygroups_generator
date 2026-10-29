"""HIGH remesh feeds Phase 2 resculpt/rebake and preserves the new mesh."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_processing as phase, phase2_mid_remesh
from polygroups_generator.custom_ui.schema import capture

context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
bake = context.scene.polygroups_baking_settings
settings.phase2_mid_remesh = False
settings.phase2_resculpt_retopo01 = True
settings.phase2_high_remesh_before_resculpting = True
settings.phase2_autobake_retopo01 = True
settings.phase2_keep_retopo01 = False
settings.phase2_delete_lower_retopo = True
settings.phase2_delete_high_after_bake = True
settings.phase2_blend_export_generated = False
settings.phase2_mesh_auto_repair = False
settings.phase2_repair_after_resculpt = False
settings.phase2_topology_guard_retopo01 = False
settings.phase2_repack_after_repair = False
context.scene.polygroups_resculpting_settings.multires_levels = 0
settings.phase2_show_restore = True
panel = capture(context, 1)
assert not panel.errors, panel.errors
assert 'phase2_high_remesh_before_resculpting' in {
    binding[2] for binding in panel.bindings.values() if binding[0] == 'property'
}

collection = bpy.data.collections.new('Generated.777')
context.scene.collection.children.link(collection)
for name in ('Highpoly_Generated.777', 'Retopo_01_Highpoly_Generated.777',
             'Retopo_12_Highpoly_Generated.777'):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)],
                     [], [(0, 1, 2, 3)])
    mesh.uv_layers.new()
    collection.objects.link(bpy.data.objects.new(name, mesh))
context.view_layer.update()
old = bpy.data.objects['Retopo_01_Highpoly_Generated.777']
old_name = old.name
generated = []


class FakeHighRemesh:
    def __init__(self, _context, owner, _report, *, source, preset, result_name):
        assert owner == collection and source == old and preset == 'HIGH'
        assert result_name == 'Resculpting_01_Highpoly_Generated.777'
        self.source, self.result_name = source, result_name
        self.job = SimpleNamespace(pipeline_progress=0)

    def start(self, _context):
        result = self.source.copy()
        result.data = self.source.data.copy()
        result.name = self.result_name
        collection.objects.link(result)
        self.source.hide_set(True)
        self.source.hide_viewport = self.source.hide_render = True
        generated.append(result)

    def poll(self):
        return True, 1.0

    def finish(self, _context):
        return generated[-1]

    def abort(self):
        pass


real_bpy = bpy
bake_targets = []


def fake_bake(*_args, **_kwargs):
    target = context.active_object
    bake_targets.append(target.name)
    if len(bake_targets) == 2:
        assert target == generated[-1]
        assert target.get('polygroups_bake_output_suffix') == 'Resculpting_01'
        assert context.scene.polygroups_model_preparation_settings.phase2_high_remesh_before_resculpting
    bake.bake_task_is_running = False
    bake.bake_task_stage = 'DONE'
    return {'FINISHED'}


proxy = SimpleNamespace(data=real_bpy.data,
    ops=SimpleNamespace(object=SimpleNamespace(
        polygroups_setup_resculpting=real_bpy.ops.object.polygroups_setup_resculpting,
        polygroups_checked_prepare_and_bake=fake_bake)))
queue = phase.Phase2Queue(context, [('mock.blend', collection.name)], True, False, lambda *_: None)
queue.begin()
with patch.object(phase, 'restore_collection', return_value=collection), \
     patch.object(phase2_mid_remesh, 'Phase2MidRemesh', FakeHighRemesh), \
     patch.object(phase, 'bpy', proxy):
    for _ in range(15):
        queue.step(context)
        if queue.finished:
            break
assert queue.finished and queue.results[-1][1] == '', queue.results
assert len(bake_targets) == 2
assert generated[-1].name in bpy.data.objects
assert old_name not in bpy.data.objects
assert 'Highpoly_Generated.777' not in bpy.data.objects
assert 'Retopo_12_Highpoly_Generated.777' in bpy.data.objects
assert generated[-1].hide_render and generated[-1].hide_viewport

# Manual lower-Retopo cleanup keeps the resculpted source regardless of stage 01.
replacement = generated[-1].copy()
replacement.data = generated[-1].data.copy()
replacement.name = old_name
collection.objects.link(replacement)
assert bpy.ops.object.polygroups_phase2_clear_lower_retopo() == {'FINISHED'}
assert old_name not in bpy.data.objects
assert generated[-1].name in bpy.data.objects
print('PHASE2_HIGH_RESCULPT_CHAIN_OK', flush=True)
