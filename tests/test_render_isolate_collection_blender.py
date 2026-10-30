"""Render isolates the rendered collection; the snapshot restores every collection afterwards."""
from pathlib import Path
import sys
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import render_queue as rq
ctx=bpy.context
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
for col in list(bpy.data.collections):bpy.data.collections.remove(col)


def collection(name,parent=None):
    col=bpy.data.collections.new(name);(parent or ctx.scene.collection).children.link(col);return col


assets=collection('Assets')
current=collection('Stone_01_01_Collection',assets);other=collection('Stone_01_02_Collection',assets)
lods=collection('Stone_01_01_LOD0_Collection',current)
generated=collection('Generated.001');misc=collection('Misc')
studio=collection('Scene_Studio');lights=collection('Rig')
lights.objects.link(bpy.data.objects.new('Key',bpy.data.lights.new('Key','AREA')))
excluded_before=collection('Hidden')
layers={layer.collection.name:layer for layer in rq._layer_collections_recursive(ctx.view_layer.layer_collection)}
layers['Hidden'].exclude=True
before={name:layer.exclude for name,layer in layers.items()}
snapshot=rq._snapshot_visibility()
rq.isolate_render_collection(ctx,current)
layers={layer.collection.name:layer for layer in rq._layer_collections_recursive(ctx.view_layer.layer_collection)}
for name in ('Assets','Stone_01_01_Collection','Stone_01_01_LOD0_Collection','Scene_Studio','Rig'):
    assert not layers[name].exclude,name
for name in ('Stone_01_02_Collection','Generated.001','Misc','Hidden'):
    assert layers[name].exclude,name
rq._restore_visibility(snapshot)
layers={layer.collection.name:layer for layer in rq._layer_collections_recursive(ctx.view_layer.layer_collection)}
assert {name:layer.exclude for name,layer in layers.items()}==before
print('RENDER_ISOLATE_COLLECTION_OK')
