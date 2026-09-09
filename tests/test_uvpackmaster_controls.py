"""Verify the UVPackmaster wrapper waits for packing and returns to Object Mode."""

from pathlib import Path
import sys
from types import SimpleNamespace

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators import uvpackmaster_controls


obj = SimpleNamespace(type="MESH", mode="OBJECT")
main_props = SimpleNamespace(heuristic_max_wait_time=0)
context = SimpleNamespace(
    active_object=obj,
    view_layer=SimpleNamespace(objects=SimpleNamespace(active=None)),
    scene=SimpleNamespace(
        uvpm4_props=SimpleNamespace(default_main_props=main_props),
    ),
)
pack_calls = []
reports = []


def mode_set(*, mode):
    obj.mode = mode
    return {"FINISHED"}


fake_bpy = SimpleNamespace(
    ops=SimpleNamespace(
        object=SimpleNamespace(mode_set=mode_set),
        mesh=SimpleNamespace(
            select_mode=lambda **_kwargs: {"FINISHED"},
            reveal=lambda: {"FINISHED"},
            select_all=lambda **_kwargs: {"FINISHED"},
        ),
        uvpackmaster4=SimpleNamespace(
            pack=lambda *args, **kwargs: pack_calls.append((args, kwargs)) or {"FINISHED"},
        ),
    ),
)
real_bpy = uvpackmaster_controls.bpy
uvpackmaster_controls.bpy = fake_bpy
try:
    operator = SimpleNamespace(report=lambda level, message: reports.append((level, message)))
    result = uvpackmaster_controls.OBJECT_OT_polygroups_uvpackmaster_pack.execute(operator, context)
finally:
    uvpackmaster_controls.bpy = real_bpy

assert result == {"FINISHED"}
assert obj.mode == "OBJECT"
assert main_props.heuristic_max_wait_time == 3
assert pack_calls[0][0] == ("EXEC_DEFAULT",)
assert not reports

addon_utils.disable(ROOT.name, default_set=True)
print("UVPACKMASTER_CONTROLS_OK", flush=True)
