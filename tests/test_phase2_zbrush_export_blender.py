"""ZBrush export: per-level OBJ files with polygroups, manifest, job script; working file untouched."""
import json
import sys
import tempfile
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
ctx = bpy.context; p = ctx.scene.polygroups_model_preparation_settings


def obj_stats(path):
    faces, groups = 0, set()
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('f '):
            faces += 1
        elif line.startswith('g '):
            groups.add(line)
    return faces, groups


with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_zbrush_export_') as directory:
    base = Path(directory)
    for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
    assert not bpy.ops.object.polygroups_phase2_export_zbrush.poll()  # unsaved file is refused

    # Mixed quad/triangle mesh: a 4x4 grid of quads plus one triangle strip, three polygroups.
    mesh = bpy.data.meshes.new('Arch')
    verts = [(x, y, 0.0) for y in range(5) for x in range(5)]
    faces = [(y * 5 + x, y * 5 + x + 1, (y + 1) * 5 + x + 1, (y + 1) * 5 + x) for y in range(4) for x in range(4)]
    verts += [(5.0, 0.0, 0.0), (5.0, 1.0, 0.0)]
    faces += [(4, 25, 26), (4, 26, 9)]
    mesh.from_pydata(verts, [], faces)
    groups = mesh.attributes.new('.sculpt_face_set', 'INT', 'FACE')
    groups.data.foreach_set('value', [1 + (i % 3) for i in range(len(mesh.polygons))])
    obj = bpy.data.objects.new('Resculpting_01_Highpoly_Generated.001', mesh)
    collection = bpy.data.collections.new('Generated.001'); ctx.scene.collection.children.link(collection)
    collection.objects.link(obj)
    ctx.view_layer.objects.active = obj; obj.select_set(True)
    ctx.view_layer.update()
    bpy.ops.object.modifier_add(type='MULTIRES')
    mod = obj.modifiers[-1]; mod.name = 'PolyGroups Multires'
    bpy.ops.object.multires_subdivide(modifier=mod.name, mode='CATMULL_CLARK')
    bpy.ops.object.multires_subdivide(modifier=mod.name, mode='CATMULL_CLARK')
    assert mod.total_levels == 2
    mod.show_viewport = False; mod.levels = 2
    base_faces = len(mesh.polygons)
    (base / '!Blend').mkdir()
    bpy.ops.wm.save_as_mainfile(filepath=str(base / '!Blend' / 'Generated.001.blend'))

    for name in ('Camera', 'Light'):
        assert name not in bpy.data.objects
    other = bpy.data.objects.new('Other', bpy.data.meshes.new('Other')); collection.objects.link(other)
    other.select_set(True); ctx.view_layer.objects.active = obj
    selection_before = sorted(o.name for o in ctx.selected_objects)
    materials_before = len(bpy.data.materials)

    p.phase2_zbrush_launch = False
    p.phase2_zbrush_build = 'PROJECT'
    assert bpy.ops.object.polygroups_phase2_export_zbrush(scope='ALL') == {'FINISHED'}, p.phase2_zbrush_status
    out = base / '!ZBrush'   # working file lives in !Blend, so the pack root is its parent
    assert out.is_dir(), list(base.iterdir())
    manifest = json.loads((out / 'job.json').read_text(encoding='utf-8'))
    assert manifest['build'] == 'PROJECT' and len(manifest['assets']) == 1
    asset = manifest['assets'][0]
    assert asset['name'] == 'Generated.001' and asset['ztl'] == 'ZTL/Generated.001.ztl', asset
    assert asset['polygroups'] == 3, asset
    counts = [item['faces'] for item in asset['levels']]
    # triangles become 3 quads at level 1, quads 4
    tris, quads = 2, base_faces - 2
    assert counts == [base_faces, quads * 4 + tris * 3, (quads * 4 + tris * 3) * 4], counts
    for item in asset['levels']:
        path = out / item['obj']
        assert path.is_file(), path
        face_count, group_names = obj_stats(path)
        assert face_count == item['faces'], (face_count, item)
        assert len(group_names) == 3, group_names
        assert not path.with_suffix('.mtl').exists()
    assert (out / 'zbrush_job.py').is_file() and (out / 'ZTL').is_dir()

    # Working data is untouched.
    assert sorted(o.name for o in ctx.selected_objects) == selection_before and ctx.view_layer.objects.active == obj
    assert len(bpy.data.materials) == materials_before and not [o for o in bpy.data.objects if o.name == 'Generated.001']
    assert mod.levels == 2 and not mod.show_viewport and len(mesh.polygons) == base_faces
    assert not [m for m in bpy.data.meshes if m.name.startswith('Arch.')]

    # Active-mesh scope exports the selected mesh under its Generated.N collection name.
    assert bpy.ops.object.polygroups_phase2_export_zbrush(scope='ACTIVE') == {'FINISHED'}, p.phase2_zbrush_status
    # Custom output folder.
    p.phase2_zbrush_directory = str(base / 'Custom')
    assert bpy.ops.object.polygroups_phase2_export_zbrush(scope='ACTIVE') == {'FINISHED'}
    assert (base / 'Custom' / 'job.json').is_file()
    # Folder batch: every Generated.N.blend is exported in its own background Blender into one job.
    collection.name = 'Generated.002'
    bpy.ops.wm.save_as_mainfile(filepath=str(base / '!Blend' / 'Generated.002.blend'), copy=True)
    collection.name = 'Generated.001'
    (base / '!Blend' / 'Other.blend').write_bytes(b'not a generated file')
    p.phase2_zbrush_directory = str(base / 'Batch')
    p.phase2_zbrush_blend_folder = str(base / '!Blend')
    p.phase2_zbrush_build = 'AUTO'
    assert bpy.ops.object.polygroups_phase2_export_zbrush_folder('EXEC_DEFAULT') == {'FINISHED'}, p.phase2_zbrush_status
    batch = json.loads((base / 'Batch' / 'job.json').read_text(encoding='utf-8'))
    assert batch['build'] == 'AUTO' and [a['name'] for a in batch['assets']] == ['Generated.001', 'Generated.002'], batch
    for item in batch['assets']:
        assert all((base / 'Batch' / level['obj']).is_file() for level in item['levels']), item
    assert not (base / 'Batch' / '_parts').exists()
    from polygroups_generator.core import zbrush_export as zb_core\n    assert isinstance(zb_core.zbrush_running(), bool)  # tasklist output is OEM-encoded on localized Windows\n    print('zbrush export ok')
