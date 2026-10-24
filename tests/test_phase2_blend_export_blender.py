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
print('PHASE2_BLEND_EXPORT_PASSED')
