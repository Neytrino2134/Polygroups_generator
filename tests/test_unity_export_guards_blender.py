"""Missing/invalid ARP rigs must reject export before any scene or file mutation."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy
import addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import unity_preparation as up, turnaround_animation as ta
scene=bpy.context.scene
settings=scene.polygroups_mesh_finalization_settings
source=bpy.context.active_object
source['unity_prepared']=True
material=bpy.data.materials.new('TextureGuard')
material.use_nodes=True
canonical=bpy.data.images.new('Tree_12_01',width=4,height=4)
duplicate=bpy.data.images.new('Tree_12_01',width=4,height=4)
node=material.node_tree.nodes.new('ShaderNodeTexImage')
node.image=duplicate
source.data.materials.clear()
source.data.materials.append(material)
assert duplicate.name=='Tree_12_01.001'
settings.unity_use_auto_rig_pro=True
settings.unity_export_all_renders=True
matrix=source.matrix_world.copy()
with TemporaryDirectory() as directory:
    settings.unity_export_directory=str(Path(directory)/'MustNotExist')
    for invalid_armature in (False,True):
        if invalid_armature:
            rig=bpy.data.objects.new('NotARP',bpy.data.armatures.new('NotARP'))
            scene.collection.objects.link(rig)
            rig.select_set(True)
        for invocation in ('EXEC_DEFAULT','INVOKE_DEFAULT'):
            try:
                result=bpy.ops.object.polygroups_export_unity(invocation)
                assert result=={'CANCELLED'}
            except RuntimeError as error:
                assert 'Auto-Rig Pro rig' in str(error)
            assert not Path(settings.unity_export_directory).exists()
            assert not scene.polygroups_render_settings.is_running and ta._ACTIVE_RENDER_TASK is None
            assert source.matrix_world==matrix and duplicate.name=='Tree_12_01.001'
    up.normalize_unity_texture_names([source])
    assert duplicate.name=='Tree_12_01' and node.image==duplicate
    assert canonical.name=='Tree_12_01__Duplicate'
print('UNITY_EXPORT_GUARDS_TEST_PASSED')
