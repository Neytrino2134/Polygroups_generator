"""Read-only preflight of final texture bindings in the supplied crystal asset."""
from pathlib import Path
from types import SimpleNamespace
import sys,bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from polygroups_generator.operators.rebake_final import final_texture_outputs,resolve_final_source
obj=bpy.data.objects['SM_Crystals_Pack_02_02_MID']
outputs,resolution=final_texture_outputs(obj,SimpleNamespace(bake_base_color=True,bake_normal=True))
assert resolution==2048
for channel in ('BaseColor','Normal'):
    image,path=outputs[channel]
    assert path.name==f'T_Crystals_Pack_02_02_{channel}.png'
    assert 'Textures' in path.parts
    print('FINAL_TEXTURE',channel,str(path),'PACKED',bool(image.packed_file))
try:source=resolve_final_source(bpy.context,obj)
except ValueError as error:
    assert 'not found in this scene' in str(error)
    print('EXPORTED_ASSET_HAS_NO_HIGH_SOURCE',str(error))
else:print('FINAL_SOURCE',source.name)
print('FINAL_REBAKE_ASSET_PREFLIGHT_OK')
