"""Clear All Files (Start from Scratch / Clear Phase 2 Files) and exact texture / material names."""
from pathlib import Path
import sys,tempfile
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core import final_cleanup as core
from polygroups_generator.core.datablock_names import take_name,drop_unused,remove_numbered_files
from polygroups_generator.operators import final_cleanup as ops
scene=bpy.context.scene


def layout(root):
    files=['!Blend/Generated.001.blend','!Unreal/SM_A_MID.fbx','!Renders/a.png','Textures/A/T_A_BaseColor.png',
           'Bakes/A/A_Bake_BaseColor.png','batch_reports/r.txt','01_Source/Textures/src.png','01_Source/src.blend',
           'other.blend','work.blend1','blender/old.blend','blender/Textures/t.png','keep.txt']
    for name in files:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'x')


def fill_scene():
    for name in ('Generated.001','A_01_01_Collection','Sources'):
        col=bpy.data.collections.new(name);scene.collection.children.link(col)
        mesh=bpy.data.meshes.new(name+'_mesh');col.objects.link(bpy.data.objects.new(name+'_obj',mesh))
    inner=bpy.data.collections.new('A_01_01_LOD0_Collection');bpy.data.collections['A_01_01_Collection'].children.link(inner)
    inner.objects.link(bpy.data.objects.new('lod',bpy.data.meshes.new('lod')))
    bpy.data.materials.new('Unused')


for mode in ('ALL','PHASE2'):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)/'Pack'/'Asset';root.mkdir(parents=True)
        bpy.ops.wm.read_homefile(use_empty=True);scene=bpy.context.scene
        bpy.ops.wm.save_as_mainfile(filepath=str(root/'work.blend'))
        layout(root);fill_scene()
        result=core.scan_reset(root,root/'work.blend',mode)
        files,size,errors=core.delete_reset(result)
        assert not errors,errors
        removed,objects=ops.clear_asset_collections(scene)
        ops.purge_all_unused()
        exists=lambda name:(root/name).exists()
        assert exists('work.blend') and exists('keep.txt') and exists('01_Source/Textures/src.png') and exists('01_Source/src.blend')
        assert not exists('!Blend') and not exists('!Unreal') and not exists('!Renders') and not exists('Textures')
        assert not exists('blender/Textures')
        if mode=='ALL':
            for name in ('Bakes','batch_reports','other.blend','work.blend1','blender/old.blend'):
                assert not exists(name),name
        else:
            for name in ('Bakes/A/A_Bake_BaseColor.png','batch_reports/r.txt','other.blend','work.blend1','blender/old.blend'):
                assert exists(name),name
        assert removed==3 and objects==3,(removed,objects)
        assert set(bpy.data.collections.keys())=={'Sources'} and 'Unused' not in bpy.data.materials
        assert set(bpy.data.objects.keys())=={'Sources_obj'}
print('CLEAR_ALL_FILES_OK')

# A re-created texture / material takes the exact name; the stale one is replaced or dropped.
old=bpy.data.images.new('T_X_BaseColor',8,8);mat=bpy.data.materials.new('M_X');mat.use_nodes=True
node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=old
new=bpy.data.images.new('tmp',8,8)
take_name(bpy.data.images,new,'T_X_BaseColor',replace=True)
assert new.name=='T_X_BaseColor' and node.image==new and len([i for i in bpy.data.images if i.name.startswith('T_X')])==1
holder=bpy.data.meshes.new('holder');holder.materials.append(mat)
aside=[];copy=bpy.data.materials.new('tmp')
take_name(bpy.data.materials,copy,'M_X',aside=aside)
assert copy.name=='M_X' and mat.name=='M_X_Old' and aside==[mat]
drop_unused(aside)
assert 'M_X_Old' in bpy.data.materials  # still used
holder.materials[0]=copy
drop_unused(aside)
assert 'M_X_Old' not in bpy.data.materials  # unused stale material removed
with tempfile.TemporaryDirectory() as directory:
    folder=Path(directory)
    for name in ('T_X_BaseColor.png','T_X_BaseColor.001.png','T_X_BaseColor.002.png','T_X_Normal.001.png'):
        (folder/name).write_bytes(b'x')
    assert remove_numbered_files(folder/'T_X_BaseColor.png')==2
    assert sorted(p.name for p in folder.iterdir())==['T_X_BaseColor.png','T_X_Normal.001.png']
print('EXACT_DATABLOCK_NAMES_OK')
