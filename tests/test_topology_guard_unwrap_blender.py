"""Topology Guard ends with an Angle Based re-unwrap of its whole scope, even when it fixed nothing."""
from pathlib import Path
import sys
import addon_utils,bmesh,bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
ctx=bpy.context
settings=ctx.scene.polygroups_seam_finalization_settings
settings.topology_guard_selected_only=False;settings.topology_guard_pack=False
bpy.ops.mesh.primitive_grid_add(x_subdivisions=6,y_subdivisions=6)  # one disk chart: nothing to fix
obj=ctx.object
bpy.ops.object.mode_set(mode='EDIT')
bm=bmesh.from_edit_mesh(obj.data);uv=bm.loops.layers.uv.verify()
for face in bm.faces:
    for loop in face.loops:loop[uv].uv=(.5,.5)  # collapsed UVs, as if broken
bmesh.update_edit_mesh(obj.data)
for unwrap,expect_changed in ((False,False),(True,True)):
    settings.topology_guard_unwrap=unwrap
    bm=bmesh.from_edit_mesh(obj.data);uv=bm.loops.layers.uv.active
    for face in bm.faces:
        for loop in face.loops:loop[uv].uv=(.5,.5)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.mesh.polygroups_topology_guard(action='APPLY')=={'FINISHED'}
    bm=bmesh.from_edit_mesh(obj.data);uv=bm.loops.layers.uv.active
    spread=max((loop[uv].uv-loop.link_loop_next[uv].uv).length for face in bm.faces for loop in face.loops)
    assert (spread>1e-4)==expect_changed,(unwrap,spread)
print('TOPOLOGY_GUARD_FINAL_UNWRAP_OK')
