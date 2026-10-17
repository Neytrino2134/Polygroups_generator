"""Temporary bake masks are not material opacity and never enter Unity/FAB exports."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import baking, mesh_export
from polygroups_generator.operators.fab_preparation import _texture_suffix

obj = bpy.data.objects['Cube']
material = bpy.data.materials.new('MaskTest')
material.use_nodes = True
obj.data.materials.clear()
obj.data.materials.append(material)
nodes = material.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
mask_nodes = []
for suffix in ('MergeMask', 'ArtifactMask', 'AlphaMap'):
    image = bpy.data.images.new('Tree_' + suffix, width=4, height=4)
    node = nodes.new('ShaderNodeTexImage')
    node.image = image
    node.label = 'Opacity'
    assert _texture_suffix(image, node) == suffix
    mask_nodes.append(node)
material.node_tree.links.new(mask_nodes[1].outputs['Color'], bsdf.inputs['Alpha'])
assert not list(mesh_export._export_texture_images([obj]))
images = [node.image for node in mask_nodes]
with TemporaryDirectory() as temp:
    root = Path(temp)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Working.blend'))
    bs = bpy.context.scene.polygroups_baking_settings
    bs.bake_resolution = 4
    merge = baking._ensure_target_image(obj, bs, baking.BAKE_ALPHA_IMAGE_PROP, 'MergeMask', 'Non-Color')
    artifact = baking._ensure_target_image(obj, bs, baking.BAKE_ARTIFACT_IMAGE_PROP, 'ArtifactMask', 'Non-Color')
    assert merge.name.endswith('_MergeMask') and artifact.name.endswith('_ArtifactMask')
    # The marker preserves identity even if an older preparation renamed the image.
    artifact.name = 'Tree_opacity'
    assert _texture_suffix(artifact, mask_nodes[1]) == 'ArtifactMask'
    detached = mesh_export._detach_export_alpha_maps([obj])
    try:
        assert all(node.image is None for node in mask_nodes)
        assert not bsdf.inputs['Alpha'].is_linked
        for fmt, ext in [('FBX', 'fbx'), ('GLB', 'glb'), ('GLTF', 'gltf')]:
            path = root / ('Unreal.' + ext)
            assert 'FINISHED' in mesh_export._export_selected_object(str(path), fmt)
            assert path.is_file()
            if ext == 'gltf':
                assert not json.loads(path.read_text()).get('images')
    finally:
        mesh_export._restore_export_alpha_maps(detached)
    obj['unity_prepared'] = True
    settings = bpy.context.scene.polygroups_mesh_finalization_settings
    settings.unity_export_directory = str(root / 'Unity')
    settings.unity_export_all_renders = False
    settings.unity_export_fbx = settings.unity_export_gltf = True
    settings.unity_export_autosave = False
    assert bpy.ops.object.polygroups_export_unity() == {'FINISHED'}
    assert [node.image for node in mask_nodes] == images
    assert bsdf.inputs['Alpha'].is_linked
    gltf = next((root / 'Unity').rglob('*.gltf'))
    data = json.loads(gltf.read_text())
    assert not data.get('images') and not data.get('textures')
    assert list((root / 'Unity').rglob('*.fbx'))
    assert not list((root / 'Unity').rglob('*.png'))
    # Legacy renamed diagnostic masks still carry their baking node identity.
    mask_nodes[1].image.name = 'Tree_Tropic_19_01_opacity'
    mask_nodes[1].name = 'PolyGroups Bake Artifact Mask'
    assert _texture_suffix(mask_nodes[1].image, mask_nodes[1]) == 'ArtifactMask'
    opacity = bpy.data.images.new('RealMaterial_opacity', width=4, height=4)
    opacity_node = nodes.new('ShaderNodeTexImage')
    opacity_node.image = opacity
    assert _texture_suffix(opacity, opacity_node) == 'Opacity'
    assert list(mesh_export._export_texture_images([obj])) == [opacity]
print('BAKE_MASK_EXPORT_PASSED')
