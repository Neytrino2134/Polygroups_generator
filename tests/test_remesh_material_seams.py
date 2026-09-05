"""Blender background regression: shared boundary seams and remesh integration."""
import sys
from pathlib import Path
from types import SimpleNamespace
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
addon_utils.enable("quad_remesher", default_set=True)
from polygroups_generator.core.remesh_job import RemeshJob
from polygroups_generator.core.material_seams import mark_material_boundary_seams
from polygroups_generator.operators.import_queue import ImportQueue

context = bpy.context
mesh = bpy.data.meshes.new("Material boundary source")
mesh.from_pydata([(0,0,0), (1,0,0), (2,0,0), (0,1,0), (1,1,0), (2,1,0)], [],
                 [(0,1,4,3), (1,2,5,4)])
source = bpy.data.objects.new("Highpoly_Materials", mesh)
context.scene.collection.objects.link(source)
for name in ("Red", "Blue"):
    mesh.materials.append(bpy.data.materials.new(name))
mesh.polygons[1].material_index = 1

class Backend:
    @staticmethod
    def doRemeshing_Start(state, context):
        state.IsRemeshing = True
    @staticmethod
    def doRemeshing_Finish(state, context):
        result = source.copy()  # Deliberately shares the source mesh.
        context.scene.collection.objects.link(result)

settings = context.scene.polygroups_model_preparation_settings
assert not settings.remesh_auto_generate_seams
for enabled in (False, True):
    context.view_layer.objects.active = source
    settings.remesh_auto_generate_seams = enabled
    job = RemeshJob(Backend, lambda *args: None)
    job.start(context)
    result, = job.finish(context)
    assert sum(edge.use_seam for edge in result.data.edges) == int(enabled)
    assert not any(edge.use_seam for edge in source.data.edges)
    if enabled:
        shared = next(edge for edge in result.data.edges if set(edge.vertices) == {1,4})
        assert shared.use_seam
        assert mark_material_boundary_seams(result) == 0
        # Clearing transferred materials afterwards preserves generated seams.
        owner = SimpleNamespace(owned_meshes=set(), owned_gray_materials=set())
        ImportQueue.replace_remesh_material(owner, result)
        assert len(result.data.materials) == 1 and sum(e.use_seam for e in result.data.edges) == 1
        assert len(source.data.materials) == 2
        # Existing manual action works in Edit Mode with the same implementation.
        for edge in result.data.edges:
            edge.use_seam = False
        result.data.update()
        result.data.materials.append(mesh.materials[1])
        result.data.polygons[1].material_index = 1
        bpy.ops.object.mode_set(mode="EDIT")
        assert bpy.ops.mesh.polygroups_mark_material_boundaries_seam() == {"FINISHED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        assert sum(edge.use_seam for edge in result.data.edges) == 1
addon_utils.disable(ROOT.name, default_set=True)
addon_utils.disable("quad_remesher", default_set=True)
print("REMESH_MATERIAL_SEAMS_TESTS_PASSED")
