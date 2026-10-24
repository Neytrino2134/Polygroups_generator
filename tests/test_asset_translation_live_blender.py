"""Explicit live smoke using existing addon keys; never prints credentials."""
import sys
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.ops.wm.read_userpref();bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.ai_generation import _get_api_key
from polygroups_generator.services.asset_translation import translate_asset_name
for provider,model in (('OPENAI','gpt-6-luna'),('GOOGLE','gemini-3.5-flash-lite')):
 key=_get_api_key(bpy.context,provider)
 if not key:
  print('LIVE_TRANSLATION_KEY_MISSING',provider,flush=True);continue
 try:
  value=translate_asset_name(provider,key,model,'Пустынные камни')
  print('LIVE_TRANSLATION_PASSED',provider,model,value,flush=True)
 except Exception as error:
  print('LIVE_TRANSLATION_FAILED',provider,str(error).replace(key,'[redacted]'),flush=True)
