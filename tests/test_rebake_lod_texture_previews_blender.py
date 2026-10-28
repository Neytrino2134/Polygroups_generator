"""LOD follow-up preserves generated previews and still rejects unrelated objects.

May also run with Containers_01_01.blend open; never saves the blend/textures.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
import bpy, addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.render_textures import create_plane, texture_planes
from polygroups_generator.operators.rebake_lods import FinalRebakeLODs

c = bpy.context
name = 'SM_Containers_01_01_MID'
target = bpy.data.objects.get(name)
if target is None:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    collection = bpy.data.collections.new('Containers_01_01_Collection')
    c.scene.collection.children.link(collection)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
    target = c.object
    target.name = name
    for owner in list(target.users_collection):
        owner.objects.unlink(target)
    collection.objects.link(target)
else:
    collection = bpy.data.collections['Containers_01_01_Collection']
    print('REAL_CONTAINER_COLLECTION', [(o.name, o.get('polygroups_texture_plane'))
                                         for o in collection.all_objects], flush=True)
    # The saved diagnostic file predates the screenshot and still has a test
    # duplicate MID. Isolate it in memory only when explicitly requested.
    if '--isolate-previews' in sys.argv:
        duplicate = collection.objects.get(name + '.001')
        if duplicate:
            isolated = bpy.data.collections.new('Test isolated duplicate')
            c.scene.collection.children.link(isolated)
            isolated.objects.link(duplicate)
            collection.objects.unlink(duplicate)
            print('TEST_ONLY_ISOLATED_DUPLICATE', duplicate.name, flush=True)
if not texture_planes(collection):
    image = bpy.data.images.new('Preview test image', width=8, height=8)
    for channel in ('BaseColor', 'Normal'):
        create_plane(collection, channel, SimpleNamespace(image=image, interpolation='Linear', extension='REPEAT'))

previews = texture_planes(collection)
c.view_layer.update()
snapshot = {o: (o.name, o.data, tuple(o.users_collection), o.matrix_world.copy(),
                tuple(o.data.materials)) for o in previews}
original_data = target.data
uvs = tuple(tuple(l.uv) for l in target.data.uv_layers.active.data)
p = c.scene.polygroups_model_preparation_settings
s = c.scene.polygroups_mesh_finalization_settings
p.phase2_run_engine = 'FAB'
s.smart_lods_count = 2
s.smart_lods_target_1 = 500
s.smart_lods_target_2 = 200
s.smart_lods_create_text = False
s.smart_lods_auto_arrange = False
s.unreal_lod_prepare_materials = False
s.unreal_lod_copy_textures = False
report = lambda _level, message: print(message, flush=True)
for _ in range(2):
    generated = FinalRebakeLODs(c, target).run(c, report)
    assert {o.name for o in generated} == {'SM_Containers_01_01_LOD0', 'SM_Containers_01_01_LOD1'}
    assert target.data == original_data
    assert tuple(tuple(l.uv) for l in target.data.uv_layers.active.data) == uvs
    for o, state in snapshot.items():
        assert (o.name, o.data, tuple(o.users_collection), o.matrix_world, tuple(o.data.materials)) == state
print('REBAKE_LODS_WITH_TEXTURE_PREVIEWS_PRESERVED_OK', flush=True)

# A similar name alone must not bypass the unrelated-object guard.
blocker = bpy.data.objects.new(collection.name + '_Texture_BaseColor_Fake', bpy.data.meshes.new('Unrelated mesh'))
collection.objects.link(blocker)
old_lods = {o.name: o for o in generated}
try:
    FinalRebakeLODs(c, target).run(c, report)
except (ValueError, RuntimeError) as error:
    assert 'Collection contains unselected objects' in str(error) and blocker.name in str(error), str(error)
else:
    raise AssertionError('An untagged unrelated object must still block preparation')
assert all(bpy.data.objects.get(name) == obj for name, obj in old_lods.items())
assert blocker.name in collection.objects
print('REBAKE_UNRELATED_OBJECT_GUARD_AND_ROLLBACK_OK', flush=True)
