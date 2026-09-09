"""Blender smoke test for update and autosave startup notice state."""

from pathlib import Path
import sys
from types import SimpleNamespace

import bpy


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
from polygroups_generator import preferences as addon_preferences


context = SimpleNamespace(
    preferences=SimpleNamespace(
        filepaths=SimpleNamespace(use_auto_save_temporary_files=True),
    ),
)
settings = SimpleNamespace(autosave_mode="CUSTOM")
assert addon_preferences.autosave_configuration_state(context, settings) == "BOTH"

context.preferences.filepaths.use_auto_save_temporary_files = False
assert addon_preferences.autosave_configuration_state(context, settings) == "OK"

settings.autosave_mode = "NATIVE"
assert addon_preferences.autosave_configuration_state(context, settings) == "NONE"

context.preferences.filepaths.use_auto_save_temporary_files = True
assert addon_preferences.autosave_configuration_state(context, settings) == "OK"

print("STARTUP_NOTICES_OK", flush=True)
