"""Integration: real Cycles final rebake, numbered source, hidden hierarchy, exact output files."""
from pathlib import Path
import sys,tempfile,hashlib
from unittest.mock import patch
import addon_utils,bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import baking,rebake_final as final
from polygroups_generator.core.bake_projection import current_mask
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
settings=scene.polygroups_baking_settings
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
settings.bake_resolution=64
settings.bake_margin=1
settings.bake_artifact_radius=0
settings.bake_artifact_autofill=False
settings.bake_artifact_mask=True
settings.auto_pack_uv_before_bake=True # Must keep existing final UVs anyway.
settings.auto_fix_generated_index=True
settings.disable_highpoly_after_bake=True
settings.use_auto_cage=False
settings.cage_extrusion=.2
settings.ray_distance=1
settings.auto_save_textures_after_bake=True


def move(obj,col):
    for old in list(obj.users_collection):old.objects.unlink(obj)
    col.objects.link(obj)


with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(directory/'rebake.blend'))
    target_collection=bpy.data.collections.new('Crystals_Pack_02_02_Collection');scene.collection.children.link(target_collection)
    bpy.ops.mesh.primitive_plane_add(size=2,location=(3,4,1))
    target=bpy.context.object;target.name='SM_Crystals_Pack_02_02_MID';move(target,target_collection)
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.subdivide(number_cuts=1);bpy.ops.object.mode_set(mode='OBJECT')
    finalmat=bpy.data.materials.new('M_Crystals_Pack_02_02');finalmat.use_nodes=True
    second=bpy.data.materials.new('M_Second');second.use_nodes=True
    target.data.materials.append(finalmat);target.data.materials.append(second)
    for p in target.data.polygons:p.material_index=p.index%2
    images={}
    files={}
    for channel,color in (('BaseColor',(1,0,0,1)),('Normal',(.5,.5,1,1))):
        image=bpy.data.images.new('T_Crystals_Pack_02_02_'+channel,width=32,height=32)
        image.generated_color=color
        if channel=='Normal':image.colorspace_settings.name='Non-Color'
        image.filepath_raw=str(directory/(image.name+'.png'));image.file_format='PNG';image.save();image.pack()
        images[channel]=image;files[channel]=Path(image.filepath_raw)
        node=finalmat.node_tree.nodes.new('ShaderNodeTexImage');node.name=final.CHANNELS[channel][2];node.image=image
    # A stale property must not redirect the output to an old Bake_Temp image.
    stale=bpy.data.images.new('Bake_Temp_Generated.002_BaseColor',width=16,height=16)
    target[baking.BAKE_BASE_COLOR_IMAGE_PROP]=stale.name
    stale_name=stale.name
    parent=bpy.data.collections.new('Hidden Sources');scene.collection.children.link(parent)
    generated=bpy.data.collections.new('Generated.002');parent.children.link(generated)
    bpy.ops.mesh.primitive_plane_add(size=3,location=(-10,7,1))
    high=bpy.context.object;high.name='Resculpting_01_Highpoly_Generated.002';move(high,generated)
    source_mat=bpy.data.materials.new('SourceColor');source_mat.use_nodes=True
    source_mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.05,.8,.1,1)
    high.data.materials.append(source_mat)
    high.rotation_euler=(.13,.17,0)
    multires=high.modifiers.new('Multires','MULTIRES')
    bpy.context.view_layer.objects.active=high
    bpy.ops.object.multires_subdivide(modifier=multires.name,mode='SIMPLE')
    multires.levels=0;multires.render_levels=1;multires.show_render=False;multires.show_viewport=False
    high.hide_set(True);high.hide_viewport=True;high.hide_render=True;high.hide_select=True
    parent.hide_viewport=True;parent.hide_render=True;parent.hide_select=True
    layer=bpy.context.view_layer.layer_collection.children[parent.name];layer.exclude=True
    for obj in bpy.context.selected_objects:obj.select_set(False)
    target.select_set(True);bpy.context.view_layer.objects.active=target
    bpy.context.view_layer.update()
    settings_before={name:getattr(settings,name) for name in ('image_prefix','bake_resolution','auto_pack_uv_before_bake','auto_fix_generated_index','disable_highpoly_after_bake','auto_save_textures_after_bake','use_selected_to_active')}
    matrix_before=high.matrix_world.copy()
    uv_before=[tuple(l.uv) for l in target.data.uv_layers.active.data]
    indices=[p.material_index for p in target.data.polygons]
    hashes={ch:hashlib.sha256(path.read_bytes()).hexdigest() for ch,path in files.items()}
    original_launch=baking.OBJECT_OT_polygroups_bake_task._launch_pass
    observed=[]
    def checked_launch(self,context,node,kind):
        assert self.target==target and self.sources==[high]
        assert (high.matrix_world.translation-target.matrix_world.translation).length<1e-6
        assert not high.hide_render and not high.hide_viewport and not high.hide_get()
        assert multires.levels==1 and not multires.show_render and not multires.show_viewport
        assert self.final_rebake_session.frozen_source is not None
        assert not layer.exclude and not parent.hide_render and not parent.hide_viewport
        assert node.image not in images.values()
        assert [tuple(l.uv) for l in target.data.uv_layers.active.data]==uv_before
        observed.append(kind)
        return original_launch(self,context,node,kind)
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',checked_launch):
        assert bpy.ops.object.polygroups_rebake_final_mesh()=={'FINISHED'},settings.bake_task_message
    assert observed==['DIFFUSE','NORMAL'],observed
    assert settings.bake_task_stage=='DONE',settings.bake_task_message
    assert dict((k,getattr(settings,k)) for k in settings_before)==settings_before
    assert high.matrix_world==matrix_before
    assert high.hide_render and high.hide_viewport and high.hide_select and layer.exclude
    assert parent.hide_viewport and parent.hide_render and parent.hide_select
    assert not multires.show_render and not multires.show_viewport and multires.levels==0
    assert list(high.data.materials)==[source_mat]
    assert list(target.data.materials)==[finalmat,second]
    assert [p.material_index for p in target.data.polygons]==indices
    assert [tuple(l.uv) for l in target.data.uv_layers.active.data]==uv_before
    for ch,image in images.items():
        assert bpy.data.images.get(image.name)==image
        assert files[ch].is_file()
        assert len(list(directory.glob('T_Crystals_Pack_02_02_'+ch+'*.png')))==1
        assert tuple(image.size)==(32,32)
        assert image.packed_file
    pixels=list(images['BaseColor'].pixels)
    center=(16*32+16)*4
    assert pixels[center+1]>pixels[center]+.2,pixels[center:center+4]
    assert hashes['BaseColor']!=hashlib.sha256(files['BaseColor'].read_bytes()).hexdigest()
    assert stale.name==stale_name
    assert not list(directory.rglob('Bakes'))
    assert not list(directory.glob('.rebake-*'))
    assert not any(image.name.startswith('ReBake_') for image in bpy.data.images)
    assert current_mask(target,images['Normal']) is not None
    assert (directory/'T_Crystals_Pack_02_02_ArtifactMask.png').is_file()
    import json
    from polygroups_generator.core.bake_projection import META_PROP
    mask=current_mask(target,images['Normal'])
    disk_metadata=json.loads((directory/'T_Crystals_Pack_02_02_ArtifactMask.png.json').read_text())
    assert disk_metadata['normal_hash']==json.loads(mask[META_PROP])['normal_hash']
    print('FINAL_REBAKE_REAL_CYCLES_OK')
    # Failure during baking must preserve output files and scene setup.
    stable={ch:hashlib.sha256(path.read_bytes()).hexdigest() for ch,path in files.items()}
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',side_effect=RuntimeError('injected bake failure')):
        try:result=bpy.ops.object.polygroups_rebake_final_mesh()
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'}
    assert stable=={ch:hashlib.sha256(path.read_bytes()).hexdigest() for ch,path in files.items()}
    assert high.matrix_world==matrix_before and layer.exclude
    assert list(target.data.materials)==[finalmat,second]
    assert not settings.bake_task_is_running
    assert not any(image.name.startswith('ReBake_') for image in bpy.data.images)
    print('FINAL_REBAKE_FAILURE_RESTORE_OK')
    # A file replacement failure must roll back files already replaced.
    replace=final.os.replace
    failed=[]
    def fail_normal_replace(src,dst):
        if Path(dst)==files['Normal'] and not failed:
            failed.append(True)
            raise OSError('injected file replacement failure')
        return replace(src,dst)
    with patch.object(final.os,'replace',fail_normal_replace):
        try:result=bpy.ops.object.polygroups_rebake_final_mesh()
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'}
    assert failed
    assert stable=={ch:hashlib.sha256(path.read_bytes()).hexdigest() for ch,path in files.items()}
    assert not list(directory.glob('.rebake-*'))
    assert high.matrix_world==matrix_before and layer.exclude
    assert list(target.data.materials)==[finalmat,second]
    assert not any(image.name.startswith('ReBake_') for image in bpy.data.images)
    print('FINAL_REBAKE_ATOMIC_ROLLBACK_OK')
    # Cancellation after postprocessing but before finalize must not save files.
    step=baking.OBJECT_OT_polygroups_bake_task._step
    def cancel_at_save(self,context):
        if self.stage=='SAVE':
            return self._finish(context,False,'Test cancellation',cancelled=True)
        return step(self,context)
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_step',cancel_at_save):
        assert bpy.ops.object.polygroups_rebake_final_mesh()=={'CANCELLED'}
    assert stable=={ch:hashlib.sha256(path.read_bytes()).hexdigest() for ch,path in files.items()}
    assert high.matrix_world==matrix_before and layer.exclude
    assert list(target.data.materials)==[finalmat,second]
    assert not any(image.name.startswith('ReBake_') for image in bpy.data.images)
    print('FINAL_REBAKE_CANCEL_RESTORE_OK')
    # Reject an absent/mismatched or ambiguous source without mutating state.
    high.name='OtherSource.002'
    try:final.FinalRebakeSession(bpy.context,target,settings)
    except ValueError as error:assert 'Generated.002' in str(error) and 'Highpoly' in str(error)
    else:raise AssertionError('Missing source accepted')
    high.name='Resculpting_01_Highpoly_Generated.002'
    duplicate=high.copy();duplicate.data=high.data.copy();duplicate.name='Resculpting_01_Highpoly_Generated.02'
    generated.objects.link(duplicate)
    try:final.resolve_final_source(bpy.context,target)
    except ValueError as error:assert 'ambiguous' in str(error)
    else:raise AssertionError('Ambiguous source accepted')
    bpy.data.objects.remove(duplicate,do_unlink=True)
    print('FINAL_REBAKE_PREFLIGHT_OK')
    from polygroups_generator.custom_ui.schema import capture
    tree=capture(bpy.context,9)
    assert not tree.errors,tree.errors
    operators=[b[1] for b in tree.bindings.values() if b[0]=='operator']
    assert operators.index('object.polygroups_rebake_final_mesh')==operators.index('object.polygroups_checked_prepare_and_bake')+1
    print('FINAL_REBAKE_UI_BUTTON_OK')
    preparation=scene.polygroups_model_preparation_settings
    finalization=scene.polygroups_mesh_finalization_settings
    try:final.FinalRebakeSession(bpy.context,target,settings,export_selected=True)
    except ValueError as error:assert 'Enable Create LODs' in str(error)
    else:raise AssertionError('Export without Create LODs accepted')
    assert preparation.phase2_rebake_export_selected
    assert preparation.phase2_rebake_create_lods and preparation.phase2_rebake_delete_current_lods
    assert preparation.phase2_rebake_repack_uv
    preparation.phase2_rebake_create_lods=True
    phase2_tree=capture(bpy.context,1)
    assert not phase2_tree.errors,phase2_tree.errors
    phase2_ops=[b[1] for b in phase2_tree.bindings.values() if b[0]=='operator']
    assert 'object.polygroups_start_phase2' in phase2_ops and 'object.polygroups_rebake_final_mesh' in phase2_ops
    assert any(b[0]=='property' and b[2]=='phase2_rebake_create_lods' for b in phase2_tree.bindings.values())
    assert any(b[0]=='property' and b[2]=='phase2_rebake_export_selected' for b in phase2_tree.bindings.values())
    from polygroups_generator.operators import phase2_pipeline_stages
    assert not any('rebake_final' in str(stage) for stage in phase2_pipeline_stages.STAGES)
    finalization.smart_lods_count=2
    finalization.smart_lods_target_1=6
    finalization.smart_lods_target_2=2
    finalization.smart_lods_auto_arrange=False
    finalization.smart_lods_create_text=False
    finalization.unreal_lod_prepare_materials=True
    finalization.unreal_lod_copy_textures=False
    finalization.unity_copy_textures=False
    finalization.unity_auto_increment_index=True
    other_collection=bpy.data.collections.new('Crystals_Pack_02_01_Collection')
    scene.collection.children.link(other_collection)
    unrelated=[]
    for i in range(5):
        mesh=bpy.data.meshes.new('Unrelated LOD mesh '+str(i))
        obj=bpy.data.objects.new(f'SM_Crystals_Pack_02_01_LOD{i}',mesh)
        other_collection.objects.link(obj)
        unrelated.append((obj,obj.name,mesh))
    for engine in ('FAB','UNITY'):
        preparation.phase2_run_engine=engine
        finalization.unreal_lod_asset_name='Crystals_Pack'
        finalization.unreal_lod_name_index='02'
        finalization.unreal_lod_version_index='01'
        finalization.unity_asset_name='ManualUnity'
        finalization.unity_name_index='03'
        finalization.unity_asset_index='07'
        finalization.unity_asset_suffix=''
        # Use an opposite Smart LOD mode to verify the Phase 2 selector owns it.
        finalization.smart_lods_prepare_mode='UNITY' if engine=='FAB' else 'UNREAL'
        previous_mode=finalization.smart_lods_prepare_mode
        original_objects=set(bpy.data.objects)
        target_matrix=target.matrix_world.copy()
        observed_lod_calls=[]
        from polygroups_generator.operators.rebake_lods import FinalRebakeLODs
        original_run=FinalRebakeLODs.run
        def after_success(self,context,report):
            # Existing final files and image bindings must be committed first.
            assert target[baking.BAKE_BASE_COLOR_IMAGE_PROP]==images['BaseColor'].name
            assert target.active_material==finalmat
            assert high.matrix_world==matrix_before and layer.exclude
            observed_lod_calls.append(self.engine)
            return original_run(self,context,report)
        with patch.object(FinalRebakeLODs,'run',after_success):
            assert bpy.ops.object.polygroups_rebake_final_mesh(create_lods=True)=={'FINISHED'},settings.bake_task_message
        assert observed_lod_calls==['UNREAL' if engine=='FAB' else 'UNITY']
        generated=[o for o in set(bpy.data.objects)-original_objects if o.type=='MESH']
        if engine=='FAB':expected={'SM_Crystals_Pack_02_02_LOD0','SM_Crystals_Pack_02_02_LOD1'}
        else:expected={'Crystals_Pack_02_02','Crystals_Pack_02_02.LOD1'}
        assert {o.name for o in generated}==expected,{o.name for o in generated}
        assert all(o.get('polygroups_lod_source')==target.name for o in generated)
        assert all(len(o.data.loop_triangles)<=6 for o in generated)
        assert target.matrix_world==target_matrix
        assert list(target.data.materials)==[finalmat,second]
        assert finalization.smart_lods_prepare_mode==previous_mode
        assert finalization.unity_asset_index=='07'
        assert [tuple(l.uv) for l in target.data.uv_layers.active.data]==uv_before
        # A second run must replace this asset's existing LODs, not reject them.
        old_lods=set(generated)
        # Remove stale levels above the newly requested count, including labels.
        stale_name='SM_Crystals_Pack_02_02_LOD4' if engine=='FAB' else 'Crystals_Pack_02_02.LOD4'
        stale_mesh=target.data.copy()
        stale_lod=bpy.data.objects.new(stale_name,stale_mesh)
        target_collection.objects.link(stale_lod)
        curve=bpy.data.curves.new('Old LOD4 label','FONT')
        stale_label=bpy.data.objects.new('Old LOD4 label '+engine,curve)
        target_collection.objects.link(stale_label)
        stale_label.parent=stale_lod
        stale_label_name=stale_label.name
        old_lods.add(stale_lod)
        old_pointers={o.as_pointer() for o in old_lods}
        old_mesh_names=[o.data.name for o in old_lods]
        assert bpy.ops.object.polygroups_rebake_final_mesh(create_lods=True)=={'FINISHED'}
        rebuilt=[bpy.data.objects[name] for name in expected]
        assert not old_pointers & {o.as_pointer() for o in rebuilt}
        assert all(o.data.name==o.name for o in rebuilt)
        assert bpy.data.objects.get(stale_name) is None
        assert bpy.data.objects.get(stale_label_name) is None
        assert list(target.data.materials)==[finalmat,second]
        # Full manual chain: bake -> replace LODs -> select current asset -> FBX/blend.
        preparation.phase2_export_engine='UNITY' if engine=='FAB' else 'FAB'
        preparation.phase2_export_glb=True
        preparation.phase2_export_gltf=True
        preparation.phase2_export_fbx=False
        preparation.phase2_export_json=True
        finalization.unity_export_directory=str(directory/'ManualUnityExports')
        finalization.unity_export_overwrite=False
        finalization.unity_export_clear_asset_folder=True
        finalization.unity_export_autosave=True
        export_settings={n:getattr(preparation,n) for n in ('phase2_export_engine','phase2_export_glb','phase2_export_gltf','phase2_export_fbx')}
        export_root=directory/'!Unreal' if engine=='FAB' else directory/'ManualUnityExports'
        fbx_folder=export_root/'FBX';fbx_folder.mkdir(parents=True,exist_ok=True)
        expected_export=expected|{target.name}
        for name in expected_export:(fbx_folder/(name+'.fbx')).write_bytes(b'OLD FBX')
        blend_file=directory/'!Blend'/'Crystals_Pack_02_02.blend'
        blend_file.parent.mkdir(exist_ok=True);blend_file.write_bytes(b'OLD BLEND')
        working_file=Path(bpy.data.filepath)
        working_hash=hashlib.sha256(working_file.read_bytes()).hexdigest()
        assert bpy.ops.object.polygroups_rebake_final_mesh(create_lods=True,export_selected=True)=={'FINISHED'},settings.bake_task_message
        assert {o.name for o in bpy.context.selected_objects}==expected_export
        assert bpy.context.active_object==target
        for name in expected_export:
            assert (fbx_folder/(name+'.fbx')).read_bytes()!=b'OLD FBX'
        info=json.loads((export_root/'MeshInfo.json').read_text())
        assert info['totals']['meshes']==3,info
        assert not list(export_root.rglob('*.glb')) and not list(export_root.rglob('*.gltf'))
        assert not list(export_root.rglob('*Crystals_Pack_02_01*'))
        with bpy.data.libraries.load(str(blend_file)) as (src,dst):
            mesh_names={name for name in src.objects if name.startswith(('SM_','Crystals_'))}
            assert mesh_names==expected_export,src.objects
            assert src.collections==['Crystals_Pack_02_02_Collection'],src.collections
        assert all(getattr(preparation,n)==v for n,v in export_settings.items())
        assert not finalization.unity_export_overwrite and finalization.unity_export_clear_asset_folder
        assert finalization.unity_export_autosave
        assert hashlib.sha256(working_file.read_bytes()).hexdigest()==working_hash
        rebuilt=[bpy.data.objects[name] for name in expected]
        print('FINAL_REBAKE_EXPORT_FBX_BLEND_'+engine+'_OK')
        # Export selects MID + LODs. Request automatic Highpoly lookup for the
        # next run by selecting only the target under the new source contract.
        bpy.ops.object.select_all(action='DESELECT');target.select_set(True)
        bpy.context.view_layer.objects.active=target
        # Failure after stashing must bring originals back with their exact data.
        rollback_curve=bpy.data.curves.new('Recoverable label','FONT')
        rollback_label=bpy.data.objects.new('Recoverable label '+engine,rollback_curve)
        rebuilt[0].users_collection[0].objects.link(rollback_label)
        rollback_label.parent=rebuilt[0]
        backups={o.name:(o,o.data,tuple(o.users_collection)) for o in [*rebuilt,rollback_label]}
        from polygroups_generator.operators.smart_lods import OBJECT_OT_polygroups_generate_smart_lods
        def fail_generation(self,context):
            raise RuntimeError('injected LOD generation failure')
            yield
        from polygroups_generator.operators import rebake_export
        preserved_blend=blend_file.read_bytes()
        with patch.object(OBJECT_OT_polygroups_generate_smart_lods,'source_steps',fail_generation), \
                patch.object(rebake_export,'export_rebaked_asset') as followup_export:
            try:result=bpy.ops.object.polygroups_rebake_final_mesh(create_lods=True,export_selected=True)
            except RuntimeError:result={'CANCELLED'}
            assert result=={'CANCELLED'}
            assert not followup_export.called
        assert blend_file.read_bytes()==preserved_blend
        for name,(original,data,collections) in backups.items():
            assert bpy.data.objects[name]==original and original.data==data
            assert tuple(original.users_collection)==collections
        assert not any(c.name.startswith('__ReBake_LOD_Backup_') for c in bpy.data.collections)
    for obj,name,mesh in unrelated:
        assert bpy.data.objects[name]==obj and obj.data==mesh and obj.name in other_collection.objects
    assert bpy.data.objects.get('SM_Crystals_Pack_02_02_LOD0')
    print('FINAL_REBAKE_EXISTING_LODS_REPLACED_AND_OTHER_ASSETS_UNTOUCHED_OK')
    print('FINAL_REBAKE_PHASE2_LODS_UNREAL_UNITY_OK')
    finalization.unity_asset_index='08'
    stable_objects=set(bpy.data.objects)
    with patch.object(FinalRebakeLODs,'run') as lod_run, patch.object(
            baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',side_effect=RuntimeError('fail before LODs')):
        try:result=bpy.ops.object.polygroups_rebake_final_mesh(create_lods=True)
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'}
        assert not lod_run.called
    assert set(bpy.data.objects)==stable_objects
    # The Phase 2 checkbox is a property passed by its manual button only.
    # A plain Baking-section invocation must keep its default bake-only behavior.
    assert preparation.phase2_rebake_create_lods
    phase_state=(preparation.phase2_pipeline_state,preparation.phase2_pipeline_done,preparation.phase2_pipeline_total)
    with patch.object(FinalRebakeLODs,'run') as lod_run:
        assert bpy.ops.object.polygroups_rebake_final_mesh()=={'FINISHED'}
        assert not lod_run.called
    assert set(bpy.data.objects)==stable_objects
    assert phase_state==(preparation.phase2_pipeline_state,preparation.phase2_pipeline_done,preparation.phase2_pipeline_total)
    print('FINAL_REBAKE_LODS_MANUAL_ONLY_AND_SUCCESS_ONLY_OK')
print('FINAL_REBAKE_TESTS_OK')
