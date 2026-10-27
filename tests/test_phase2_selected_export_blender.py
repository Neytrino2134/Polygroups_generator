"""Actual selected-only Phase 2 exports, overwrite, and clean selected blend files."""
import hashlib,json,struct,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_blend_export as blends
ctx=bpy.context
p=ctx.scene.polygroups_model_preparation_settings
s=ctx.scene.polygroups_mesh_finalization_settings
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)


def cube(name,collection):
    bpy.ops.mesh.primitive_cube_add(location=(2,7,3))
    obj=ctx.object;obj.name=name
    for old in list(obj.users_collection):old.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def select(objects,active=None):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:obj.select_set(True)
    ctx.view_layer.objects.active=active or objects[0]
    ctx.view_layer.update()


def glb_mesh_names(path):
    data=path.read_bytes()
    size,kind=struct.unpack_from('<II',data,12)
    doc=json.loads(data[20:20+size].decode('utf-8'))
    return {node['name'] for node in doc['nodes'] if 'mesh' in node}


with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
    objects={}
    for version in ('01','02'):
        base='Crystals_Pack_02_'+version
        col=bpy.data.collections.new(base+'_Collection');ctx.scene.collection.children.link(col)
        image=bpy.data.images.new(base+'_Color',width=8,height=8)
        image.filepath_raw=str(root/(image.name+'.png'));image.file_format='PNG';image.save()
        image.source='FILE';image.reload()
        material=bpy.data.materials.new(base+'_Material');material.use_nodes=True
        material.node_tree.nodes.new('ShaderNodeTexImage').image=image
        for level in ('MID','LOD0','LOD1'):
            objects[version,level]=cube('SM_'+base+'_'+level,col)
            objects[version,level].data.materials.append(material)
    marker=bpy.data.objects.new('SelectionMarker',None);ctx.scene.collection.objects.link(marker)
    selected=objects['01','LOD1']
    select([selected,marker],marker)
    p.phase2_export_engine='FAB'
    p.phase2_export_glb=p.phase2_export_gltf=p.phase2_export_fbx=True
    s.unreal_glb_mode=s.unreal_gltf_mode='COMBINED'
    folder=root/'!Unreal'
    (folder/'FBX').mkdir(parents=True)
    untouched=folder/'FBX'/'SM_Crystals_Pack_02_01_LOD0.fbx';untouched.write_bytes(b'UNSELECTED FILE')
    glb=folder/'GLB'/'Crystals_Pack_02_01.glb';glb.parent.mkdir();glb.write_bytes(b'OLD SELECTED FILE')
    assert bpy.ops.object.polygroups_phase2_export(selected_only=True)=={'FINISHED'}
    assert glb_mesh_names(glb)=={selected.name}
    assert json.loads((folder/'MeshInfo.json').read_text())['totals']['meshes']==1
    assert untouched.read_bytes()==b'UNSELECTED FILE'
    assert not list(folder.rglob('*Crystals_Pack_02_02*'))
    assert set(ctx.selected_objects)=={selected,marker} and ctx.active_object==marker
    previous=hashlib.sha256(glb.read_bytes()).hexdigest()
    selected.data.vertices[0].co.x+=.25;selected.data.update()
    assert bpy.ops.object.polygroups_phase2_export(selected_only=True)=={'FINISHED'}
    assert hashlib.sha256(glb.read_bytes()).hexdigest()!=previous
    print('SELECTED_UNREAL_EXPORT_OVERWRITE_OK')
    unity_col=bpy.data.collections.new('Unity_00_01_LOD0_Collection');ctx.scene.collection.children.link(unity_col)
    unity0=cube('Unity_00_01',unity_col);unity0['unity_prepared']=True
    unity1=cube('Unity_00_01.LOD1',unity_col);unity1['unity_prepared']=True
    select([unity1,marker],marker)
    p.phase2_export_engine='UNITY'
    s.unity_export_directory=str(root/'Unity')
    s.unity_export_overwrite=False;s.unity_export_clear_asset_folder=True
    s.unity_export_autosave=False;s.unity_use_auto_rig_pro=False
    s.unity_glb_mode=s.unity_gltf_mode='COMBINED'
    unity_glb=root/'Unity'/'GLB'/'Unity_00_01.glb';unity_glb.parent.mkdir(parents=True);unity_glb.write_bytes(b'OLD')
    assert bpy.ops.object.polygroups_phase2_export(selected_only=True)=={'FINISHED'}
    assert glb_mesh_names(unity_glb)=={unity1.name}
    assert not s.unity_export_overwrite and s.unity_export_clear_asset_folder
    assert set(ctx.selected_objects)=={unity1,marker} and ctx.active_object==marker
    assert bpy.ops.object.polygroups_phase2_export(selected_only=True)=={'FINISHED'}
    print('SELECTED_UNITY_EXPORT_OVERWRITE_OK')
    # Select one mesh in each of two multi-mesh collections. An unselected
    # parent must not leak into either the exported scene or its object data.
    child=objects['01','LOD1'];parent=objects['01','MID']
    world=child.matrix_world.copy();child.parent=parent;child.matrix_world=world
    selected_b=objects['02','MID']
    select([child,selected_b,marker],marker)
    p.phase2_blend_export_pack=True
    p.phase2_blend_export_reset_y=False
    p.phase2_blend_export_generated=True
    output=root/'!Blend';output.mkdir()
    asset_a=output/'Crystals_Pack_02_01.blend';asset_a.write_bytes(b'OLD BLEND')
    generated=bpy.data.collections.new('Generated.999');ctx.scene.collection.children.link(generated)
    cube('Resculpting_01_Highpoly_Generated.999',generated)
    select([child,selected_b,marker],marker)
    names_before={o:o.name for o in bpy.data.objects}
    memberships={o:tuple(o.users_collection) for o in bpy.data.objects}
    positions={o:o.matrix_world.copy() for o in (child,parent,selected_b)}
    assert bpy.ops.object.polygroups_phase2_export_blend(selected_only=True)=={'FINISHED'},p.phase2_blend_export_status
    assert sorted(file.name for file in output.glob('*.blend'))==['Crystals_Pack_02_01.blend','Crystals_Pack_02_02.blend']
    for version,obj in (('01',child),('02',selected_b)):
        path=output/f'Crystals_Pack_02_{version}.blend'
        with bpy.data.libraries.load(str(path)) as (src,dst):
            assert {name for name in src.objects if name.startswith('SM_')}=={obj.name},src.objects
            assert src.collections==[f'Crystals_Pack_02_{version}_Collection'],src.collections
            assert src.images==[f'Crystals_Pack_02_{version}_Color'],src.images
    assert all(o.name==name and tuple(o.users_collection)==memberships[o] for o,name in names_before.items())
    assert all(o.matrix_world==matrix for o,matrix in positions.items())
    assert child.parent==parent
    assert set(ctx.selected_objects)=={child,selected_b,marker} and ctx.active_object==marker
    assert not (output/'Generated.999.blend').exists()
    print('SELECTED_BLEND_EXACT_SUBSETS_OK')
    # Rewrite the same destination and honor the existing reset-Y option.
    p.phase2_blend_export_reset_y=True
    before=hashlib.sha256(asset_a.read_bytes()).hexdigest()
    assert bpy.ops.object.polygroups_phase2_export_blend(selected_only=True)=={'FINISHED'}
    assert hashlib.sha256(asset_a.read_bytes()).hexdigest()!=before
    with bpy.data.libraries.load(str(asset_a)) as (src,dst):dst.objects=[child.name]
    loaded=dst.objects[0]
    assert loaded.parent is None and abs(loaded.location.y)<1e-6
    bpy.data.objects.remove(loaded,do_unlink=True)
    assert child.parent==parent and child.matrix_world==positions[child]
    stable=asset_a.read_bytes()
    with patch.object(blends,'export_collection_blend',side_effect=RuntimeError('injected selected blend failure')):
        try:result=bpy.ops.object.polygroups_phase2_export_blend(selected_only=True)
        except RuntimeError:result={'CANCELLED'}
        assert result=={'CANCELLED'}
    assert asset_a.read_bytes()==stable
    assert not list(output.glob('.selected-*'))
    assert all(o.name==name and tuple(o.users_collection)==memberships[o] for o,name in names_before.items())
    assert set(ctx.selected_objects)=={child,selected_b,marker} and ctx.active_object==marker
    print('SELECTED_BLEND_OVERWRITE_AND_FAILURE_RESTORE_OK')
    select([marker],marker)
    assert bpy.ops.object.polygroups_phase2_export(selected_only=True)=={'CANCELLED'}
    assert bpy.ops.object.polygroups_phase2_export_blend(selected_only=True)=={'CANCELLED'}
    from polygroups_generator.custom_ui.schema import capture
    tree=capture(ctx,1);assert not tree.errors,tree.errors
    assert any(binding[0]=='operator' and binding[1]=='object.polygroups_phase2_export'
               and getattr(binding[2],'selected_only',False) for binding in tree.bindings.values())
    assert any(binding[0]=='operator' and binding[1]=='object.polygroups_phase2_export_blend'
               and getattr(binding[2],'selected_only',False) for binding in tree.bindings.values())
print('PHASE2_SELECTED_EXPORT_TESTS_OK')
