"""Real ReLOD -> replacement FBX/Blend, visibility restoration and export failures."""
import sys,tempfile,hashlib,json
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import rebake_export,relod,smart_lods,sequential_jobs
c=bpy.context;p=c.scene.polygroups_model_preparation_settings;s=c.scene.polygroups_mesh_finalization_settings
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s.smart_lods_count=2;s.smart_lods_target_1=200;s.smart_lods_target_2=100
s.smart_lods_create_text=False;s.smart_lods_auto_arrange=False
p.phase2_export_sort='LODS_FORMAT';p.phase2_blend_export_pack=False
p.phase2_export_fbx=False;p.phase2_export_glb=True;p.phase2_export_gltf=True
sources=[];collections=[]
for index in (1,2):
    col=bpy.data.collections.new(f'ReExport_01_{index:02d}_Collection');c.scene.collection.children.link(col)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8)
    source=c.object;source.name=f'SM_ReExport_01_{index:02d}_MID'
    for owner in list(source.users_collection):owner.objects.unlink(source)
    col.objects.link(source);sources.append(source);collections.append(col)
    material=bpy.data.materials.new('Asset material');material.use_nodes=True;source.data.materials.append(material)
    preview=bpy.data.objects.new(col.name+'_Texture_BaseColor',source.data.copy());col.objects.link(preview)
    preview['polygroups_texture_plane']='BaseColor'
snapshot={obj:(obj.data,obj.matrix_world.copy(),tuple(tuple(v.co) for v in obj.data.vertices)) for obj in sources}
assert not p.phase2_relod_reexport
with tempfile.TemporaryDirectory(prefix='test_relod_reexport_',dir=ROOT) as directory:
    root=Path(directory);main=root/'Working.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(main));working_hash=hashlib.sha256(main.read_bytes()).hexdigest()
    # Off means generation only.
    with patch.object(rebake_export,'export_rebaked_asset') as export:
        assert bpy.ops.object.polygroups_relod()=={'FINISHED'}
        assert not export.called
    p.phase2_relod_delete_current_lods=True;p.phase2_relod_reexport=True
    p.phase2_relod_json=True
    exports=root/'!Unreal'/'FBX';exports.mkdir(parents=True)
    blends=root/'!Blend';blends.mkdir()
    for source,col in zip(sources,collections):
        base=source.name[:-4]
        for name in (source.name,base+'_LOD0',base+'_LOD1'):(exports/(name+'.fbx')).write_bytes(b'OLD FBX')
        (blends/(col.name.removesuffix('_Collection')+'.blend')).write_bytes(b'OLD BLEND')
    sources[0].hide_viewport=True;sources[0].hide_set(True)
    collections[0].hide_render=True;collections[0].hide_viewport=True
    c.view_layer.layer_collection.children[collections[0].name].exclude=True
    c.view_layer.update()
    expected_eye=sources[0].hide_get()
    sources[1].select_set(True);c.view_layer.objects.active=sources[1]
    expected_selected={o.name for o in c.selected_objects}
    assert bpy.ops.object.polygroups_relod()=={'FINISHED'},p.phase2_relod_status
    assert p.phase2_relod_done==2 and not p.phase2_relod_running
    assert {o.name for o in c.selected_objects}==expected_selected and c.active_object==sources[1]
    assert sources[0].hide_viewport and sources[0].hide_get()==expected_eye
    assert collections[0].hide_viewport and collections[0].hide_render
    assert c.view_layer.layer_collection.children[collections[0].name].exclude
    for source,col in zip(sources,collections):
        base=source.name[:-4];expected={source.name,base+'_LOD0',base+'_LOD1'}
        for name in expected:assert (exports/(name+'.fbx')).read_bytes()!=b'OLD FBX'
        blend=blends/(col.name.removesuffix('_Collection')+'.blend')
        with bpy.data.libraries.load(str(blend)) as (src,_unused):
            assert {name for name in src.objects if name.startswith('SM_')}==expected,src.objects
            assert not any('_Texture_' in name for name in src.objects)
        assert not list(exports.glob('*Texture*'))
    assert not list(root.rglob('*.glb')) and not list(root.rglob('*.gltf'))
    assert not p.phase2_export_fbx and p.phase2_export_glb and p.phase2_export_gltf
    assert hashlib.sha256(main.read_bytes()).hexdigest()==working_hash
    info=json.loads((root/'!Unreal'/'MeshInfo.json').read_text(encoding='utf-8'))
    assert info['totals']['meshes']==6 and len(info['assets'])==2,info['totals']
    assert all(row['files'].get('FBX') for row in info['meshes'])
    for obj,(data,matrix,coords) in snapshot.items():
        assert obj.data==data and obj.matrix_world==matrix and tuple(tuple(v.co) for v in obj.data.vertices)==coords
    print('RELOD_REAL_FBX_BLEND_REPLACEMENT_AND_SOURCE_PRESERVATION_OK',flush=True)
    # Failed generation never exports and restores the current LOD set.
    old={o.name:o.as_pointer() for o in c.scene.objects if o.get('polygroups_lod_source')}
    with patch.object(smart_lods,'_fit_uv_preserve',side_effect=RuntimeError('generation failed')), \
            patch.object(rebake_export,'export_rebaked_asset') as export:
        try:result=bpy.ops.object.polygroups_relod()
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'} and not export.called
    assert all(bpy.data.objects[name].as_pointer()==pointer for name,pointer in old.items())
    # Failed export keeps the newly completed LODs, reports its stage and clears busy state.
    with patch.object(rebake_export,'export_rebaked_asset',side_effect=RuntimeError('export failed')):
        try:result=bpy.ops.object.polygroups_relod()
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'}
    assert 'ReLOD succeeded; re-export failed' in p.phase2_relod_status
    assert not p.phase2_relod_running and sequential_jobs.ACTIVE_JOB is None
    assert not any(col.name.startswith('__ReBake_LOD_Backup_') for col in bpy.data.collections)
print('RELOD_EXPORT_OFF_GENERATION_FAILURE_AND_EXPORT_FAILURE_OK',flush=True)
