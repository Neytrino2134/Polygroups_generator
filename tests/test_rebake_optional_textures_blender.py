"""Final ReBake never requires the MID's current textures: duplicates, missing images or no material."""
from pathlib import Path
import sys,tempfile
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import rebake_final as final
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
settings=scene.polygroups_baking_settings
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
settings.bake_resolution=32;settings.bake_margin=1;settings.bake_artifact_radius=0
settings.bake_artifact_autofill=False;settings.bake_artifact_mask=False
settings.use_auto_cage=False;settings.cage_extrusion=.2;settings.ray_distance=1
ASSET='Optional_Tex_01_03'


def make_pair():
    bpy.ops.mesh.primitive_plane_add(size=2)
    target=bpy.context.object;target.name=f'SM_{ASSET}_MID'
    generated=bpy.data.collections.new('Generated.003');scene.collection.children.link(generated)
    bpy.ops.mesh.primitive_plane_add(size=3)
    high=bpy.context.object;high.name='Resculpting_01_Highpoly_Generated.003'
    for col in list(high.users_collection):col.objects.unlink(high)
    generated.objects.link(high)
    mat=bpy.data.materials.new('Src');mat.use_nodes=True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.05,.8,.1,1)
    high.data.materials.append(mat)
    for obj in bpy.context.selected_objects:obj.select_set(False)
    target.select_set(True);bpy.context.view_layer.objects.active=target
    return target,high,generated


def clear(target,high,generated):
    bpy.data.objects.remove(target);bpy.data.objects.remove(high);bpy.data.collections.remove(generated)


with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    bpy.ops.wm.save_as_mainfile(filepath=str(directory/'optional.blend'))
    # 1. Duplicate BaseColor images (same file loaded twice) and no Normal at all.
    target,high,generated=make_pair()
    material=bpy.data.materials.new('M_'+ASSET);material.use_nodes=True;target.data.materials.append(material)
    base=bpy.data.images.new(f'T_{ASSET}_BaseColor',width=16,height=16)
    base.filepath_raw=str(directory/(base.name+'.png'));base.file_format='PNG';base.save()
    duplicate=bpy.data.images.load(base.filepath_raw,check_existing=False)
    assert duplicate!=base
    duplicate_name=duplicate.name
    # A leftover numbered copy on disk from an earlier run is removed after ReBake.
    numbered=directory/f'T_{ASSET}_BaseColor.001.png'
    numbered.write_bytes(Path(base.filepath_raw).read_bytes())
    for image in (base,duplicate):
        material.node_tree.nodes.new('ShaderNodeTexImage').image=image
    outputs,resolution=final.final_texture_outputs(target,settings)
    assert outputs['BaseColor'][0]==base and outputs['Normal'][0] is None
    assert outputs['Normal'][1]==directory/f'T_{ASSET}_Normal.png' and resolution==16
    assert bpy.ops.object.polygroups_rebake_final_mesh()=={'FINISHED'},settings.bake_task_message
    assert settings.bake_task_stage=='DONE',settings.bake_task_message
    assert (directory/f'T_{ASSET}_Normal.png').is_file()
    images={node.image for node in material.node_tree.nodes if node.type=='TEX_IMAGE'}
    assert duplicate_name not in bpy.data.images and base in images,images
    assert not any('.0' in image.name for image in bpy.data.images if image.name.startswith('T_')),list(bpy.data.images)
    assert not numbered.exists()
    normal=bpy.data.images.get(f'T_{ASSET}_Normal')
    bsdf=material.node_tree.nodes.get('Principled BSDF')
    assert bsdf.inputs['Normal'].links and normal in images
    clear(target,high,generated)
    print('REBAKE_DUPLICATE_AND_MISSING_TEXTURES_OK')
    # 2. MID without any material: textures go to Textures/<asset>, material is created.
    bpy.data.images.remove(base);bpy.data.images.remove(normal)
    target,high,generated=make_pair()
    assert not target.data.materials
    outputs,resolution=final.final_texture_outputs(target,settings)
    folder=directory/'Textures'/ASSET
    assert outputs['BaseColor']==(None,folder/f'T_{ASSET}_BaseColor.png') and resolution==32
    assert bpy.ops.object.polygroups_rebake_final_mesh()=={'FINISHED'},settings.bake_task_message
    assert settings.bake_task_stage=='DONE',settings.bake_task_message
    assert (folder/f'T_{ASSET}_BaseColor.png').is_file() and (folder/f'T_{ASSET}_Normal.png').is_file()
    material=target.data.materials[0]
    bsdf=material.node_tree.nodes.get('Principled BSDF')
    assert bsdf.inputs['Base Color'].links[0].from_node.image.name==f'T_{ASSET}_BaseColor'
    print('REBAKE_WITHOUT_MATERIAL_OK')
