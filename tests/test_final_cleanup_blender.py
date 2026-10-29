"""Clear Temp Files: scan categories, protected folders, !Blend check and deletion."""
import sys
import tempfile
from pathlib import Path
import bpy, addon_utils
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core import final_cleanup as core  # noqa: E402
from polygroups_generator.operators import final_cleanup as ops  # noqa: E402


def touch(path, size=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x' * size)
    return path


with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_final_cleanup_') as directory:
    base = Path(directory) / 'Pack' / '08_Gray_Rocks_Ready'
    base.mkdir(parents=True)
    work = base / '08_Gray_Rocks_Ready.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(work))
    for stale in base.glob('*.blend1'):
        stale.unlink()
    keep = [
        touch(base / '!Blend' / 'Generated.001.blend'), touch(base / '!Blend' / 'Generated.002.blend'),
        touch(base / '!Blend' / 'Gray_Rocks_01.blend'), touch(base / '!Renders' / 'a.png'),
        touch(base / '!Unreal' / 'a.fbx'), touch(base / '!ZBrush' / 'ZTL' / 'a.ztl'),
        touch(base / 'Textures' / 'color.png'), touch(base / 'Textures' / 'old.blend'),
        touch(base / '01_Source' / 'rock.blend', 50), touch(base / '01_Source' / 'rock.blend1', 50),
        touch(base / '20_Source' / 'blender' / 'x.blend', 50), touch(base / '!Blend' / 'Textures' / 'q.blend1'),
    ]
    backups = [touch(base / '08_Gray_Rocks_Ready.blend1', 100), touch(base / 'Other.blend2', 100),
               touch(base / 'Other.BlendAutosave1', 100), touch(base / '!Blend' / 'Generated.001.blend1', 100),
               touch(base / '!Renders' / 'b.blend5', 100)]
    beside = [touch(base / 'Extra.blend', 1000), touch(base / 'Test.BLEND', 1000)]
    other = [touch(base / 'blender' / 'old.blend', 2000), touch(base / 'blender' / 'deep' / 'old2.blend', 2000)]
    temp = [touch(base / 'Bakes' / 'one.png', 3000), touch(base / 'Bakes' / 'sub' / 'two.png', 3000),
            touch(base / 'batch_reports' / '2026' / 'events.jsonl', 500)]

    result = core.scan(base, work)
    totals = result.totals()
    assert totals['backup'] == (5, 500), totals
    assert totals['blend_beside'] == (2, 2000) and totals['blend_other'] == (2, 4000), totals
    assert totals['temp_folder'] == (3, 6500), totals
    assert result.file_count == 12 and result.total_bytes == 13000
    paths = {item.path for item in result.items}
    assert not paths & set(keep) and work not in paths and base / 'Textures' not in paths

    # Check: !Blend has 3 blend files; Generated files are classified by object names.
    names = {'Generated.001': ['Highpoly_Generated.001', 'Resculpting_01_Highpoly_Generated.001'],
             'Generated.002': ['Highpoly_Generated.002']}
    report = core.check(base, read_names=lambda path: names[path.name[:-6]])
    assert report.blend_count == 3 and [item.name for item in report.generated] == ['Generated.001', 'Generated.002']
    assert report.generated[0].ok and not report.generated[1].ok and not report.all_ok
    assert 'Highpoly 1' in report.generated[1].summary()
    names['Generated.002'] = ['Highpoly_Generated.002', 'Retopo_01_Highpoly_Generated.002']
    assert core.check(base, read_names=lambda path: names[path.name[:-6]]).all_ok
    broken = core.check(base, read_names=lambda path: (_ for _ in ()).throw(OSError('bad')))
    assert not broken.all_ok and 'cannot read' in broken.generated[0].error

    # Unused data of the open blend: materials, images and textures nobody uses.
    ops.purge_orphans()  # leftovers of the startup file
    used = bpy.data.materials.new('Used'); used.use_nodes = True
    mesh = bpy.data.meshes.new('M'); mesh.materials.append(used)
    holder = bpy.data.objects.new('Holder', mesh)
    bpy.context.scene.collection.objects.link(holder)
    lonely = bpy.data.materials.new('Lonely')
    bpy.data.images.new('Free', 4, 4)
    pinned = bpy.data.images.new('Pinned', 4, 4); pinned.use_fake_user = True
    bpy.data.textures.new('Tex', 'IMAGE')

    # Operators, using the saved blend as the open file.
    assert bpy.ops.object.polygroups_final_cleanup_scan() == {'FINISHED'}
    assert ops.STATE['scan'].file_count == 12 and ops.STATE['check'].blend_count == 3
    assert ops.STATE['orphans'] == dict(materials=1, images=1, textures=1), ops.STATE['orphans']
    assert bpy.ops.object.polygroups_final_cleanup_clear('EXEC_DEFAULT') == {'FINISHED'}, ops.STATE['status']
    assert ops.STATE['scan'].file_count == 0 and 'Deleted 12 files' in ops.STATE['status'], ops.STATE['status']
    for path in backups + beside + other:
        assert not path.exists(), path
    assert 'purged 3 unused' in ops.STATE['status'], ops.STATE['status']
    assert 'Lonely' not in bpy.data.materials and 'Free' not in bpy.data.images and 'Tex' not in bpy.data.textures
    assert 'Used' in bpy.data.materials and 'Pinned' in bpy.data.images
    assert sum(ops.STATE['orphans'].values()) == 0
    assert not (base / 'Bakes').exists() and not (base / 'batch_reports').exists()
    for path in keep + [work]:
        assert path.exists(), path
    assert not bpy.ops.object.polygroups_final_cleanup_clear.poll()

    # A changed file is not deleted.
    changed = touch(base / 'Late.blend', 5)
    scanned = core.scan(base, work)
    changed.write_bytes(b'longer content')
    deleted, _size, errors = core.delete(scanned)
    assert deleted == 0 and changed.exists() and errors

# Drive roots are refused.
try:
    core.scan(Path(Path.cwd().anchor), Path(Path.cwd().anchor) / 'a.blend')
    raise AssertionError('drive root accepted')
except ValueError:
    pass
print('final cleanup ok')
