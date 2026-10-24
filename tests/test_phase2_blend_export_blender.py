"""Per-collection blend export: clean scene, own textures only, working file untouched."""
import sys, tempfile
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
ctx = bpy.context; p = ctx.scene.polygroups_model_preparation_settings

with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_blend_export_') as directory:
    root = Path(directory)
    # unsaved file is refused by poll
    assert not bpy.ops.object.polygroups_phase2_export_blend.poll()
    for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
    textures = {}
    for name in ('Stone_01_01', 'Stone_01_02'):
        image = bpy.data.images.new(name + '_Color', 8, 8)
        image.filepath_raw = str(root / (name + '_Color.png')); image.file_format = 'PNG'; image.save()
        image.source = 'FILE'; image.reload()
        material = bpy.data.materials.new(name + '_Mat'); material.use_nodes = True
        node = material.node_tree.nodes.new('ShaderNodeTexImage'); node.image = image
        col = bpy.data.collections.new(name + '_Collection'); ctx.scene.collection.children.link(col)
        mesh = bpy.data.meshes.new(name); mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        mesh.materials.append(material)
        col.objects.link(bpy.data.objects.new('SM_' + name + '_MID', mesh))
        textures[name] = image
    # pre-existing Camera/Light/Scene names must not leak into or break the export
    bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    ctx.scene.name = 'Scene'
    other = bpy.data.collections.new('Other'); ctx.scene.collection.children.link(other)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Pack.blend'))
    assert bpy.ops.object.polygroups_phase2_export_blend() == {'FINISHED'}, p.phase2_blend_export_status
    out = root / '!Blend'
    assert sorted(f.name for f in out.glob('*.blend')) == ['Stone_01_01.blend', 'Stone_01_02.blend']
    # working file is unchanged
    assert ctx.scene.name == 'Scene' and 'Camera' in bpy.data.objects and 'Scene.001' not in bpy.data.scenes
    assert all(img.packed_file is None for img in textures.values())
    assert not [o for o in bpy.data.objects if o.name.endswith('__airetopo_hold')]
    for name in textures:
        with bpy.data.libraries.load(str(out / (name + '.blend'))) as (src, dst):
            assert src.scenes == ['Scene'], src.scenes
            assert src.collections == [name + '_Collection'], src.collections
            assert src.cameras == ['Camera'] and src.lights == ['Light'], (src.cameras, src.lights)
            assert src.images == [name + '_Color'], src.images
            assert src.materials == [name + '_Mat'] and src.objects.count('Camera') == 1
            dst.scenes = src.scenes
            dst.images = src.images
        assert dst.images[0].packed_file is not None, 'texture was not packed'
        scene = dst.scenes[0]
        # Loaded beside same-named originals, so Blender appends .001 suffixes.
        strip = lambda value: value.rsplit('.', 1)[0] if value[-4:-3] == '.' and value[-3:].isdigit() else value
        assert sorted(strip(o.name) for o in scene.objects) == sorted(['Camera', 'Light', 'SM_' + name + '_MID']), \
            [o.name for o in scene.objects]
        assert scene.camera and strip(scene.camera.name) == 'Camera'
        bpy.data.scenes.remove(scene)
    # Prepared meshes are written at Y = 0 while the working file keeps its positions.
    mid = bpy.data.objects['SM_Stone_01_01_MID']; mid.location = (2, 7, 3)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Pack.blend'))
    assert bpy.ops.object.polygroups_phase2_export_blend() == {'FINISHED'}
    assert tuple(mid.location) == (2, 7, 3)
    with bpy.data.libraries.load(str(out / 'Stone_01_01.blend')) as (src, dst):
        dst.objects = [n for n in src.objects if n == 'SM_Stone_01_01_MID']
    assert tuple(dst.objects[0].location) == (2, 0, 3), tuple(dst.objects[0].location)
    # Studio collections (with nested children) replace the generated Camera/Light.
    from polygroups_generator.operators.render_studio import TAG
    for obj in list(bpy.data.objects):
        if obj.name == 'Camera': bpy.data.objects.remove(obj, do_unlink=True)
    roles = {}
    for role, name in (('scene', 'Scene_Studio'), ('camera', 'Camera_Studio'), ('light', 'Light_Studio')):
        col = bpy.data.collections.new(name); col[TAG] = role; ctx.scene.collection.children.link(col)
        roles[role] = col
    nested = bpy.data.collections.new('Camera_Nested'); roles['camera'].children.link(nested)
    for i, parent in enumerate((roles['camera'], nested)):
        parent.objects.link(bpy.data.objects.new(f'Studio_Cam_{i}', bpy.data.cameras.new(f'Studio_Cam_{i}')))
    roles['light'].objects.link(bpy.data.objects.new('Studio_Lamp', bpy.data.lights.new('Studio_Lamp', 'AREA')))
    roles['scene'].objects.link(bpy.data.objects.new('Studio_Floor', bpy.data.meshes.new('Studio_Floor')))
    ctx.scene.camera = bpy.data.objects['Studio_Cam_1']
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Pack.blend'))
    assert bpy.ops.object.polygroups_phase2_export_blend() == {'FINISHED'}, p.phase2_blend_export_status
    with bpy.data.libraries.load(str(out / 'Stone_01_01.blend')) as (src, dst):
        assert set(src.collections) == {'Stone_01_01_Collection', 'Scene_Studio', 'Camera_Studio',
                                        'Light_Studio', 'Camera_Nested'}, src.collections
        assert sorted(src.cameras) == ['Studio_Cam_0', 'Studio_Cam_1'] and src.lights == ['Studio_Lamp']
        assert 'Studio_Floor' in src.objects and 'Camera' not in list(src.objects) and 'Light' not in list(src.objects)
        dst.scenes = src.scenes
    assert dst.scenes[0].camera.name.startswith('Studio_Cam_1')
    assert ctx.scene.name == 'Scene' and ctx.scene.camera.name == 'Studio_Cam_1'
    # Generated.N collections are exported only when enabled, with their own textures packed.
    image = bpy.data.images.new('Resc_Color', 8, 8)
    image.filepath_raw = str(root / 'Resc_Color.png'); image.file_format = 'PNG'; image.save()
    image.source = 'FILE'; image.reload()
    material = bpy.data.materials.new('Resc_Mat'); material.use_nodes = True
    material.node_tree.nodes.new('ShaderNodeTexImage').image = image
    generated = bpy.data.collections.new('Generated.001'); ctx.scene.collection.children.link(generated)
    mesh = bpy.data.meshes.new('Resculpting_01_Mesh'); mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.materials.append(material)
    generated.objects.link(bpy.data.objects.new('Resculpting_01.001', mesh))
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Pack.blend'))
    assert not p.phase2_blend_export_generated
    assert bpy.ops.object.polygroups_phase2_export_blend() == {'FINISHED'}
    assert not (out / 'Generated.001.blend').exists()
    p.phase2_blend_export_generated = True
    assert bpy.ops.object.polygroups_phase2_export_blend() == {'FINISHED'}, p.phase2_blend_export_status
    assert image.packed_file is None
    with bpy.data.libraries.load(str(out / 'Generated.001.blend')) as (src, dst):
        assert 'Generated.001' in src.collections and src.images == ['Resc_Color'], (src.collections, src.images)
        dst.images = src.images
    assert dst.images[0].packed_file is not None
print('PHASE2_BLEND_EXPORT_PASSED')
