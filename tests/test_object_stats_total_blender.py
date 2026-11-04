"""The viewport stats overlay sums every selected mesh."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator import object_stats_overlay as overlay

bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.object
bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4)
sphere = bpy.context.object
cube_counts, sphere_counts = overlay.mesh_counts(cube), overlay.mesh_counts(sphere)
assert cube_counts == (6, 12, 12, 8), cube_counts

bpy.ops.object.select_all(action='DESELECT')
cube.select_set(True)
assert overlay.total_counts(overlay.selected_meshes(bpy.context)) == cube_counts
sphere.select_set(True)
objects = overlay.selected_meshes(bpy.context)
assert len(objects) == 2
assert overlay.total_counts(objects) == tuple(a + b for a, b in zip(cube_counts, sphere_counts))
print('object stats total ok')
