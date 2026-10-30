"""Unreal presets fix the highest Retopo_XX (loose parts + Topology Guard); a render window that cannot close never stops the queue."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import render_window
from polygroups_generator.operators import phase2_processing as phase2
from polygroups_generator.operators import phase2_start_dialog as dialog

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings

# Both start presets turn the MID fixes on; only ZBrush guards its (rebaked) HIGH remesh.
for preset in ('UNREAL', 'UNREAL_ZBRUSH'):
    dialog.apply_start_preset(p, preset)
    assert p.phase2_mesh_auto_repair and p.phase2_remove_loose_parts and p.phase2_topology_guard_highest, preset
    assert p.phase2_smart_uv_repair, preset
    assert p.phase2_topology_guard_retopo01 == (preset == 'UNREAL_ZBRUSH'), preset
    assert p.phase2_run_fix_source and p.phase2_fix_source_before_mid, preset  # double fix is on by default

# Remove Small Loose Parts hits only the highest Retopo_XX.
collection = bpy.data.collections.new('Generated.001')
ctx.scene.collection.children.link(collection)
objects = {}
for number in (1, 3):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    speck = bmesh.ops.create_cube(bm, size=0.02)
    bmesh.ops.translate(bm, vec=(3, 0, 0), verts=speck['verts'])
    mesh = bpy.data.meshes.new(f'Retopo_{number:02d}_Highpoly_Generated.001')
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(mesh.name, mesh)
    collection.objects.link(obj)
    objects[number] = obj
queue = phase2.Phase2Queue.__new__(phase2.Phase2Queue)
queue.collection, queue.settings = collection, p
queue.report = lambda *args: None
assert queue.highest_mesh() == objects[3]
before = {number: len(obj.data.polygons) for number, obj in objects.items()}
p.phase2_remove_loose_parts = False
queue.remove_loose_parts(ctx)
assert len(objects[3].data.polygons) == before[3]
p.phase2_remove_loose_parts = True
queue.remove_loose_parts(ctx)
assert len(objects[3].data.polygons) == before[3] - 6 and len(objects[1].data.polygons) == before[1]

# Blender 5.x refuses a context override with a temporary screen: closing must not raise.
def refuse(**kwargs):
    raise TypeError("Overriding context with temporary screen isn't supported")
window = SimpleNamespace(screen=SimpleNamespace())
fake_context = SimpleNamespace(temp_override=refuse)
with patch.object(render_window.bpy, 'context', fake_context):
    assert render_window.close_window(window) is False
print('phase2 highest fixes ok')
