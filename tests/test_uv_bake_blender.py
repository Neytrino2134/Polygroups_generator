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
assert s.uv_bake_resolution=='2048'  # default 2K
s.uv_bake_resolution='1024'  # smallest choice keeps the test light


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
    # x, y on the RES grid of the source; the baked image is OUT pixels wide (Output Resolution).
    size=image.size[0];x=int((x+.5)*size/RES);y=int((y+.5)*size/RES)
    return list(image.pixels[(y*size+x)*4:(y*size+x)*4+4])


with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'uvbake.blend'))
    # 1. Duplicate: a _UVBake copy gets the new material; the source stays as it was.
    obj,mat=source_mesh()
    s.uv_bake_duplicate=True
    assert bpy.ops.object.polygroups_uv_bake()=={'FINISHED'},s.uv_bake_status
    copy=bpy.data.objects['SM_Rock_01_01_MID_UVBake']
    assert list(obj.data.materials)==[mat] and obj.data.uv_layers['UVMap'].active_render
    assert copy.data!=obj.data and copy.data.uv_layers.active.name=='UVMap'
    assert len(copy.data.uv_layers)==1 and copy.data.uv_layers['UVMap'].active_render
    assert copy.users_collection[0].name=='Generated_UVBake.001'
    new_mat=copy.data.materials[0];assert new_mat.name=='M_SM_Rock_01_01_MID_UVBake'
    base=bpy.data.images['SM_Rock_01_01_MID_UVBake_BaseColor']
    normal=bpy.data.images['SM_Rock_01_01_MID_UVBake_Normal']
    mask=bpy.data.images['SM_Rock_01_01_MID_UVBake_MergeMask']
    assert tuple(base.size)==tuple(normal.size)==tuple(mask.size)==(1024,1024),tuple(base.size)
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
    # Running again keeps the previous copy in its own collection.
    copy.select_set(False);obj.select_set(True);ctx.view_layer.objects.active=obj
    assert bpy.ops.object.polygroups_uv_bake()=={'FINISHED'},s.uv_bake_status
    assert ctx.object != copy and ctx.object.users_collection[0].name=='Generated_UVBake.002'
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

    # The new actions process every selected mesh, even when each starts with one map.
    obj, _ = source_mesh()
    obj.name = 'Retopo_03.007'
    obj.data.uv_layers.remove(obj.data.uv_layers['UVMap.001'])
    for loop in obj.data.uv_layers['UVMap'].data:
        loop.uv.x += 2
    other = obj.copy()
    other.data = obj.data.copy()
    scene.collection.objects.link(other)
    other.name = 'Retopo_03.008'
    other.select_set(True)
    sources = (obj, other)
    original_uvs = {mesh: [tuple(loop.uv) for loop in mesh.data.uv_layers['UVMap'].data] for mesh in sources}
    s.uv_bake_duplicate = True
    before_objects = set(bpy.data.objects)
    assert bpy.ops.object.polygroups_uv_bake(action='CREATE') == {'FINISHED'}
    assert set(bpy.data.objects) == before_objects
    for mesh in sources:
        layers = mesh.data.uv_layers
        assert layers.active.name == 'UVMap_New' and layers['UVMap'].active_render
        assert [tuple(loop.uv) for loop in layers.active.data] == original_uvs[mesh]
        layers.remove(layers.active)

    # Test the PACK call boundary with deterministic moved UVs, then run actual Cycles transfer.
    from unittest.mock import patch
    from polygroups_generator.operators.uvpackmaster_controls import OBJECT_OT_polygroups_uvpackmaster_pack

    def pack(operator, context):
        mesh = context.active_object
        assert set(context.selected_objects) == {mesh}
        assert mesh.data.uv_layers.active.name == 'UVMap_New'
        for loop in mesh.data.uv_layers.active.data:
            loop.uv.x -= 2
        return {'FINISHED'}

    bpy.types.Scene.uvpm4_props = bpy.props.BoolProperty()
    try:
        s.uv_bake_duplicate = True
        with patch.object(OBJECT_OT_polygroups_uvpackmaster_pack, 'execute', pack):
            assert bpy.ops.object.polygroups_uv_bake(action='PACK') == {'FINISHED'}
            packed = tuple(ctx.selected_objects)
            assert len(packed) == 2
            assert {mesh.name for mesh in packed} == {'Retopo_03_UVBake.007', 'Retopo_03_UVBake.008'}
            for mesh in packed:
                assert len(mesh.data.uv_layers) == 1 and mesh.data.uv_layers.active.name == 'UVMap'
                assert all(0 <= loop.uv.x <= 1 for loop in mesh.data.uv_layers.active.data)
                mesh.select_set(False)
            for mesh in sources:
                mesh.select_set(True)
            ctx.view_layer.objects.active = obj
            assert bpy.ops.object.polygroups_uv_bake(action='PACK_BAKE') == {'FINISHED'}
            assert len(ctx.selected_objects) == 2 and not set(ctx.selected_objects).intersection(packed)
            for mesh in ctx.selected_objects:
                assert len(mesh.data.uv_layers) == 1 and mesh.data.uv_layers.active.name == 'UVMap'
                assert mesh.data.materials[0].node_tree.nodes[C.BAKE_BASE_COLOR_NODE].image
                assert any(node.type == 'UVMAP' and node.uv_map == 'UVMap'
                           for node in mesh.data.materials[0].node_tree.nodes)
        for mesh in sources:
            assert len(mesh.data.uv_layers) == 1
            assert [tuple(loop.uv) for loop in mesh.data.uv_layers.active.data] == original_uvs[mesh]

        for mesh in ctx.selected_objects:
            mesh.select_set(False)
        other.data.uv_layers.active.name = 'OtherUV'
        for mesh, color in zip(sources, ((1, 0, 0, 1), (0, 0, 1, 1))):
            mesh.select_set(True)
            material = bpy.data.materials.new(mesh.name + '_Color')
            material.use_nodes = True
            material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = color
            mesh.data.materials[0] = material
        ctx.view_layer.objects.active = obj
        pack_calls = []

        def pack_together(operator, context):
            targets = sorted(context.selected_objects, key=lambda mesh: mesh.name)
            assert len(targets) == 2
            pack_calls.append(targets)
            for index, mesh in enumerate(targets):
                assert mesh.data.uv_layers.active.name.endswith('_New')
                for loop in mesh.data.uv_layers.active.data:
                    loop.uv.x = (loop.uv.x - 2) * .4 + .05 + index * .5
            return {'FINISHED'}

        s.uv_bake_pack_bake_mode = 'TOGETHER'
        with patch.object(OBJECT_OT_polygroups_uvpackmaster_pack, 'execute', pack_together):
            assert bpy.ops.object.polygroups_uv_bake(action='PACK_BAKE') == {'FINISHED'}
        copies = tuple(ctx.selected_objects)
        assert len(pack_calls) == 1 and set(pack_calls[0]) == set(copies)
        assert len({mesh.data.materials[0] for mesh in copies}) == 1
        assert {mesh.data.uv_layers.active.name for mesh in copies} == {'UVMap', 'OtherUV'}
        assert all(len(mesh.data.uv_layers) == 1 and mesh.data.uv_layers.active.active_render for mesh in copies)
        atlas = bpy.data.images[copies[0][C.BAKE_BASE_COLOR_IMAGE_PROP]]
        assert all(mesh[C.BAKE_BASE_COLOR_IMAGE_PROP] == atlas.name for mesh in copies)
        left, right = pixel(atlas, 3, 8), pixel(atlas, 12, 8)
        assert left[0] > .9 and left[2] < .1 and right[2] > .9 and right[0] < .1, (left, right)
        mask = bpy.data.images[copies[0][C.BAKE_ALPHA_IMAGE_PROP]]
        assert pixel(mask, 3, 8)[0] > .9 and pixel(mask, 12, 8)[0] > .9 and pixel(mask, 8, 8)[0] < .1
        assert all([tuple(loop.uv) for loop in mesh.data.uv_layers.active.data] == original_uvs[mesh]
                   for mesh in sources)
    finally:
        del bpy.types.Scene.uvpm4_props
    print('UV_BAKE_SELECTED_CREATE_PACK_AND_TRANSFER_OK')
