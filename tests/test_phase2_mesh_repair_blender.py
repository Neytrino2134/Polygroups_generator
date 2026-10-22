"""Real repair before bake: both defects, only highest Retopo, shared data safe."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators import phase2_processing as phase2, safety_checks

context = bpy.context
settings = context.scene.polygroups_model_preparation_settings
bake = context.scene.polygroups_baking_settings
assert settings.phase2_mesh_auto_repair

bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1)
bm.normal_update()
face = max(bm.faces, key=lambda f: f.calc_center_median().z)
a, c, d = list(face.verts)
b = bm.verts.new(a.co * .4 + c.co * .4 + d.co * .2)
e = bm.verts.new(b.co * .8 + d.co * .2)
bm.faces.remove(face)
bm.faces.new((a, c, b, e))
bm.faces.new((a, e, b))
bm.faces.new((a, b, c, d))
edge = min(bm.edges, key=lambda edge: sum(v.co.z for v in edge.verts))
vertex = edge.verts[0]
_, duplicate = bmesh.utils.edge_split(edge, vertex, .5)
bmesh.ops.triangulate(bm, faces=list(duplicate.link_faces))
duplicate.co = vertex.co
uv = bm.loops.layers.uv.new('UVMap')
for face in bm.faces:
    for loop in face.loops:
        loop[uv].uv = (loop.vert.co.x, loop.vert.co.y)
data = bpy.data.meshes.new('Shared defective mesh')
bm.to_mesh(data)
bm.free()
original_counts = len(data.vertices), len(data.polygons)
collection = bpy.data.collections.new('Generated.009')
for name in ('Highpoly_Generated.009', 'Retopo_02_Highpoly_Generated.009', 'Retopo_12_Highpoly_Generated.009'):
    collection.objects.link(bpy.data.objects.new(name, data))

with TemporaryDirectory() as directory:
    source = Path(directory) / 'Working_Generated_009.blend'
    bpy.data.libraries.write(str(source), {collection})
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)
    bpy.data.meshes.remove(data)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / 'Working.blend'))
    real_bpy = safety_checks.bpy
    for enabled in (True, False):
        settings.phase2_mesh_auto_repair = enabled
        calls = []
        def fake_bake(*args, **kwargs):
            low = context.active_object
            high, highest = phase2.bake_pair(queue.collection)
            lower = next(obj for obj in queue.collection.objects if obj.name.startswith('Retopo_02_'))
            assert low == highest and low.name.startswith('Retopo_12_')
            assert set(context.selected_objects) == {high, low}
            assert (len(high.data.vertices), len(high.data.polygons)) == original_counts
            assert (len(lower.data.vertices), len(lower.data.polygons)) == original_counts
            counts = len(low.data.vertices), len(low.data.polygons)
            if enabled:
                # One folded pocket removes two vertices; the coincident edge
                # removes one more. Both fixes must precede the bake call.
                assert counts[0] == original_counts[0] - 3, (counts, original_counts)
                assert low.data != high.data and low.data != lower.data
            else:
                assert counts == original_counts
            calls.append(low.name)
            bake.bake_task_is_running = False
            bake.bake_task_stage = 'DONE'
            return {'FINISHED'}
        proxy = SimpleNamespace(app=real_bpy.app, ops=SimpleNamespace(object=SimpleNamespace(polygroups_bake_task=fake_bake)))
        queue = phase2.Phase2Queue(context, [(str(source), 'Generated.009')], True, True, print)
        queue.begin()
        with patch.object(safety_checks, 'bpy', proxy):
            for _ in range(8):
                queue.step(context)
                if queue.finished:
                    break
        assert queue.finished and len(calls) == 1, queue.results
        assert settings.phase2_done_count == 1 and settings.phase2_failed_count == 0

print('PHASE2_MESH_REPAIR_PASSED')
