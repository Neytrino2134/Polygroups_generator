"""Blender --background --factory-startup --python-exit-code 1 --python this_file.

Checks settings at engine dispatch without launching the Quad Remesher engine.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable('quad_remesher', default_set=True)
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.core.remesh_defaults import (
    DEFAULTS_APPLIED_KEY, apply_quad_remesher_defaults_once, get_remesh_preset_counts,
)
from polygroups_generator.core.remesh_job import RemeshJob

scene = bpy.context.scene
settings = scene.qremesher
scene[DEFAULTS_APPLIED_KEY] = False
settings.autodetect_hard_edges = True
apply_quad_remesher_defaults_once(scene)
assert not settings.autodetect_hard_edges
assert scene[DEFAULTS_APPLIED_KEY]
counts = dict(get_remesh_preset_counts(bpy.context))
assert counts['ULTRA'] == 100000
assert bpy.ops.object.polygroups_set_quad_count_preset(quad_count=counts['ULTRA']) == {'FINISHED'}
assert settings.target_count == 100000
model = scene.polygroups_model_preparation_settings
for name in ('file_import_remesh_preset', 'batch_remesh_preset',
             'batch_stage_3_remesh_preset', 'batch_stage_4_remesh_preset'):
    assert 'ULTRA' in model.bl_rna.properties[name].enum_items.keys()
preferences = bpy.context.preferences.addons[ROOT.name].preferences
preferences.remesh_ultra_count = 123456
assert dict(get_remesh_preset_counts(bpy.context))['ULTRA'] == 123456
preferences.remesh_ultra_count = 100000
settings.target_count = 1234
settings.use_materials = False
settings.symmetry_x = True
# This test isolates engine dispatch defaults. PolyGroup generation is covered
# by test_remesh_progress and requires an initialized undo stack.
scene.polygroups_model_preparation_settings.remesh_pregenerate_polygroups = False
calls = []


def engine_start(state, context):
    props = context.scene.qremesher
    assert not props.autodetect_hard_edges, 'hard edge detection reached the engine'
    assert props.target_count == 1234
    assert not props.use_materials and props.symmetry_x
    calls.append(context.active_object.name)
    state.IsRemeshing = True


backend = SimpleNamespace(doRemeshing_Start=engine_start)
bpy.ops.mesh.primitive_cube_add()
for _ in range(2):
    # Existing scene defaults and a manual change must not bypass enforcement.
    settings.autodetect_hard_edges = True
    apply_quad_remesher_defaults_once(scene)
    RemeshJob(backend, lambda *_: None).start(bpy.context)
    assert not settings.autodetect_hard_edges
assert len(calls) == 2
print('REMESH_HARD_EDGE_DEFAULT_TESTS_PASSED', flush=True)
