"""Installed Quad Remesher HIGH adapter: seams, name, UV and settings restore."""
import math
import sys
import time
from pathlib import Path
from unittest.mock import patch

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable('quad_remesher', default_set=False)
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_mid_remesh
from polygroups_generator.operators.phase2_mid_remesh import Phase2MidRemesh
from polygroups_generator.pin_edges import pin_layer
from polygroups_generator.core.mesh_ngons import ngon_count

context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
settings.remesh_pregenerate_polygroups = False
quad = context.scene.qremesher
original_target = quad.target_count = 789
seams = context.scene.polygroups_seam_preparation_settings
original_angle = seams.smart_seam_angle_limit = math.radians(47)

collection = bpy.data.collections.new('Generated.778')
context.scene.collection.children.link(collection)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12)
source = context.object
source.name = 'Retopo_01_Highpoly_Generated.778'
for owner in list(source.users_collection):
    owner.objects.unlink(source)
collection.objects.link(source)
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(source.data)
shared_quad_edge = next(edge for edge in bm.edges
                        if len(edge.link_faces) == 2 and all(len(face.verts) == 4 for face in edge.link_faces))
bmesh.ops.dissolve_edges(bm, edges=[shared_quad_edge], use_verts=False)
pins = pin_layer(bm, True)
for edge in bm.edges:
    edge.seam = True
    edge[pins] = 1
for face in bm.faces:
    for loop in face.loops:
        loop[bm.loops.layers.uv.active].pin_uv = True
bmesh.update_edit_mesh(source.data)
bpy.ops.object.mode_set(mode='OBJECT')
assert ngon_count(source.data) == 1

job = Phase2MidRemesh(context, collection, print, source=source, preset='HIGH',
                      result_name='Resculpting_01_Highpoly_Generated.778')
with patch.object(phase2_mid_remesh, 'get_remesh_preset_counts',
                  return_value=(('LOW', 500), ('MID', 700), ('HIGH', 1000))):
    job.start(context)
assert quad.target_count == 1000
assert ngon_count(source.data) == 0
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    done, _progress = job.poll()
    if done:
        break
    time.sleep(.1)
else:
    job.abort()
    raise AssertionError('HIGH Remesh timed out')
result = job.finish(context)
assert result.name == 'Resculpting_01_Highpoly_Generated.778'
assert result != source and result.data.uv_layers.active is not None
assert quad.target_count == original_target
assert abs(seams.smart_seam_angle_limit - original_angle) < 1e-6
assert not any(item.value for item in source.data.attributes['polygroups_pin_edge'].data)
assert not any(loop.pin_uv for loop in source.data.uv_layers.active.data)
assert not all(edge.use_seam for edge in source.data.edges)
print('PHASE2_NATIVE_HIGH_REMESH_OK', flush=True)
