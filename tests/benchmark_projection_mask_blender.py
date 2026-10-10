"""Isolated native normal + mask benchmark. Run once per size with -- <size>."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
import json
import tempfile
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import baking
from polygroups_generator.core.bake_projection import invalidate, save_mask_png

size = int(sys.argv[sys.argv.index('--') + 1])
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2)
low = bpy.context.object
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -.2))
high = bpy.context.object
high.rotation_euler.x = 3.141592653589793
settings = bpy.context.scene.polygroups_baking_settings
settings.bake_resolution = size
settings.bake_normal = True
settings.bake_artifact_radius = 2
settings.cage_extrusion = .1
settings.ray_distance = 1
settings.use_selected_to_active = True
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
material, base, normal = baking._ensure_bake_material(low, settings)
low.active_material = material
baking._select_sources_and_target(bpy.context, [high], low)
invalidate(low)
started = time.perf_counter()
baking._bake_to_node(bpy.context, low, normal, 'NORMAL', settings)
normal_seconds = time.perf_counter() - started
started = time.perf_counter()
image, meta = baking._generate_bake_artifact_mask(bpy.context, low, [high], settings)
mask_seconds = time.perf_counter() - started
assert meta['reversed'] == size*size and meta['misses'] == 0
save_seconds = None
if '--save' in sys.argv:
    with tempfile.TemporaryDirectory() as directory:
        started = time.perf_counter()
        save_mask_png(image, str(Path(directory) / 'ArtifactMask.png'))
        save_seconds = time.perf_counter() - started

class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
        'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
        'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
counters = Counters()
counters.cb = ctypes.sizeof(counters)
ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
print('PROJECTION_BENCHMARK', json.dumps(dict(size=size, normal_seconds=normal_seconds, mask_seconds=mask_seconds,
    save_verify_seconds=save_seconds,
    peak_working_set_mib=counters.PeakWorkingSetSize/1048576, peak_commit_mib=counters.PeakPagefileUsage/1048576,
    note='Includes native normal/HIT/UV bakes, ownership and classifier; excludes background filling; PNG measured only with --save')), flush=True)
