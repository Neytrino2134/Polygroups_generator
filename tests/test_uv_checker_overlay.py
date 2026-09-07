"""Blender background regression for the Solid-mode UV checker overlay."""
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.uv_checker_overlay import _cache_key, _sync_edit_mesh, checker_geometry


settings = bpy.context.scene.polygroups_seam_finalization_settings
assert settings.show_checker_solid_mode is False
assert abs(settings.checker_overlay_opacity - 0.35) < 1.0e-6

mesh = bpy.data.meshes.new("UV Checker Overlay Test Mesh")
mesh.from_pydata(
    [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
    [],
    [(0, 1, 2, 3)],
)
uv_layer = mesh.uv_layers.new(name="UVMap")
for loop, uv in zip(uv_layer.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
    loop.uv = uv
obj = bpy.data.objects.new("UV Checker Overlay Test", mesh)
bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

positions, uvs = checker_geometry(obj)
assert len(positions) == 6
assert len(uvs) == 6
assert {tuple(uv) for uv in uvs} == {(0, 0), (1, 0), (1, 1), (0, 1)}
original_key = _cache_key(obj)

# Reproduce a UV Editor-only change while the object is in Edit Mode. The
# overlay must see it even when the dependency graph does not flag geometry.
bpy.ops.object.mode_set(mode="EDIT")
bm = bmesh.from_edit_mesh(mesh)
bm.faces.ensure_lookup_table()
bm_uv = bm.loops.layers.uv.active
bm.faces[0].loops[0][bm_uv].uv.x += 0.375
bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
_sync_edit_mesh(obj)
assert _cache_key(obj) != original_key

bpy.ops.object.mode_set(mode="OBJECT")
bpy.data.objects.remove(obj, do_unlink=True)
print("UV_CHECKER_OVERLAY_TEST_PASSED")
