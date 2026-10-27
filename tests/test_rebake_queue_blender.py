"""Real queue: all repairs, changed-UV packing, Cycles, LODs and final exports."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import addon_utils
import bmesh
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable('uvpackmaster4',default_set=True)
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import baking,rebake_final,rebake_queue,sequential_jobs
from polygroups_generator.operators.uvpackmaster_controls import OBJECT_OT_polygroups_uvpackmaster_pack
from polygroups_generator.operators.repair_mesh_folds import MESH_OT_polygroups_repair_mesh_folds
from polygroups_generator.custom_ui.schema import capture

context=bpy.context;scene=context.scene
p=scene.polygroups_model_preparation_settings
s=scene.polygroups_mesh_finalization_settings
bake=scene.polygroups_baking_settings
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
bake.bake_base_color=True;bake.bake_normal=False;bake.bake_artifact_mask=False;bake.bake_artifact_autofill=False
bake.auto_pack_uv_before_bake=True;bake.use_auto_cage=True;bake.use_smart_cage=False
bake.autogenerate_smart_cage=False;bake.bake_resolution=16
p.phase2_run_engine='FAB';p.fold_repair_zero_area=False;p.fold_repair_stretched_triangles=False
s.smart_lods_count=1;s.smart_lods_target_1=8;s.smart_lods_prepare_mode='UNREAL'
assert all(getattr(p,name) for name in ('phase2_rebake_repair_mesh','phase2_rebake_repair_folds',
    'phase2_rebake_repair_coincident','phase2_rebake_repair_zero_area','phase2_rebake_repair_stretched',
    'phase2_rebake_repack_uv'))


def fixture(index,folder):
    asset=f'Queue_00_{index:02d}'
    col=bpy.data.collections.new(asset+'_Collection');scene.collection.children.link(col)
    high_col=bpy.data.collections.new(f'Generated.{index:03d}');scene.collection.children.link(high_col)
    bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=2,radius=1)
    source_data=bpy.data.meshes.new('Source '+asset);bm.to_mesh(source_data)
    high=bpy.data.objects.new(f'Resculpting_01_Highpoly_Generated.{index:03d}',source_data)
    high_col.objects.link(high)
    material=bpy.data.materials.new('Green '+asset);material.use_nodes=True
    material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(0,1,0,1)
    high.data.materials.append(material)
    edge=next(iter(bm.edges));vertex=edge.verts[0]
    _,duplicate=bmesh.utils.edge_split(edge,vertex,.5)
    bmesh.ops.triangulate(bm,faces=list(duplicate.link_faces));duplicate.co=vertex.co
    uv=bm.loops.layers.uv.new('UVMap')
    for edge in bm.edges:edge.seam=True
    for face in bm.faces:
        for loop,xy in zip(face.loops,((0,0),(.1,0),(.05,.1))):loop[uv].uv=xy
    data=bpy.data.meshes.new('Final '+asset);bm.to_mesh(data);bm.free()
    target=bpy.data.objects.new('SM_'+asset+'_MID',data);target.location.x=index*3;col.objects.link(target)
    image=bpy.data.images.new('T_'+asset+'_BaseColor',width=16,height=16)
    image.generated_color=(1,0,0,1);image.filepath_raw=str(folder/(image.name+'.png'));image.file_format='PNG';image.save()
    for number in range(2):
        material=bpy.data.materials.new(f'M_{asset}_{number}');material.use_nodes=True
        node=material.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
        target.data.materials.append(material)
    for face in target.data.polygons:face.material_index=face.index%2
    high.hide_viewport=high.hide_render=True;high.hide_set(True)
    context.view_layer.update()
    return target,high,Path(image.filepath),len(target.data.vertices)


with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_rebake_queue_') as directory:
    root=Path(directory);bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
    targets=[fixture(index,root) for index in (1,2)]
    bpy.ops.object.select_all(action='DESELECT')
    for target,_,_,_ in targets:target.select_set(True)
    context.view_layer.objects.active=targets[0][0]
    assert bpy.ops.object.polygroups_rebake_queue_edit(action='ADD')=={'FINISHED'}
    assert bpy.ops.object.polygroups_rebake_queue_edit(action='ADD')=={'FINISHED'}
    assert len(p.phase2_rebake_queue)==2
    assert bpy.ops.object.polygroups_rebake_queue_edit(action='REMOVE',index=1)=={'FINISHED'}
    assert len(p.phase2_rebake_queue)==1
    assert bpy.ops.object.polygroups_rebake_queue_edit(action='ADD')=={'FINISHED'}
    panel=capture(context,1);assert not panel.errors,panel.errors
    props={binding[2] for binding in panel.bindings.values() if binding[0]=='property'}
    assert {'phase2_rebake_repair_mesh','phase2_rebake_repair_zero_area','phase2_rebake_repack_uv'}<=props
    rebake_button=next(binding[2] for binding in panel.bindings.values()
                       if binding[0]=='operator' and binding[1]=='object.polygroups_rebake_final_mesh')
    assert rebake_button.use_queue and rebake_button.repair_mesh
    edits=[binding[2] for binding in panel.bindings.values()
           if binding[0]=='operator' and binding[1]=='object.polygroups_rebake_queue_edit']
    assert {edit.index for edit in edits if edit.action=='REMOVE'}=={0,1}
    pack_calls=[];launch_order=[]
    real_pack=OBJECT_OT_polygroups_uvpackmaster_pack.execute
    real_launch=baking.OBJECT_OT_polygroups_bake_task._launch_pass
    def packed(operator,ctx):
        assert len(ctx.selected_objects)==1 and ctx.active_object in [t[0] for t in targets]
        pack_calls.append(ctx.active_object.name)
        return real_pack(operator,ctx)
    def launched(task,ctx,*args):
        assert not task.target.get('polygroups_rebake_uv_needs_pack')
        assert not bpy.ops.object.polygroups_rebake_queue_edit.poll()
        launch_order.append(task.target.name)
        return real_launch(task,ctx,*args)
    original_files={path:path.read_bytes() for _,_,path,_ in targets}
    with patch.object(OBJECT_OT_polygroups_uvpackmaster_pack,'execute',packed), \
         patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',launched):
        assert bpy.ops.object.polygroups_rebake_final_mesh(use_queue=True,repair_mesh=True,
            create_lods=True,export_selected=True)=={'FINISHED'}
    assert launch_order==pack_calls==[target.name for target,_,_,_ in targets],(launch_order,pack_calls)
    assert all(entry.state=='DONE' for entry in p.phase2_rebake_queue)
    assert not p.phase2_rebake_queue_running and p.phase2_rebake_queue_progress==100
    assert sequential_jobs.ACTIVE_JOB is None and baking._ACTIVE_BAKE_TASK is None
    for target,high,path,before_vertices in targets:
        assert len(target.data.vertices)==before_vertices-1
        assert len(target.data.materials)==2 and all(face.material_index in (0,1) for face in target.data.polygons)
        assert path.read_bytes()!=original_files[path]
        asset=target.name[3:-4]
        assert (root/'!Blend'/(asset+'.blend')).is_file()
        assert list((root/'!Unreal').rglob(target.name+'.fbx'))
        assert high.hide_viewport and high.hide_render
    print('REBAKE_QUEUE_REPAIR_PACK_CYCLES_LODS_EXPORT_OK',flush=True)

    # Unchanged UV skips packing on a second run; only this toggle controls repair.
    with patch.object(OBJECT_OT_polygroups_uvpackmaster_pack,'execute') as no_pack:
        assert bpy.ops.object.polygroups_rebake_final_mesh(use_queue=True,repair_mesh=True)=={'FINISHED'}
        assert not no_pack.called

    # Stop at a failed second mesh; never discard the first completed item.
    preserved=targets[1][2].read_bytes()
    def fail_second(task,ctx,*args):
        if task.target==targets[1][0]:raise RuntimeError('injected second-mesh failure')
        return real_launch(task,ctx,*args)
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass',fail_second):
        try:result=bpy.ops.object.polygroups_rebake_final_mesh(use_queue=True,repair_mesh=True)
        except RuntimeError:result={'CANCELLED'}
    assert result=={'CANCELLED'}
    assert [entry.state for entry in p.phase2_rebake_queue]==['DONE','FAILED']
    assert targets[1][2].read_bytes()==preserved and not p.phase2_rebake_queue_running
    assert sequential_jobs.ACTIVE_JOB is None
    assert bpy.ops.object.polygroups_phase2_reset_state()=={'FINISHED'}
    assert len(p.phase2_rebake_queue)==2 and all(entry.state=='PENDING' for entry in p.phase2_rebake_queue)

    # A missing entry is found by whole-list preflight before any bake begins.
    p.phase2_rebake_queue.add()
    with patch.object(baking.OBJECT_OT_polygroups_bake_task,'_launch_pass') as no_bake:
        try:result=bpy.ops.object.polygroups_rebake_final_mesh(use_queue=True,repair_mesh=True)
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'} and not no_bake.called
    assert bpy.ops.object.polygroups_rebake_queue_edit(action='CLEAR')=={'FINISHED'}
    assert not len(p.phase2_rebake_queue)
    bpy.ops.object.select_all(action='DESELECT');targets[0][0].select_set(True);context.view_layer.objects.active=targets[0][0]
    with patch.object(rebake_queue.OBJECT_OT_polygroups_rebake_queue_run,'execute') as no_queue:
        assert bpy.ops.object.polygroups_rebake_final_mesh(use_queue=True,repair_mesh=True)=={'FINISHED'}
        assert not no_queue.called
    # Packing failure leaves a dirty marker so a retry still packs even if the
    # already-applied repair no longer changes UV on the second attempt.
    target=targets[0][0]
    session=rebake_final.FinalRebakeSession(context,target,bake,repair_mesh=True)
    def changed_uv(operator,ctx):
        target.data.uv_layers.active.data[0].uv.x+=.001
        return {'FINISHED'}
    with patch.object(MESH_OT_polygroups_repair_mesh_folds,'execute',changed_uv), \
         patch.object(OBJECT_OT_polygroups_uvpackmaster_pack,'execute',lambda self,ctx:{'CANCELLED'}):
        try:session.repair_target()
        except RuntimeError as error:assert 'UV repack' in str(error)
        else:raise AssertionError('Packing failure must stop before baking')
    assert target.get('polygroups_rebake_uv_needs_pack')
    retry_calls=[]
    def retry_pack(operator,ctx):
        retry_calls.append(ctx.active_object)
        return real_pack(operator,ctx)
    with patch.object(MESH_OT_polygroups_repair_mesh_folds,'execute',lambda self,ctx:{'FINISHED'}), \
         patch.object(OBJECT_OT_polygroups_uvpackmaster_pack,'execute',retry_pack):
        session.repair_target()
    assert retry_calls==[target] and not target.get('polygroups_rebake_uv_needs_pack')
    def changed_geometry(operator,ctx):
        target.data.vertices[0].co.x+=.0001
        return {'FINISHED'}
    with patch.object(MESH_OT_polygroups_repair_mesh_folds,'execute',changed_geometry), \
         patch.object(OBJECT_OT_polygroups_uvpackmaster_pack,'execute') as no_pack:
        session.repair_target()
        assert not no_pack.called
    session.close(False)
    assert not any(image.name.startswith('ReBake_') for image in bpy.data.images)
print('REBAKE_QUEUE_MANAGEMENT_FAILURE_AND_SINGLE_FALLBACK_OK',flush=True)
