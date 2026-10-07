"""Verify cursor text stays short and GPU progress geometry stays in the corner."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import bpy
import addon_utils

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import turnaround_animation as ta, render_queue as rq
area=object()
context=SimpleNamespace(area=area,region=SimpleNamespace(width=1200,height=900))
task=SimpleNamespace(_area=area,_mouse_x=600,_mouse_y=500,_frames_done=2,_total_frames=10,
    _settings=SimpleNamespace(animation_progress=20,animation_status='Detailed rendering status'))
for caption in ('Render','Export'):
    task._cursor_status=caption
    blf=Mock()
    blf.dimensions.return_value=(48,12)
    batch=Mock(return_value=Mock())
    with patch.object(ta,'bpy',SimpleNamespace(context=context)), patch.object(ta,'blf',blf), \
         patch.object(ta,'gpu',Mock()), patch.object(ta,'batch_for_shader',batch), \
         patch.object(ta,'_ACTIVE_RENDER_TASK',task):
        ta._draw_animation_cursor()
    assert [call.args[1] for call in blf.draw.call_args_list]==[
        caption,caption,'Completed 2/10  20%','Detailed rendering status']
    assert batch.call_count==3
    for call in batch.call_args_list:
        assert all(x<=376 and y<=78 for x,y in call.args[2]['pos'])
cursor=rq.RenderQueueCursor(bpy.context)
assert cursor.status_line=='Render'
cursor.close()
print('RENDER_CURSOR_OVERLAY_TEST_PASSED')
