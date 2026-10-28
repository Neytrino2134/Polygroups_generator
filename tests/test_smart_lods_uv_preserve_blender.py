"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)


def key(co, uv):
    return tuple(round(value, 5) for value in co) + (round(uv.x, 5), round(uv.y, 5))


def corners(mesh):
    uv = mesh.uv_layers.active.data
    return {key(mesh.vertices[loop.vertex_index].co, uv[loop.index].uv) for loop in mesh.loops}


def remove_lods(count):
    for index in range(count):
        obj = bpy.data.objects[f"Mesh.004.LOD{index}"]
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_monkey_add()
source = bpy.context.object
source.name = "Mesh.004"
subdivision = source.modifiers.new("sub", "SUBSURF")
subdivision.levels = 2
bpy.ops.object.modifier_apply(modifier=subdivision.name)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
bpy.ops.uv.seams_from_islands()
bpy.ops.object.mode_set(mode="OBJECT")
original = corners(source.data)

settings = bpy.context.scene.polygroups_mesh_finalization_settings
prep = bpy.context.scene.polygroups_model_preparation_settings
assert settings.smart_lods_decimate_method == "UV_PRESERVE"
assert settings.smart_lods_uv_seam_mode == "LOCK"
assert prep.batch_smart_lods_decimate_method == "UV_PRESERVE"
settings.smart_lods_auto_arrange = False
settings.smart_lods_final_decimate = False
settings.smart_lods_count = 3
targets = (6000, 3000, 1500)
for index, target in enumerate(targets, 1):
    setattr(settings, f"smart_lods_target_{index}", target)

# Every LOD corner is an original (position, UV) pair: no texture sliding, no re-unwrap.
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
for index, target in enumerate(targets):
    lod = bpy.data.objects[f"Mesh.004.LOD{index}"]
    assert 0 < len(lod.data.loop_triangles) <= target, (index, len(lod.data.loop_triangles))
    assert len(lod.modifiers) == 0
    assert corners(lod.data) <= original, index
remove_lods(3)

# A budget locked seams cannot reach relaxes protection, still with exact UVs.
settings.smart_lods_count = 1
settings.smart_lods_target_1 = 400
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
lod = bpy.data.objects["Mesh.004.LOD0"]
assert len(lod.data.loop_triangles) <= 400, len(lod.data.loop_triangles)
assert corners(lod.data) <= original
remove_lods(1)

# Smart Decimate stays selectable and re-unwraps as before.
settings.smart_lods_decimate_method = "SMART_DECIMATE"
settings.smart_lods_target_1 = 3000
assert bpy.ops.object.polygroups_generate_smart_lods() == {"FINISHED"}
lod = bpy.data.objects["Mesh.004.LOD0"]
assert len(lod.data.loop_triangles) <= 3000
assert not corners(lod.data) <= original, "Blender path is expected to move UVs"
remove_lods(1)
print("SMART_LODS_UV_PRESERVE_TEST_PASSED")
