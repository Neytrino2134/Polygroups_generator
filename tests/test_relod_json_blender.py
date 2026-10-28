"""JSON-only ReLOD aggregates assets, drops stale LODs and preserves FAB copy."""
import sys,tempfile,json
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import rebake_export,smart_lods
from polygroups_generator.services import fab_media as media
c=bpy.context;p=c.scene.polygroups_model_preparation_settings;s=c.scene.polygroups_mesh_finalization_settings
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s.smart_lods_count=2;s.smart_lods_target_1=200;s.smart_lods_target_2=100
s.smart_lods_create_text=False;s.smart_lods_auto_arrange=False
for index in (1,2):
    collection=bpy.data.collections.new(f'JSON_01_{index:02d}_Collection');c.scene.collection.children.link(collection)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8)
    obj=c.object;obj.name=f'SM_JSON_01_{index:02d}_MID'
    for owner in list(obj.users_collection):owner.objects.unlink(obj)
    collection.objects.link(obj)
assert not p.phase2_relod_json and not p.phase2_relod_reexport
with tempfile.TemporaryDirectory(prefix='test_relod_json_',dir=ROOT) as directory:
    root=Path(directory);bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
    gallery=c.scene.airetopo_fab_media_settings
    document=media.template();document['fields']['description']='Preserve this editorial copy'
    document['fields']['assetHeadline']='Original headline'
    gallery.result_text=bpy.data.texts.new('Existing gallery');gallery.result_text.write(media.dumps(document))
    gallery.saved_filepath=str(root/'gallery.json');Path(gallery.saved_filepath).write_text(media.dumps(document),encoding='utf-8')
    with patch.object(rebake_export,'export_rebaked_asset') as export:
        assert bpy.ops.object.polygroups_relod()=={'FINISHED'}
        assert not export.called and not (root/'!Unreal'/'MeshInfo.json').exists()
        p.phase2_relod_json=True;p.phase2_relod_delete_current_lods=True
        assert bpy.ops.object.polygroups_relod()=={'FINISHED'},p.phase2_relod_status
        assert not export.called
    info_path=root/'!Unreal'/'MeshInfo.json'
    info=json.loads(info_path.read_text(encoding='utf-8'))
    assert info['totals']['meshes']==6 and len(info['assets'])==2
    assert not list(root.rglob('*.fbx')) and not (root/'!Blend').exists()
    assert info['totals']['triangles']==sum(row['triangles'] for row in info['meshes'])
    updated=media.validate(Path(gallery.saved_filepath).read_text(encoding='utf-8'))
    assert updated['fields']['description']==document['fields']['description']
    assert updated['fields']['assetHeadline']==document['fields']['assetHeadline']
    expected=media.measured_fields(media.inventory(c))
    assert all(updated['fields'][key]==value for key,value in expected.items())
    assert media.validate(gallery.result_text.as_string())==updated
    # Changed LOD count replaces stale rows and refreshes actual evaluated counts.
    s.smart_lods_count=1;s.smart_lods_target_1=80
    assert bpy.ops.object.polygroups_relod()=={'FINISHED'}
    info=json.loads(info_path.read_text(encoding='utf-8'))
    assert info['totals']['meshes']==4 and not any(row['lod_index']==1 for row in info['meshes'])
    for row in info['meshes']:
        obj=bpy.data.objects[row['name']];obj.data.calc_loop_triangles()
        assert row['triangles']==len(obj.data.loop_triangles)
    # Failure midway through generation keeps the previous complete JSON.
    before=info_path.read_bytes();gallery_before=Path(gallery.saved_filepath).read_bytes()
    with patch.object(smart_lods,'_fit_uv_preserve',side_effect=RuntimeError('generation failure')):
        try:result=bpy.ops.object.polygroups_relod()
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'}
    assert info_path.read_bytes()==before and Path(gallery.saved_filepath).read_bytes()==gallery_before
    # Malformed existing gallery fails before LOD mutation.
    pointers={o.name:o.as_pointer() for o in c.scene.objects}
    gallery.result_text.clear();gallery.result_text.write('invalid JSON')
    try:result=bpy.ops.object.polygroups_relod()
    except RuntimeError:result={'CANCELLED'}
    assert result=={'CANCELLED'} and pointers=={o.name:o.as_pointer() for o in c.scene.objects}
print('RELOD_JSON_ONLY_AGGREGATION_GALLERY_STALE_LODS_AND_FAILURES_OK',flush=True)
