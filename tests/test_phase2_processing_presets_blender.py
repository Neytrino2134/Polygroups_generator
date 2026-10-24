"""Dynamic preset switching without starting jobs or resetting unrelated settings."""
import sys
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
ctx=bpy.context;p=ctx.scene.polygroups_model_preparation_settings
p.phase2_autosave=True;p.phase2_autosave_every=7;p.phase2_skip_retopo_backups=True
p.phase2_delete_high_after_bake=p.phase2_delete_lower_retopo=True
p.phase2_repack_only_if_changed=False
kept=('phase2_autosave','phase2_autosave_every','phase2_skip_retopo_backups',
      'phase2_delete_high_after_bake','phase2_delete_lower_retopo','phase2_repack_only_if_changed')
original={name:getattr(p,name) for name in kept}
def switch(name):
 assert bpy.ops.object.polygroups_phase2_processing_preset(preset=name)=={'FINISHED'}
 assert original=={name:getattr(p,name) for name in kept}
def verify_ui():
 from polygroups_generator.custom_ui.schema import capture,walk
 p.phase2_show_restore=True
 model=capture(ctx,1);assert not model.errors,model.errors
 buttons=[node for node in walk(model.node) if node.get('kind')=='button'
          and 'polygroups_phase2_processing_preset' in node.get('id','')]
 assert len(buttons)==3,buttons
 assert buttons[0].get('depress')==(not p.phase2_auto_bake and not p.phase2_mesh_auto_repair)
 assert buttons[1].get('depress')==p.phase2_auto_bake
 assert buttons[2].get('depress')==p.phase2_resculpt_retopo01
switch('IMPORT')
assert not any(getattr(p,name) for name in ('phase2_auto_bake','phase2_mesh_auto_repair',
 'phase2_repack_after_repair','phase2_repair_artifacts','phase2_resculpt_retopo01','phase2_autobake_retopo01'))
verify_ui()
switch('REBAKE')
assert all(getattr(p,name) for name in ('phase2_auto_bake','phase2_mesh_auto_repair','phase2_repack_after_repair','phase2_repair_artifacts'))
assert not p.phase2_resculpt_retopo01 and not p.phase2_autobake_retopo01
verify_ui()
p.phase2_keep_retopo01=False
switch('RESCULPT')
assert p.phase2_auto_bake and p.phase2_resculpt_retopo01 and p.phase2_autobake_retopo01 and p.phase2_keep_retopo01
verify_ui()
switch('REBAKE');assert p.phase2_resculpt_retopo01
switch('RESCULPT')
assert p.phase2_auto_bake and not p.phase2_resculpt_retopo01 and not p.phase2_autobake_retopo01
verify_ui()
switch('IMPORT');switch('RESCULPT')
assert p.phase2_auto_bake and p.phase2_resculpt_retopo01
verify_ui()
p.phase2_is_running=True
assert not bpy.ops.object.polygroups_phase2_processing_preset.poll()
p.phase2_is_running=False
assert bpy.ops.object.polygroups_phase2_processing_preset.poll()
print('PHASE2_PROCESSING_DYNAMIC_PRESETS_PASSED')
