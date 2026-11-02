"""MeshInfo destination and prepared asset identity for Unreal/Unity and staging."""
import sys,json,tempfile
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.mesh_export import _write_export_mesh_info
s=bpy.context.scene.polygroups_mesh_finalization_settings
s.unreal_lod_asset_name='Wrong Pack';s.unreal_lod_name_index='99'
s.unity_asset_name='Unity Test';s.unity_name_index='7';s.unity_asset_suffix='Set_12_34'
def record(name,asset=None):
    result=dict(name=name,triangles=12,vertices=8)
    if asset:result.update(asset=asset,role='LOD',lod_index=0)
    return result
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    for engine,entries,expected in (
        ('Unreal',[record('SM_Rock_Set_03_01_LOD0','Rock_Set_03_01'),record('SM_Rock_Set_03_02_LOD0','Rock_Set_03_02')],('Rock_Set','03')),
        ('Unity',[record('Unity_Test_07_01_Set_12_34.LOD1')],('Unity_Test','07')),
        ('Unity',[record('Previously_Prepared_02_01.LOD1')],('Previously_Prepared','02')),
        ('Unreal',[record('Unnumbered')],('Wrong_Pack','99')),
    ):
        folder=root/engine;folder.mkdir(exist_ok=True)
        _write_export_mesh_info(str(folder),'JSON',entries,engine)
        data=json.loads((folder/'MeshInfo.json').read_text(encoding='utf-8'))
        assert data['Path']==str(folder.resolve())
        assert (data['AssetName'],data['NameIndex'])==expected,data
        assert all((item['AssetName'],item['NameIndex'])==expected for item in data['meshes'])
        assert data['totals']['triangles']==12*len(entries)
        for asset in data.get('assets',[]):assert (asset['AssetName'],asset['NameIndex'])==expected
    # A mixed pack has per-mesh identities without falsely naming one common asset.
    entries=[record('SM_Stone_01_01_LOD0'),record('SM_Tree_02_01_LOD0')]
    _write_export_mesh_info(str(root),'JSON',entries,'Unreal')
    data=json.loads((root/'MeshInfo.json').read_text(encoding='utf-8'))
    assert data['AssetName']==data['NameIndex']==''
    assert [(row['AssetName'],row['NameIndex']) for row in data['meshes']]==[('Stone','01'),('Tree','02')]
    # ReLOD writes in a temporary folder before moving JSON to its destination.
    staged=root/'staged';staged.mkdir();final=root/'final'
    _write_export_mesh_info(str(staged),'JSON',[record('SM_Stone_01_01_MID')],'Unreal',output_directory=final)
    data=json.loads((staged/'MeshInfo.json').read_text(encoding='utf-8'))
    assert data['Path']==str(final.resolve()) and 'staged' not in data['Path']
print('MESHINFO_PATH_AND_ASSET_IDENTITY_METADATA_OK',flush=True)
