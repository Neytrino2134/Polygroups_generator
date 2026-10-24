"""Structured requests, asynchronous field updates and dialog lifetime in Blender."""
import json,sys,time,threading
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.services import ai_text as api,asset_translation as service
from polygroups_generator.operators import asset_translation as ops
from polygroups_generator.operators.ai_generation import _get_preferences
ctx=bpy.context;s=ctx.scene.polygroups_mesh_finalization_settings;p=_get_preferences(ctx)
assert p.default_text_task_model=='gpt-6-luna'
assert {'gpt-6-luna','gpt-6.1-sol','gemini-3.5-flash-lite','gemini-3.6-flash','gemini-3.8-flash'} <= {x[0] for x in service.TEXT_TASK_MODELS}
class Reply:
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self):return json.dumps(self.data).encode()
requests=[]
def http(request,timeout):
 body=json.loads(request.data);requests.append(body);r=Reply()
 text=json.dumps({'asset_name':'desert rocks'})
 if 'openai.com' in request.full_url:
  assert body['text']['format']['strict'] and body['store'] is False
  r.data={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}
 else:
  assert body['generationConfig']['responseMimeType']=='application/json'
  assert body['generationConfig']['responseJsonSchema']['required']==['asset_name']
  r.data={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}]}
 return r
with patch.object(api.urllib.request,'urlopen',http):
 for provider,model in (('OPENAI','gpt-6-luna'),('GOOGLE','gemini-3.5-flash-lite')):
  assert service.translate_asset_name(provider,'not-real',model,'Пустынные камни')=='Desert_Rocks'
for invalid in ('Desert_Rocks','{"asset_name":"Камни"}','{"asset_name":"Rock","extra":true}','{"asset_name":5}'):
 with patch.object(service,'generate_text',return_value=(invalid,'Completed')):
  try:service.translate_asset_name('OPENAI','not-real','gpt-6-luna','stones')
  except api.TextGenerationError:pass
  else:raise AssertionError(invalid)
def wait():
 end=time.monotonic()+3
 while ops._jobs and time.monotonic()<end:ops._apply_results();time.sleep(.01)
 assert not ops._jobs
seen=[]
def translate(provider,key,model,source):
 seen.append((provider,model,source));return 'Desert_Rocks'
with patch.object(ops,'_get_api_key',return_value='not-real'),patch.object(ops,'translate_asset_name',translate):
 for model in ('gpt-6-luna','gemini-3.5-flash-lite'):
  p.default_text_task_model=model
  for field in ops.FIELDS[:-1]:
   setattr(s,field,'Пустынные камни')
   assert bpy.ops.object.polygroups_translate_asset_name(field=field)=={'FINISHED'}
   wait();assert getattr(s,field)=='Desert_Rocks'
 # Use real RNA operator properties for Phase 2 popup target, never the settings proxy.
 from polygroups_generator.operators.batch_finalization import OBJECT_OT_polygroups_batch_finalization
 popup=ctx.window_manager.operator_properties_last('object.polygroups_batch_finalization');popup.asset='Пустынные камни'
 token=ops.bind_dialog(popup)
 assert bpy.ops.object.polygroups_translate_asset_name(field='asset',dialog=token)=={'FINISHED'}
 wait();assert popup.asset=='Desert_Rocks'
 ops.release_dialog(token);assert token not in ops._dialogs
 assert all(model.startswith('gemini')==(provider=='GOOGLE') for provider,model,source in seen)
 gate=threading.Event()
 def delayed(*args):gate.wait(2);return 'Desert_Rocks'
 with patch.object(ops,'translate_asset_name',delayed):
  s.fab_asset_name='original'
  assert bpy.ops.object.polygroups_translate_asset_name(field='fab_asset_name')=={'FINISHED'}
  assert bpy.ops.object.polygroups_translate_asset_name(field='fab_asset_name')=={'CANCELLED'}
  s.fab_asset_name='User_Edit';gate.set();wait();assert s.fab_asset_name=='User_Edit'
 with patch.object(ops,'translate_asset_name',side_effect=api.TextGenerationError('Quota reached')):
  assert bpy.ops.object.polygroups_translate_asset_name(field='fab_asset_name')=={'FINISHED'}
  wait();assert s.fab_asset_name=='User_Edit'
  assert 'Quota' in ops._status[(s.as_pointer(),'fab_asset_name')]
ops.stop_translation_jobs()
from polygroups_generator.custom_ui.schema import capture,walk
s.show_fab_rename_settings=True;s.show_unity_rename_settings=True;s.show_smart_lods_settings=True
model=capture(ctx,11);assert not model.errors,model.errors
buttons=[n for n in walk(model.node) if n.get('kind')=='button' and 'polygroups_translate_asset_name' in n.get('id','')]
assert buttons, 'Translation buttons missing in finalization UI'
assert 'WORLD' in bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon'].enum_items.keys()
print('ASSET_TRANSLATION_JSON_ASYNC_DIALOG_AND_UI_PASSED')

