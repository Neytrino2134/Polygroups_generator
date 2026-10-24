"""Blender text generation integration with mocked provider HTTP responses."""
import io, json, sys, time, threading, tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import bpy, addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon=addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.services import ai_text as api
from polygroups_generator.operators import ai_text as ops
from polygroups_generator.properties import SECTION_SUBSECTION_PROPERTIES
ctx=bpy.context;scene=ctx.scene
key='test-key-not-real'
class Response:
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self):return json.dumps(self.data).encode('utf-8')
requests=[]
def reply(request,timeout):
 body=json.loads(request.data);requests.append((request,body))
 if 'openai.com' in request.full_url:
  assert body['store'] is False and body['instructions']=='Translate into Russian'
  return Response({'status':'completed','output':[{'type':'reasoning'}, {'type':'message','content':[
    {'type':'output_text','text':'Первая строка'}, {'type':'output_text','text':'Second line'}]}]})
 assert 'key=' not in request.full_url and body['systemInstruction']['parts'][0]['text']=='Translate into Russian'
 return Response({'candidates':[{'finishReason':'STOP','content':{'parts':[
  {'thought':True,'text':'private thought'}, {'text':'Первая строка'}, {'text':'Second line'}]}}]})
with patch.object(api.urllib.request,'urlopen',reply):
 for provider,model in (('OPENAI','gpt-6-luna'),('GOOGLE','gemini-3.5-flash-lite')):
  text,status=api.generate_text(provider,key,model,'Hello','Translate into Russian')
  assert text=='Первая строка\nSecond line' and status=='Completed'
assert len(requests)==2
def error_reply(request,timeout):
 raise HTTPError(request.full_url,429,'limit',{},io.BytesIO(json.dumps({'error':{'message':'Quota '+key}}).encode()))
with patch.object(api.urllib.request,'urlopen',error_reply):
 try:api.generate_text('OPENAI',key,'gpt-6-luna','Hello')
 except api.TextGenerationError as error:assert '429' in str(error) and key not in str(error)
 else:raise AssertionError('Expected quota error')
with patch.object(api.urllib.request,'urlopen',return_value=Response({'candidates':[], 'promptFeedback':{'blockReason':'SAFETY'}})):
 try:api.generate_text('GOOGLE',key,'gemini-3.5-flash-lite','Hello')
 except api.TextGenerationError as error:assert 'SAFETY' in str(error)
 else:raise AssertionError('Expected blocked response')

assert 'topic_ai_3' in SECTION_SUBSECTION_PROPERTIES['show_ai_generation_section']
assert scene.airetopo_openai_text_settings.model=='gpt-6-luna'
assert scene.airetopo_google_text_settings.model=='gemini-3.5-flash-lite'
gate=threading.Event();calls=[]
def fake_generate(provider,key,model,prompt,instructions,limit):
 assert gate.wait(2)
 calls.append((provider,model,prompt,instructions))
 return 'Hello\nПривет', 'Completed'
def wait_jobs():
 deadline=time.monotonic()+3
 while ops._jobs and time.monotonic()<deadline:
  ops._apply_results();time.sleep(.01)
 assert not ops._jobs
with patch.object(ops,'_get_api_key',return_value=key),patch.object(ops,'generate_text',fake_generate):
 for provider in ('OPENAI','GOOGLE'):
  s=ops.settings_for(scene,provider);s.prompt='Translate me';s.task='TRANSLATE';s.language='Russian'
  assert bpy.ops.object.airetopo_generate_text(provider=provider)=={'FINISHED'}
  assert s.is_generating
  assert bpy.ops.object.airetopo_generate_text(provider=provider)=={'CANCELLED'}
 gate.set();wait_jobs()
assert len(calls)==2 and all('Russian' in call[3] for call in calls)
for provider in ('OPENAI','GOOGLE'):
 s=ops.settings_for(scene,provider)
 assert not s.is_generating and s.result_text.as_string()=='Hello\nПривет'
 assert bpy.ops.object.airetopo_text_document(provider=provider,action='COPY')=={'FINISHED'}
 if not bpy.app.background:
  assert ctx.window_manager.clipboard.replace('\r\n','\n')=='Hello\nПривет'
  assert bpy.ops.object.airetopo_text_document(provider=provider,action='PASTE')=={'FINISHED'}
  assert s.input_text.as_string().replace('\r\n','\n')=='Hello\nПривет'
 s.model='CUSTOM';s.custom_model='custom-text-model'
old=scene.airetopo_openai_text_settings.result_text
with patch.object(ops,'_get_api_key',return_value=key),patch.object(ops,'generate_text',side_effect=api.TextGenerationError('Quota reached')):
 assert bpy.ops.object.airetopo_generate_text(provider='OPENAI')=={'FINISHED'}
 wait_jobs()
 assert 'Quota reached' in scene.airetopo_openai_text_settings.last_status
 assert scene.airetopo_openai_text_settings.result_text==old
ops.stop_text_jobs()
from polygroups_generator.custom_ui.schema import capture
scene.airetopo_panel_visibility_settings.topic_ai_3=True
model=capture(ctx,1);assert not model.errors,model.errors
if bpy.app.background:
 with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_text_') as directory:
  path=str(Path(directory)/'Text.blend');bpy.ops.wm.save_as_mainfile(filepath=path)
  bpy.ops.wm.open_mainfile(filepath=path)
  assert bpy.context.scene.airetopo_openai_text_settings.result_text.as_string()=='Hello\nПривет'
  assert bpy.context.scene.airetopo_google_text_settings.model=='CUSTOM'
 addon.unregister();addon.register()
print('AI_TEXT_API_PARSING_ASYNC_UI_PERSISTENCE_PASSED')
