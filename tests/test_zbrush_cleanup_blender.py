"""Actual Blender cleanup: job identity, partial/failure retention and success."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import zbrush_cleanup as cleanup
from polygroups_generator.core import zbrush_export as zb

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings
assert not p.phase2_zbrush_cleanup_on_success
p.phase2_zbrush_cleanup_on_success = True

with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_zb_cleanup_') as directory:
    root = Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    def fixture():
        col = bpy.data.collections.new('Generated.001')
        ctx.scene.collection.children.link(col)
        child = bpy.data.collections.new('Nested'); col.children.link(child)
        mesh = bpy.data.meshes.new('Cleanup mesh')
        obj = bpy.data.objects.new('Resculpting_01_Highpoly_Generated.001', mesh)
        child.objects.link(obj)
        child.hide_viewport = True
        asset = zb.asset_record(col.name, obj.name, [{'level': 0, 'faces': 0, 'verts': 0}], 0)
        (root / 'Mesh' / col.name).mkdir(parents=True, exist_ok=True)
        (root / asset['levels'][0]['obj']).write_text('temporary OBJ')
        zb.write_manifest(root, [asset], source_blend=bpy.data.filepath)
        return col, obj, asset

    col, obj, asset = fixture()
    other = bpy.data.collections.new('Keep collection'); ctx.scene.collection.children.link(other)
    unrelated = root / 'Mesh' / 'Other.obj'; unrelated.write_text('keep in auto cleanup')
    keep = root / 'Mesh' / 'keep.txt'; keep.write_text('keep')
    (root / 'ZTL').mkdir()
    ztl = root / asset['ztl']; ztl.write_bytes(b'ztl')
    def arm():
        cleanup.watch_success(ctx, root, [asset])
        return json.loads((root / 'job.json').read_text())['job_id']
    def result(job_id, finished=True, ok=True):
        (root / zb.RESULT_NAME).write_text(json.dumps(dict(job_id=job_id, finished=finished,
            assets=[dict(name=asset['name'], ztl=asset['ztl'], ok=ok)])))
    job_id = arm()
    from polygroups_generator.core.zbrush_job import Job
    manifest = json.loads((root / 'job.json').read_text())
    Job(None, str(root), manifest).write_result(finished=True)
    assert json.loads((root / zb.RESULT_NAME).read_text())['job_id'] == job_id
    result('stale'); assert cleanup.poll_success() == 2.0
    result(job_id, finished=False); assert cleanup.poll_success() == 2.0
    assert col.name in bpy.data.collections and (root / asset['levels'][0]['obj']).is_file()
    result(job_id, ok=False); assert cleanup.poll_success() is None
    assert col.name in bpy.data.collections and (root / asset['levels'][0]['obj']).is_file()
    job_id = arm(); result(job_id)
    ztl.unlink(); assert cleanup.poll_success() is None
    assert col.name in bpy.data.collections
    ztl.write_bytes(b'ztl')
    job_id = arm(); result(job_id)
    extra = bpy.data.objects.new('Added while waiting', None); col.objects.link(extra)
    assert cleanup.poll_success() is None and col.name in bpy.data.collections
    bpy.data.objects.remove(extra, do_unlink=True)
    job_id = arm(); result(job_id)
    with patch.object(cleanup, 'focus_blender') as focus:
        assert cleanup.poll_success() is None
        focus.assert_called_once()
    assert 'Generated.001' not in bpy.data.collections and 'Nested' not in bpy.data.collections
    assert 'Cleanup mesh' not in bpy.data.meshes
    assert not (root / asset['levels'][0]['obj']).exists()
    assert ztl.is_file() and unrelated.is_file() and keep.is_file() and other.name in bpy.data.collections
    assert bpy.ops.object.polygroups_zbrush_clear_obj() == {'FINISHED'}  # Default root: no Mesh folder.
    p.phase2_zbrush_directory = str(root)
    assert bpy.ops.object.polygroups_zbrush_clear_obj() == {'FINISHED'}
    assert not (root / 'Mesh').exists() and ztl.is_file()
    assert p.phase2_zbrush_status == 'Successfully deleted 2 files / 2 folders (including Mesh)'
    assert cleanup.clear_mesh_folder(root) == (0, 0)
    col, obj, asset = fixture()
    empty = bpy.data.collections.new('Generated.002'); ctx.scene.collection.children.link(empty)
    assert bpy.ops.object.polygroups_zbrush_delete_generated() == {'FINISHED'}
    assert 'Generated.001' not in bpy.data.collections and 'Generated.002' not in bpy.data.collections
    assert other.name in bpy.data.collections
    from polygroups_generator.custom_ui.schema import capture
    assert not capture(ctx, 1).errors
print('ZBRUSH_SUCCESS_ONLY_CLEANUP_PASSED')
