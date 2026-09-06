"""Blender background regression for placeholder Weld errors."""
import sys
from pathlib import Path
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.apply_weld import _has_meaningful_error

assert not _has_meaningful_error(RuntimeError("No error"))
assert not _has_meaningful_error(RuntimeError(" no ERROR "))
assert not _has_meaningful_error(RuntimeError(""))
assert _has_meaningful_error(RuntimeError("Real failure"))
print("WELD_NO_ERROR_REPORT_TEST_PASSED", flush=True)
addon_utils.disable(ROOT.name, default_set=True)
