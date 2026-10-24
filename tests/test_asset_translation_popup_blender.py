"""Foreground validation of the actual Phase 2 dialog and translation target."""
import sys,runpy,traceback,tempfile
_folder=None
from pathlib import Path
from unittest.mock import patch
import bpy
ROOT=Path(__file__).resolve().parents[1]
def finish():
 if _folder is not None:_folder.cleanup()
 bpy.ops.wm.quit_blender()
def start():
 global _folder
 try:
  runpy.run_path(str(ROOT/'tests/test_asset_translation_blender.py'),run_name='__main__')
  from polygroups_generator.operators import asset_translation as ops
  ctx=bpy.context
  _folder=tempfile.TemporaryDirectory(dir=ROOT,prefix='test_translation_popup_')
  bpy.ops.wm.save_as_mainfile(filepath=str(Path(_folder.name)/'Popup.blend'))
  ctx.scene.polygroups_mesh_finalization_settings.unreal_lod_asset_name='Пустынные камни'
  with patch.object(ops,'_get_api_key',return_value='not-real'),patch.object(ops,'translate_asset_name',return_value='Desert_Rocks'):
   area=next(a for a in ctx.window.screen.areas if a.type=='VIEW_3D')
   with ctx.temp_override(area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
    assert bpy.ops.object.polygroups_batch_finalization('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
    token=next(iter(ops._dialogs));popup=ops._dialogs[token]
    assert popup.asset=='Пустынные камни'
    assert bpy.ops.object.polygroups_translate_asset_name(field='asset',dialog=token)=={'FINISHED'}
    import time
    end=time.monotonic()+2
    while ops._jobs and time.monotonic()<end:ops._apply_results();time.sleep(.01)
    assert popup.asset=='Desert_Rocks'
  print('ASSET_TRANSLATION_NATIVE_POPUP_PASSED',flush=True)
 except Exception:
  print('ASSET_TRANSLATION_NATIVE_POPUP_FAILED',traceback.format_exc(),flush=True)
 bpy.app.timers.register(finish,first_interval=1)
bpy.app.timers.register(start,first_interval=.5)
