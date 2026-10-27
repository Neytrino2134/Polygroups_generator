"""Real Blender inventory, provider contracts, async errors and JSON export."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon = addon_utils.enable(ROOT.name, default_set=False)
assert addon is not None
from polygroups_generator.services import fab_media as media, ai_text
from polygroups_generator.operators import fab_media as ops
from polygroups_generator.properties import SECTION_SUBSECTION_PROPERTIES

ctx = bpy.context
scene = ctx.scene
s = scene.airetopo_fab_media_settings
assert 'topic_ai_4' in SECTION_SUBSECTION_PROPERTIES['show_ai_generation_section']
assert 'gpt-6.1-terra' in {m[0] for m in media.MODELS}
assert {m[0] for m in media.MODELS} == {m[0] for m in ai_text.OPENAI_MODELS + ai_text.GOOGLE_MODELS} - {'CUSTOM'}
template_path = ROOT / 'tests/fixtures/texflow-fab-media-v2.json'
assert set(media.template()['fields']) == set(json.loads(template_path.read_text(encoding='utf-8'))['fields'])


def collection(name):
    value = bpy.data.collections.new(name)
    scene.collection.children.link(value)
    return value


def mesh(col, name, quads=1):
    data = bpy.data.meshes.new(name)
    verts = [(i * 2 + x, y, 0) for i in range(quads) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    data.from_pydata(verts, [], [tuple(range(i * 4, i * 4 + 4)) for i in range(quads)])
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    return obj


a = collection('Tomb_01_02_Collection')
unrelated = collection('Unrelated')
unrelated_layer = ctx.view_layer.layer_collection.children[unrelated.name]
unrelated_layer.exclude = True
low = mesh(a, 'SM_Tomb_01_02_LOD0', 2)
mesh(a, 'SM_Tomb_01_02_LOD1', 1)
mid = mesh(a, 'SM_Tomb_01_02_MID', 5)
mesh(a, 'SM_Tomb_01_02_HIGH', 10)
mesh(a, 'UCX_SM_Tomb_01_02', 3)
mesh(a, 'Helper', 1)
b = collection('Tomb_01_10_Collection')
mesh(b, 'SM_Tomb_01_10_MID', 3)
ctx.view_layer.update()
source = media.inventory(ctx)
assert len(source['assets']) == 2 and len(source['warnings']) == 1
measured = media.measured_fields(source)
assert measured['assetsQuantityLine2'] == '3 STATIC MESHES'
assert measured['polycountLOW01'] == '4' and measured['polycountMID01'] == '10'
assert measured['fileNameLOW02'] == '' and measured['polycountMID02'] == '6'
assert measured['averagePolycountMid'] == '~ 8'
# Evaluated modifiers, rather than only base mesh polygons, determine triangles.
modifier = mid.modifiers.new('Array', 'ARRAY')
modifier.count = 2
ctx.view_layer.update()
assert media.measured_fields(media.inventory(ctx))['polycountMID01'] == '20'
assert unrelated_layer.exclude
mid.hide_set(True)
ctx.view_layer.update()
assert media.measured_fields(media.inventory(ctx))['polycountMID01'] == '20'
layer = ctx.view_layer.layer_collection.children[a.name]
layer.exclude = True
ctx.view_layer.update()
visibility_before = (layer.exclude, mid.hide_get())
assert media.measured_fields(media.inventory(ctx))['polycountMID01'] == '20'
assert (layer.exclude, mid.hide_get()) == visibility_before, (visibility_before, layer.exclude, mid.hide_get())
layer.exclude = False
mid.hide_viewport = True
a.hide_viewport = True
assert media.measured_fields(media.inventory(ctx))['polycountMID01'] == '20'
assert mid.hide_viewport and a.hide_viewport
mid.hide_viewport = False
a.hide_viewport = False
mid.hide_set(False)
mid.modifiers.remove(modifier)
explicit = mesh(a, 'SM_Tomb_01_02_LOW', 3)
ctx.view_layer.update()
assert media.measured_fields(media.inventory(ctx))['polycountLOW01'] == '6'
assert media.measured_fields(media.inventory(ctx))['assetsQuantityLine2'] == '3 STATIC MESHES'
assert media.compact(2000) == '2K' and media.compact(3800) == '3.8K'

s.description = 'Stylized graveyard pack; UV unwrapped; Base Color and Normal, 2K textures'
s.seriesName = 'Halloween series'
assert bpy.ops.object.airetopo_fab_media(action='FILL') == {'FINISHED'}
assert s.assetHeadline == 'Tomb' and s.seriesName == 'Halloween series'
assert s.assetsQuantityLine1 == '2 UNIQUE ASSETS'
assert 'triangles' in s.prompt_text.as_string() and 'schemaVersion' in s.prompt_text.as_string()


class Response:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return json.dumps(self.data).encode()


requests = []


def http(request, timeout):
    body = json.loads(request.data)
    requests.append(body)
    if 'openai.com' in request.full_url:
        assert body['text']['format']['strict'] and body['reasoning']['effort'] == 'low'
        doc = json.loads(body['input'])['template']
    else:
        assert body['generationConfig']['responseJsonSchema'] == media.SCHEMA
        doc = json.loads(body['contents'][0]['parts'][0]['text'])['template']
    doc['fields']['mainHeadline1'] = 'Tomb'
    doc['fields']['mainHeadline2'] = 'Stones'
    doc['fields']['polycountLOW01'] = 'INVENTED BY MODEL'
    text = json.dumps(doc)
    if 'openai.com' in request.full_url:
        return Response({'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]})
    return Response({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}]})


def drain():
    deadline = time.monotonic() + 4
    while ops._jobs and time.monotonic() < deadline:
        ops._apply_results()
        time.sleep(.01)
    assert not ops._jobs and not s.is_generating


with patch.object(ops, '_get_api_key', return_value='test-key-not-real'), patch.object(ai_text.urllib.request, 'urlopen', http):
    for model in ('gpt-6.1-terra', 'gemini-3.5-flash-lite'):
        s.model = model
        assert bpy.ops.object.airetopo_fab_media(action='GENERATE') == {'FINISHED'}
        assert bpy.ops.object.airetopo_fab_media(action='GENERATE') == {'CANCELLED'}
        drain()
        result = media.validate(s.result_text.as_string())
        assert result['fields']['polycountLOW01'] == '6'
        assert result['fields']['mainHeadline2'] == 'Stones'
assert len(requests) == 2
old = s.result_text
with patch.object(ops, '_get_api_key', return_value='test-key-not-real'), patch.object(ops, 'generate_text', return_value=('{}', 'Completed')):
    assert bpy.ops.object.airetopo_fab_media(action='GENERATE') == {'FINISHED'}
    drain()
    assert s.result_text == old and 'schemaVersion' in s.last_status
with patch.object(ops, '_get_api_key', return_value=''):
    assert bpy.ops.object.airetopo_fab_media(action='GENERATE') == {'CANCELLED'}
    assert s.result_text == old
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'media.json'
    assert bpy.ops.object.airetopo_save_fab_media(filepath=str(path)) == {'FINISHED'}
    assert media.validate(path.read_text(encoding='utf-8')) == media.validate(old.as_string())
    old.write('broken')
    assert bpy.ops.object.airetopo_save_fab_media(filepath=str(path)) == {'CANCELLED'}
    assert media.validate(path.read_text(encoding='utf-8'))['schemaVersion'] == 2

# Ambiguous layouts and over-capacity templates must fail without silently dropping data.
duplicate = mesh(a, 'Other_LOW')
ctx.view_layer.update()
try:
    media.inventory(ctx)
except ValueError as error:
    assert 'multiple LOW' in str(error)
else:
    raise AssertionError('Ambiguous LOW meshes accepted')
bpy.data.objects.remove(duplicate, do_unlink=True)
for index in range(19):
    mesh(collection(f'Extra_{index}_Collection'), f'Extra_{index}_MID')
ctx.view_layer.update()
try:
    media.inventory(ctx)
except ValueError as error:
    assert '20 assets' in str(error)
else:
    raise AssertionError('Inventory over capacity accepted')
assert bpy.ops.object.airetopo_fab_media(action='CLEAR') == {'FINISHED'}
assert not s.seriesName and not s.description and s.result_text is None
addon.unregister()
assert not hasattr(bpy.types.Scene, 'airetopo_fab_media_settings')
addon.register()
print('FAB_MEDIA_INTEGRATION_PASSED')
