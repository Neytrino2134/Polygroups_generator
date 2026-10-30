"""The manual ReBake button says Selected for one MID and Queue once meshes are added to the queue."""
from pathlib import Path
import sys
from types import SimpleNamespace
import addon_utils,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core.phase2_progress import draw_rebake
ctx=bpy.context
p=ctx.scene.polygroups_model_preparation_settings


class Layout:
    """Records operator button texts; every other layout call is a no-op."""
    def __init__(self,texts):self.texts=texts
    def operator(self,idname,**kwargs):
        if idname=='object.polygroups_rebake_final_mesh':self.texts.append(kwargs.get('text'))
        return SimpleNamespace()
    def __getattr__(self,name):
        return lambda *args,**kwargs:self


def label():
    texts=[];draw_rebake(Layout(texts),ctx,p);return texts[0]


bpy.ops.mesh.primitive_plane_add();mid=ctx.object;mid.name='SM_Label_01_01_MID'
assert label()=='ReBake Selected Final Mesh',label()
p.phase2_rebake_queue.add().target=mid
assert label()=='ReBake Queue Final Meshes',label()
p.phase2_rebake_queue.clear()
assert label()=='ReBake Selected Final Mesh'
print('REBAKE_BUTTON_LABEL_OK')
