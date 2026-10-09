"""GUI lifecycle: per-area sessions, file load, cleanup and same-module reload."""
from pathlib import Path
import sys
import os
import tempfile
import traceback
import bpy
import addon_utils
bpy.context.preferences.use_preferences_save = False

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('AIRETOPO_UI_VALIDATION_OUTPUT',ROOT/'docs/custom_ui'))
OUT.mkdir(parents=True,exist_ok=True)
LOG=OUT/'lifecycle_test.log'
LOG.write_text('Starting\n')
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.custom_ui import lifecycle
prefs=bpy.context.preferences.addons[ROOT.name].preferences
prefs.ui_mode='CUSTOM'
state={'step':0}
TEMP=tempfile.TemporaryDirectory(prefix='airetopo-ui-lifecycle-')


def tick():
    try:
        window=bpy.context.window_manager.windows[0]
        areas=[a for a in window.screen.areas if a.type=='VIEW_3D']
        area=areas[0]
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            step=state['step']
            if step==0:
                assert len(lifecycle.SESSIONS)==1
                lifecycle.register()  # idempotent
                assert len(lifecycle.SESSIONS)==1
                bpy.ops.screen.area_split(direction='VERTICAL',factor=.5)
                state['step']=1
                return .5
            if step==1:
                areas=[a for a in window.screen.areas if a.type=='VIEW_3D']
                assert len(areas)==2
                other=areas[1]
                other_region=next(r for r in other.regions if r.type=='WINDOW')
                with bpy.context.temp_override(area=other,region=other_region):
                    if lifecycle.key_for(bpy.context) not in lifecycle.SESSIONS:
                        bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
                assert len(lifecycle.SESSIONS)==2
                sessions=list(lifecycle.SESSIONS.values())
                sessions[0].select(0)
                sessions[1].select(9)
                assert sessions[0].section!=sessions[1].section
                LOG.write_text(LOG.read_text()+'Independent viewport sessions passed\n')
                bpy.ops.wm.save_as_mainfile(filepath=str(Path(TEMP.name)/'lifecycle.blend'))
                state['step']=2
                return .4
            if step==2:
                bpy.ops.wm.open_mainfile(filepath=str(Path(TEMP.name)/'lifecycle.blend'),load_ui=False)
                assert not lifecycle.SESSIONS
                state['step']=3
                return 1
            if step==3:
                assert lifecycle.SESSIONS
                for session in lifecycle.SESSIONS.values():
                    assert session.scene==bpy.context.scene.as_pointer()
                    assert not session.model.errors
                LOG.write_text(LOG.read_text()+'File load cleanup and restart passed\n')
                addon_utils.disable(ROOT.name)
                assert not lifecycle.SESSIONS
                assert lifecycle._handle is None
                assert not bpy.app.timers.is_registered(lifecycle._tick)
                addon_utils.enable(ROOT.name,default_set=True)
                state['step']=4
                return 1
            LOG.write_text(LOG.read_text()+'Disable/re-enable passed\nCUSTOM_UI_LIFECYCLE_TESTS_PASSED\n')
            addon_utils.disable(ROOT.name)
            TEMP.cleanup()
            bpy.ops.wm.quit_blender()
    except Exception:
        LOG.write_text(LOG.read_text()+traceback.format_exc())
        addon_utils.disable(ROOT.name)
        TEMP.cleanup()
        bpy.ops.wm.quit_blender()
    return None

bpy.app.timers.register(tick,first_interval=1,persistent=True)
