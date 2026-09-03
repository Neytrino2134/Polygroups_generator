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
    DEFAULTS_APPLIED_KEY, apply_quad_remesher_defaults_once,
)
from polygroups_generator.core.remesh_job import RemeshJob

scene = bpy.context.scene
settings = scene.qremesher
scene[DEFAULTS_APPLIED_KEY] = False
settings.autodetect_hard_edges = True
apply_quad_remesher_defaults_once(scene)
assert not settings.autodetect_hard_edges
assert scene[DEFAULTS_APPLIED_KEY]
settings.target_count = 1234
settings.use_materials = False
settings.symmetry_x = True
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
