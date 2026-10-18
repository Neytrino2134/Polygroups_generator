"""Generate independent LOD packs for selected sources in real Blender."""
from pathlib import Path
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators.smart_lods import LOD_SOURCE, LOD_INDEX

settings = bpy.context.scene.polygroups_mesh_finalization_settings
settings.smart_lods_count = 2
settings.smart_lods_target_1 = 80
settings.smart_lods_target_2 = 40
settings.smart_lods_create_text = True
sources = []
for index in (1, 2):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, location=(index * 5, 0, 0))
    source = bpy.context.object
    source.name = f'Source{index}'
    collection = bpy.data.collections.new(f'Pack{index}')
    bpy.context.scene.collection.children.link(collection)
    for previous in list(source.users_collection):
        previous.objects.unlink(source)
    collection.objects.link(source)
    sources.append(source)
bpy.ops.object.select_all(action='DESELECT')
for source in sources:
    source.select_set(True)
light = bpy.data.objects['Light']
light.select_set(True)
bpy.context.view_layer.objects.active = sources[1]
selection = set(bpy.context.selected_objects)
counts = [len(source.data.polygons) for source in sources]
assert bpy.ops.object.polygroups_generate_smart_lods() == {'FINISHED'}
assert bpy.context.active_object == sources[1]
assert set(bpy.context.selected_objects) == selection
for source, count in zip(sources, counts):
    assert len(source.data.polygons) == count
    for index, target in ((1, 80), (2, 40)):
        lod = bpy.data.objects[f'{source.name}.LOD.{index}']
        assert lod[LOD_SOURCE] == source.name and lod[LOD_INDEX] == index
        assert set(lod.users_collection) == set(source.users_collection)
        lod.data.calc_loop_triangles()
        assert 0 < len(lod.data.loop_triangles) <= target
        assert lod.children
before = set(bpy.data.objects)
assert bpy.ops.object.polygroups_generate_smart_lods() == {'CANCELLED'}
assert set(bpy.data.objects) == before
# Origin alignment uses the origin distance even with strongly offset geometry.
for source in sources:
    for vertex in source.data.vertices:
        vertex.co.x += 7
    for index in (1, 2):
        lod = bpy.data.objects[f'{source.name}.LOD.{index}']
        for child in list(lod.children):
            bpy.data.objects.remove(child, do_unlink=True)
        bpy.data.objects.remove(lod, do_unlink=True)
settings.smart_lods_alignment = 'ORIGIN'
settings.smart_lods_spacing = 3.25
assert bpy.ops.object.polygroups_generate_smart_lods() == {'FINISHED'}
for source in sources:
    for index in (1, 2):
        lod = bpy.data.objects[f'{source.name}.LOD.{index}']
        expected = source.matrix_world.translation.copy()
        expected.x += index * 3.25
        assert (lod.matrix_world.translation - expected).length < 1e-5
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator import ui
model = capture(bpy.context, ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_mesh_finalization))
assert not model.errors, model.errors
assert any(b[0] == 'property' and b[2] == 'smart_lods_alignment' for b in model.bindings.values())
print('SMART_LODS_MULTIPLE_PASSED')
