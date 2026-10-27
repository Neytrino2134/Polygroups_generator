"""Scene-persistent FAB gallery generation inputs."""
import bpy
from ..services.fab_media import FIELD_DEFAULTS, MODELS


class AIRETOPO_PG_fab_media_settings(bpy.types.PropertyGroup):
    __annotations__ = {
        **{key: bpy.props.StringProperty(name=key, default=value) for key, value in FIELD_DEFAULTS.items()},
        'model': bpy.props.EnumProperty(name='Model', items=MODELS, default='gpt-6.1-terra'),
        'notes': bpy.props.StringProperty(name='Pack facts / hints', description='Confirmed textures, UVs, collision, materials, style and uses; no unsupported claims'),
        'notes_text': bpy.props.PointerProperty(name='Multiline pack facts', type=bpy.types.Text),
        'result_text': bpy.props.PointerProperty(name='JSON result', type=bpy.types.Text),
        'prompt_text': bpy.props.PointerProperty(name='Prepared prompt', type=bpy.types.Text),
        'is_generating': bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'}),
        'last_status': bpy.props.StringProperty(name='Status'),
        'saved_filepath': bpy.props.StringProperty(name='Saved JSON', subtype='FILE_PATH'),
        'inventory_summary': bpy.props.StringProperty(name='Inventory'),
        'max_tokens': bpy.props.IntProperty(name='Max Output Tokens', default=8192, min=1024, max=128000),
    }
