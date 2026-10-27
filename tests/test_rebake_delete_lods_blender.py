"""Pre-bake removal matches the exact MID family and preserves other assets."""
import sys
from pathlib import Path
import addon_utils
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.rebake_lods import current_asset_lods,delete_current_asset_lods

context=bpy.context
collection=bpy.data.collections.new('Elsewhere');context.scene.collection.children.link(collection)


def obj(name):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
    result=bpy.data.objects.new(name,mesh);collection.objects.link(result);return result


target=obj('SM_Asset_00_12_MID')
lods=[obj('SM_Asset_00_12_LOD0'),obj('SM_Asset_00_12_LOD9')]
unrelated=[obj(name) for name in ('SM_Asset_00_13_LOD0','SM_Asset_00_120_LOD0',
    'SM_Asset_00_12_MID_LOD0','SM_Asset_00_12_LOD0.001','Resculpting_01_Highpoly_Generated.012')]
curve=bpy.data.curves.new('LOD label','FONT');label=bpy.data.objects.new('Label for LOD9',curve)
collection.objects.link(label);label.parent=lods[1]
collection.hide_viewport=True;collection.hide_render=True
context.view_layer.update()
assert current_asset_lods(context,target)==set(lods)

# No partial deletion when any matched object belongs to another scene.
other=bpy.data.scenes.new('Other Scene');other.collection.objects.link(lods[0])
try:delete_current_asset_lods(context,target)
except ValueError as error:assert 'shared by another scene' in str(error)
else:raise AssertionError('Shared object must be preserved')
assert all(item.name in bpy.data.objects for item in lods)
other.collection.objects.unlink(lods[0]);bpy.data.scenes.remove(other)
child=obj('Unrelated child');child.parent=lods[0]
try:delete_current_asset_lods(context,target)
except ValueError as error:assert 'unrelated child' in str(error)
else:raise AssertionError('Unrelated child must be preserved')
child.parent=None
names=[item.name for item in lods]+[label.name]
keep={item.name:item for item in [target,*unrelated,child]}
assert delete_current_asset_lods(context,target)==2
assert all(name not in bpy.data.objects for name in names)
assert all(bpy.data.objects[name]==item for name,item in keep.items())
assert collection.hide_viewport and collection.hide_render
assert delete_current_asset_lods(context,target)==0
assert not any(col.name.startswith('__ReBake_LOD_Backup_') for col in bpy.data.collections)
print('REBAKE_DELETE_EXACT_LOD_FAMILY_AND_OWNERSHIP_OK',flush=True)
