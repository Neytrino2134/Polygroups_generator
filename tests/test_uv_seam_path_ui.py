"""Compatibility entry point for the native UV Tweak event regression.
Run Blender with --enable-event-simulate.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("test_uv_tweak_events.py")), run_name="__main__")
