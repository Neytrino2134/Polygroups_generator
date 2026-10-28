"""Real Cycles with a missing local Highpoly appended from !Blend/Generated.N.blend."""
from pathlib import Path
import hashlib,sys,tempfile
from unittest.mock import patch
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import baking,rebake_final as final
from polygroups_generator.operators.rebake_source import TemporaryRebakeSource,DATA_KINDS
ctx=bpy.context;scene=ctx.scene
settings=scene.polygroups_baking_settings
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
settings.bake_resolution=64;settings.bake_artifact_mask=False
settings.bake_margin=1;settings.auto_pack_uv_before_bake=False
settings.use_auto_cage=False;settings.cage_extrusion=.2;settings.ray_distance=1
settings.disable_highpoly_after_bake=True
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)


def snapshot():
    return {kind:set(getattr(bpy.data,kind)) for kind in DATA_KINDS if hasattr(bpy.data,kind)}


def move(obj,col):
    for old in list(obj.users_collection):old.objects.unlink(obj)
    col.objects.link(obj)


with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);folder=root/'!Blend';folder.mkdir();(folder/'Maps').mkdir()
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
    # Write an actual separate Generated.002 collection with un-packed relative textures.
    before_source=snapshot()
    collection=bpy.data.collections.new('Generated.002');scene.collection.children.link(collection)
    bpy.ops.mesh.primitive_plane_add(size=3,location=(10,20,0))
    high=ctx.object;high.name='Resculpting_01_Highpoly_Generated.002';move(high,collection)
    for v in high.data.vertices:v.co.z=.1
    mat=bpy.data.materials.new('ImportedHighMaterial');mat.use_nodes=True;high.data.materials.append(mat)
    color=bpy.data.images.new('SharedHighColor',width=16,height=16)
    color.generated_color=(.05,.8,.1,1)
    color.filepath_raw=str(folder/'Maps'/'HighColor.png');color.file_format='PNG';color.save();color.source='FILE';color.reload()
    node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=color
    mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    multires=high.modifiers.new('Imported Multires','MULTIRES')
    bpy.ops.object.multires_subdivide(modifier=multires.name,mode='SIMPLE')
    multires.levels=0;multires.render_levels=1;multires.show_render=False;multires.show_viewport=False
    bpy.ops.mesh.primitive_cube_add();backup=ctx.object;backup.name='Backup_Retopo_Imported';move(backup,collection)
    collection.hide_viewport=collection.hide_render=True
    source_file=folder/'Generated.002.blend'
    bpy.data.libraries.write(str(source_file),{collection},path_remap='RELATIVE_ALL',compress=True)
    file_hash=hashlib.sha256(source_file.read_bytes()).hexdigest()
    owned={item for kind,values in before_source.items() for item in set(getattr(bpy.data,kind))-values}
    bpy.data.batch_remove(ids=owned)
    # Prepared target and existing final output images.
    target_col=bpy.data.collections.new('Crystals_Pack_02_02_Collection');scene.collection.children.link(target_col)
    bpy.ops.mesh.primitive_plane_add(size=2)
    target=ctx.object;target.name='SM_Crystals_Pack_02_02_MID';move(target,target_col)
    final_mat=bpy.data.materials.new('M_Crystals_Pack_02_02');final_mat.use_nodes=True;target.data.materials.append(final_mat)
    outputs={}
    for channel,color in (('BaseColor',(1,0,0,1)),('Normal',(.5,.5,1,1))):
        image=bpy.data.images.new('T_Crystals_Pack_02_02_'+channel,width=16,height=16)
        if channel=='Normal':image.colorspace_settings.name='Non-Color'
        image.generated_color=color;image.filepath_raw=str(root/(image.name+'.png'));image.file_format='PNG';image.save();image.source='FILE';image.reload()
        node=final_mat.node_tree.nodes.new('ShaderNodeTexImage');node.name=final.CHANNELS[channel][2];node.image=image
        outputs[channel]=image
    # Existing data of the same names must not be reused, renamed, or removed.
    local_col=bpy.data.collections.new('Generated.002');scene.collection.children.link(local_col)
    sentinel=bpy.data.objects.new('KeepThisLocalMesh',bpy.data.meshes.new('KeepLocalData'));local_col.objects.link(sentinel)
    layer=ctx.view_layer.layer_collection.children[local_col.name];layer.exclude=True;layer.hide_viewport=True
    local_col.hide_viewport=local_col.hide_render=True
    other_scene=scene.copy();other_scene.name='Unrelated Scene'
    for col in list(other_scene.collection.children):other_scene.collection.children.unlink(col)
    outside=bpy.data.objects.new('Resculpting_01_Highpoly_Generated.002',bpy.data.meshes.new('OutsideHighData'))
    other_scene.collection.objects.link(outside)
    existing_image=bpy.data.images.new('SharedHighColor',width=16,height=16);existing_image.generated_color=(1,0,0,1)
    for obj in ctx.selected_objects:obj.select_set(False)
    target.select_set(True);ctx.view_layer.objects.active=target;ctx.view_layer.update()
    baseline=snapshot()
    collection_names={col:col.name for col in bpy.data.collections}
    launched=[]
    original_launch=baking.OBJECT_OT_polygroups_bake_task._launch_pass
    def inspect_import(self,context,node,kind):
        imported=self.final_rebake_session.source_import
        assert imported is not None and imported.collection!=local_col
        assert imported.source!=outside and imported.source in imported.collection.all_objects[:]
        assert self.sources==[imported.source]
        mod=next(m for m in imported.source.modifiers if m.type=='MULTIRES')
        assert not mod.show_render and not mod.show_viewport and mod.levels==1
        assert self.final_rebake_session.frozen_source is not None
        tex=next(n.image for n in imported.source.active_material.node_tree.nodes if n.type=='TEX_IMAGE')
        assert tex!=existing_image and Path(bpy.path.abspath(tex.filepath)).is_file(),tex.filepath
        assert list(tex.pixels)[1]>.5
        launched.append(kind)
        return original_launch(self,context,node,kind)
    def assert_clean():
        assert set(bpy.data.objects)==baseline['objects']
        assert set(bpy.data.collections)==baseline['collections']
        assert set(bpy.data.meshes)==baseline['meshes']
        assert set(bpy.data.materials)==baseline['materials']
        assert all(col.name==name for col,name in collection_names.items())
        assert bpy.data.objects[outside.name]==outside and outside.name in other_scene.objects
        assert sentinel.name in local_col.objects and layer.exclude and layer.hide_viewport
        assert local_col.hide_viewport and local_col.hide_render
        assert bpy.data.images.get('SharedHighColor')==existing_image
        assert not any(img.name.startswith('SharedHighColor.') for img in bpy.data.images)
        assert hashlib.sha256(source_file.read_bytes()).hexdigest()==file_hash
        assert list(target.data.materials)==[final_mat]
        assert ctx.active_object==target
    # Constructor preflight reads the library without appending anything.
    plan=final.FinalRebakeSession(ctx,target,settings)
    assert plan.source is None and plan.source_import.path==source_file
    assert snapshot()==baseline
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',inspect_import):
        assert bpy.ops.object.polygroups_rebake_final_mesh()=={'FINISHED'},settings.bake_task_message
    assert launched==['DIFFUSE','NORMAL']
    assert list(outputs['BaseColor'].pixels)[(8*16+8)*4+1]>.5
    assert_clean()
    print('REBAKE_IMPORTED_SOURCE_REAL_CYCLES_AND_OWNERSHIP_OK')
    # Keep the import alive through both optional follow-ups; remove it only
    # after the exported asset has been written successfully.
    from polygroups_generator.operators import rebake_export
    p=scene.polygroups_model_preparation_settings
    s=scene.polygroups_mesh_finalization_settings
    p.phase2_run_engine='FAB';p.phase2_export_sort='LODS_FORMAT'
    settings.bake_artifact_mask=True
    s.smart_lods_count=2;s.smart_lods_target_1=s.smart_lods_target_2=2
    s.smart_lods_auto_arrange=s.smart_lods_create_text=False
    s.unreal_lod_prepare_materials=True
    full_before=snapshot()
    followup=rebake_export.export_rebaked_asset
    alive=[]
    def inspect_followup(context,target,generated,collection,engine,report):
        imported=[col for col in bpy.data.collections if col not in baseline['collections']
                  and any(o.name.startswith('Resculpting_01_Highpoly_Generated') for o in col.all_objects)]
        assert len(imported)==1,[(col.name,col in baseline['collections']) for col in bpy.data.collections]
        alive.append(imported[0].name)
        return followup(context,target,generated,collection,engine,report)
    with patch.object(rebake_export,'export_rebaked_asset',inspect_followup):
        assert bpy.ops.object.polygroups_rebake_final_mesh(create_lods=True,export_selected=True)=={'FINISHED'},settings.bake_task_message
    assert alive
    assert set(bpy.data.collections)==baseline['collections']
    assert (root/'!Unreal'/'FBX'/(target.name+'.fbx')).is_file()
    with bpy.data.libraries.load(str(folder/'Crystals_Pack_02_02.blend')) as (src,dst):
        assert src.collections==['Crystals_Pack_02_02_Collection'],src.collections
        assert not any(name.startswith('Resculpting_') or name.startswith('Backup_') for name in src.objects)
    assert outside.name in other_scene.objects and layer.exclude
    # Remove only test-owned LOD/follow-up IDs before failure/cancel cases.
    followup_ids={item for kind,values in full_before.items() for item in set(getattr(bpy.data,kind))-values}
    bpy.data.batch_remove(ids=followup_ids)
    ctx.view_layer.objects.active=target
    target.select_set(True)
    assert_clean()
    print('REBAKE_IMPORTED_SOURCE_FULL_CHAIN_LATE_CLEANUP_OK')
    # The same-folder lookup works when the open asset already lives in !Blend.
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/'Crystals_Pack_02_02.blend'))
    assert TemporaryRebakeSource(2).path==source_file
    stable={ch:Path(bpy.path.abspath(img.filepath)).read_bytes() for ch,img in outputs.items()}
    # Cancel restores Edit Mode as well as deleting only append-owned data.
    bpy.ops.object.mode_set(mode='EDIT')
    step=baking.OBJECT_OT_polygroups_bake_task._step
    def cancel(self,context):
        if self.stage=='BASE_READY':return self._finish(context,False,'Cancel imported rebake',cancelled=True)
        return step(self,context)
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_step',cancel):
        assert bpy.ops.object.polygroups_rebake_final_mesh()=={'CANCELLED'}
    assert target.mode=='EDIT'
    bpy.ops.object.mode_set(mode='OBJECT')
    assert_clean()
    assert stable=={ch:Path(bpy.path.abspath(img.filepath)).read_bytes() for ch,img in outputs.items()}
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',side_effect=RuntimeError('Imported bake failure')):
        try:result=bpy.ops.object.polygroups_rebake_final_mesh()
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'}
    assert_clean()
    assert stable=={ch:Path(bpy.path.abspath(img.filepath)).read_bytes() for ch,img in outputs.items()}
    print('REBAKE_IMPORTED_SOURCE_CANCEL_FAILURE_CLEANUP_OK')
    # A correct object in a different collection must be rejected with no leaks.
    extra_before=snapshot()
    invalid_col=bpy.data.collections.new('Generated.003');scene.collection.children.link(invalid_col)
    wrong=bpy.data.objects.new('WrongCollectionMember',bpy.data.meshes.new('WrongMemberMesh'));invalid_col.objects.link(wrong)
    orphan=bpy.data.objects.new('Resculpting_01_Highpoly_Generated.003',bpy.data.meshes.new('OrphanHighMesh'))
    invalid_file=folder/'Generated.003.blend'
    bpy.data.libraries.write(str(invalid_file),{invalid_col,orphan},compress=True)
    extra_ids={item for kind,values in extra_before.items() for item in set(getattr(bpy.data,kind))-values}
    bpy.data.batch_remove(ids=extra_ids)
    before_invalid=snapshot()
    try:TemporaryRebakeSource(3).load(ctx)
    except ValueError as error:assert 'not in' in str(error)
    else:raise AssertionError('Wrong collection accepted')
    assert snapshot()==before_invalid
    try:TemporaryRebakeSource(4)
    except ValueError as error:assert 'Generated.004.blend' in str(error)
    else:raise AssertionError('Missing source file accepted')
    print('REBAKE_IMPORTED_SOURCE_VALIDATION_OK')
print('REBAKE_SOURCE_IMPORT_TESTS_OK')
