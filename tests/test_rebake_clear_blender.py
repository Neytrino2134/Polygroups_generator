"""Clear Before ReBake: MID/HIGH materials and their own textures, asset texture folders and export
textures go away; Highpoly source textures, other assets and other files stay."""
from pathlib import Path
import sys,tempfile
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.rebake_clear import clear_before_rebake
ctx=bpy.context
p=ctx.scene.polygroups_model_preparation_settings
assert p.phase2_rebake_clear_materials  # on by default


def mesh(name,material=None,image=None):
    obj=bpy.data.objects.new(name,bpy.data.meshes.new(name));ctx.scene.collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
        if image:material.node_tree.nodes.new('ShaderNodeTexImage').image=image
    return obj


def material(name):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;return mat


with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'work.blend'))
    for name in ('Textures/A_01_01/T_A_01_01_BaseColor.png','Textures/A_01_01/T_A_01_01_BaseColor_Old.png',
                 'Textures/B_01_02/T_B_01_02_BaseColor.png','!Unreal/FBX/Textures/T_A_01_01_BaseColor.png',
                 '!Unreal/FBX/Textures/T_A_01_01_Normal.001.png','!Unreal/FBX/Textures/T_B_01_02_BaseColor.png',
                 '!Unreal/FBX/SM_A_01_01_MID.fbx','!Unreal/SM_A_01_01/Textures/T_A_01_01_Normal.png'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'x')
    shared=bpy.data.images.new('Highpoly_Source_BaseColor',4,4)  # also read by the Highpoly material
    own=bpy.data.images.new('T_A_01_01_BaseColor',4,4);old=bpy.data.images.new('T_A_01_01_BaseColor_Old',4,4)
    mid_mat=material('M_A_01_01');mid_mat.node_tree.nodes.new('ShaderNodeTexImage').image=old
    mid=mesh('SM_A_01_01_MID',mid_mat,own);mid.data.materials.append(material('M_A_01_01.001'))
    high=mesh('SM_A_01_01_HIGH',material('M_A_01_01_HIGH'),shared)
    source=mesh('Highpoly_Generated.001',material('Source'),shared)
    other=mesh('SM_B_01_02_MID',material('M_B_01_02'),bpy.data.images.new('T_B_01_02_BaseColor',4,4))
    summary=clear_before_rebake(ctx,[mid])
    assert not summary['errors'],summary
    assert not mid.data.materials and not high.data.materials
    for name in ('M_A_01_01','M_A_01_01.001','M_A_01_01_HIGH','T_A_01_01_BaseColor','T_A_01_01_BaseColor_Old'):
        assert name not in bpy.data.materials and name not in bpy.data.images,name
    assert 'Highpoly_Source_BaseColor' in bpy.data.images and source.data.materials[0].name=='Source'
    assert other.data.materials[0].name=='M_B_01_02' and 'T_B_01_02_BaseColor' in bpy.data.images
    exists=lambda name:(root/name).exists()
    assert not exists('Textures/A_01_01') and exists('Textures/B_01_02/T_B_01_02_BaseColor.png')
    assert not exists('!Unreal/FBX/Textures/T_A_01_01_BaseColor.png')
    assert not exists('!Unreal/FBX/Textures/T_A_01_01_Normal.001.png')
    assert exists('!Unreal/FBX/Textures/T_B_01_02_BaseColor.png') and exists('!Unreal/FBX/SM_A_01_01_MID.fbx')
    assert not exists('!Unreal/SM_A_01_01/Textures')
print('REBAKE_CLEAR_BEFORE_OK')
