"""UV Bake: textures move from the old UV map onto a mirrored new one (real Cycles bake),
with MergeMask, saved PNGs, Merge Materials properties, duplicate (_UVBake) and in-place modes."""
from pathlib import Path
import sys,tempfile
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import bake_constants as C
ctx=bpy.context;scene=ctx.scene
s=scene.polygroups_baking_settings
s.bake_margin=1
RES=16


def source_mesh():
    for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.mesh.primitive_plane_add(size=2)
    obj=ctx.object;obj.name='SM_Rock_01_01_MID'
    old=obj.data.uv_layers[0];old.name='UVMap'
    new=obj.data.uv_layers.new(name='UVMap.001')
    for loop_old,loop_new in zip(old.data,new.data):
        loop_new.uv=(1-loop_old.uv[0],loop_old.uv[1])  # the "repacked" map: mirrored in U
    old.active_render=True;obj.data.uv_layers.active=new
    image=bpy.data.images.new('T_Rock_Source',RES,RES)
    pixels=[]
    for y in range(RES):
        for x in range(RES):
            pixels+= [1,0,0,1] if x<RES//2 else [0,0,1,1]  # left red, right blue on the old UV
    image.pixels.foreach_set(pixels)
    image.filepath_raw=str(root/'T_Rock_Source.png');image.file_format='PNG';image.save()
    mat=bpy.data.materials.new('M_Rock_Source');mat.use_nodes=True
    node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
    mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    obj.data.materials.append(mat)
    return obj,mat


def pixel(image,x,y):
    values=list(image.pixels[(y*RES+x)*4:(y*RES+x)*4+4]);return values


with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'uvbake.blend'))
    # 1. Duplicate: a _UVBake copy gets the new material; the source stays as it was.
    obj,mat=source_mesh()
    s.uv_bake_duplicate=True
    assert bpy.ops.object.polygroups_uv_bake()=={'FINISHED'},s.uv_bake_status
    copy=bpy.data.objects['SM_Rock_01_01_MID_UVBake']
    assert list(obj.data.materials)==[mat] and obj.data.uv_layers['UVMap'].active_render
    assert copy.data!=obj.data and copy.data.uv_layers.active.name=='UVMap.001'
    assert copy.data.uv_layers['UVMap.001'].active_render
    new_mat=copy.data.materials[0];assert new_mat.name=='M_SM_Rock_01_01_MID_UVBake'
    base=bpy.data.images['SM_Rock_01_01_MID_UVBake_BaseColor']
    normal=bpy.data.images['SM_Rock_01_01_MID_UVBake_Normal']
    mask=bpy.data.images['SM_Rock_01_01_MID_UVBake_MergeMask']
    left,right=pixel(base,3,8),pixel(base,12,8)
    assert left[2]>.5 and left[0]<.2 and right[0]>.5 and right[2]<.2,(left,right)  # mirrored: left is blue now
    flat=pixel(normal,8,8)
    assert abs(flat[0]-.5)<.05 and abs(flat[1]-.5)<.05 and flat[2]>.9,flat
    assert pixel(mask,8,8)[0]>.99
    for image in (base,normal,mask):
        assert (root/'Bakes'/'SM_Rock_01_01_MID_UVBake'/(image.name+'.png')).is_file(),image.name
    for prop,image in ((C.BAKE_BASE_COLOR_IMAGE_PROP,base),(C.BAKE_NORMAL_IMAGE_PROP,normal),
                       (C.BAKE_ALPHA_IMAGE_PROP,mask),(C.BAKE_SOURCE_ALPHA_IMAGE_PROP,mask)):
        assert copy[prop]==image.name,prop
    assert new_mat.node_tree.nodes[C.BAKE_ALPHA_NODE].image==mask and copy[C.BAKE_TARGET_MATERIAL_PROP]==new_mat.name
    assert 'M_Rock_Source.001' not in bpy.data.materials  # temporary bake copies are gone
    # Running again replaces the copy and its textures (no .001).
    assert bpy.ops.object.polygroups_uv_bake()=={'FINISHED'},s.uv_bake_status
    names=[o.name for o in bpy.data.objects]+[i.name for i in bpy.data.images]+[m.name for m in bpy.data.materials]
    assert not [n for n in names if n.endswith('.001') and 'UVBake' in n],names
    print('UV_BAKE_DUPLICATE_OK')
    # 2. In place: the mesh itself gets the new material and active UV map.
    obj,mat=source_mesh();s.uv_bake_duplicate=False
    assert bpy.ops.object.polygroups_uv_bake()=={'FINISHED'},s.uv_bake_status
    assert 'SM_Rock_01_01_MID_UVBake' not in bpy.data.objects
    assert obj.data.materials[0].name=='M_SM_Rock_01_01_MID'
    assert obj.data.uv_layers.active.name=='UVMap.001' and obj.data.uv_layers['UVMap.001'].active_render
    base=bpy.data.images['SM_Rock_01_01_MID_BaseColor']
    assert pixel(base,3,8)[2]>.5 and pixel(base,12,8)[0]>.5
    print('UV_BAKE_IN_PLACE_OK')
    # 3. A tangent-space normal map is re-encoded for the new UV map: mirrored U flips its X.
    obj,mat=source_mesh();s.uv_bake_duplicate=True
    tilt=bpy.data.images.new('T_Rock_Normal',RES,RES);tilt.colorspace_settings.name='Non-Color'
    tilt.pixels.foreach_set([.75,.5,.93,1]*(RES*RES))
    tilt.filepath_raw=str(root/'T_Rock_Normal.png');tilt.file_format='PNG';tilt.save()
    tree=mat.node_tree;node=tree.nodes.new('ShaderNodeTexImage');node.image=tilt
    nmap=tree.nodes.new('ShaderNodeNormalMap')
    tree.links.new(node.outputs['Color'],nmap.inputs['Color'])
    tree.links.new(nmap.outputs['Normal'],tree.nodes['Principled BSDF'].inputs['Normal'])
    assert bpy.ops.object.polygroups_uv_bake()=={'FINISHED'},s.uv_bake_status
    value=pixel(bpy.data.images['SM_Rock_01_01_MID_UVBake_Normal'],8,8)
    assert abs(value[0]-.25)<.06 and abs(value[1]-.5)<.06,value
    print('UV_BAKE_NORMAL_TANGENT_OK')
