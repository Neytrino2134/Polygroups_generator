"""Run the refactor regression selection in isolated Blender processes."""
import argparse
import os
from pathlib import Path
import subprocess
import time
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    'test_refactor_settings_lifecycle_blender.py',
    'test_panel_defaults.py',
    'test_panel_visibility_stages.py',
    'test_remesh_defaults.py',
    'test_render_resolution_presets.py',
    'test_cutter_draw_stabilize.py',
    'test_object_seam_cutter.py',
    'test_cutter_autofix.py',
    'test_cutter_backup.py',
    'test_mirror_cutter_transforms.py',
    'test_local_ring_fit.py',
    'test_local_contour_cutter_apply.py',
    'test_import_queue.py',
]
UI_BAKE_TESTS = [
    'test_panel_defaults.py', 'test_panel_search.py', 'test_narrow_panel.py',
    'test_experimental_windows.py', 'test_custom_ui_blender.py',
    'test_refactor_settings_lifecycle_blender.py', 'test_panel_search_scope_blender.py',
    'test_session_group_visibility_blender.py', 'test_edge_menu.py',
    'test_outliner_header.py', 'test_view_assists_toggle.py', 'test_panel_visibility_stages.py',
    'test_bake_auto_source.py', 'test_bake_alpha_merge.py', 'test_bake_artifact_mask.py',
    'test_bake_mask_export_blender.py', 'test_bake_artifact_fill_blender.py',
    'test_smart_cage_blender.py',
]

parser = argparse.ArgumentParser()
parser.add_argument('blender', type=Path)
parser.add_argument('--tests', nargs='+')
parser.add_argument('--suite', choices=['initial', 'ui-bake'], default='initial')
args = parser.parse_args()
if args.tests is None:
    args.tests = UI_BAKE_TESTS if args.suite == 'ui-bake' else TESTS
failed = []
for name in args.tests:
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='polygroups_validation_') as directory:
            env = dict(os.environ, AIRETOPO_UI_VALIDATION_OUTPUT=directory)
            result = subprocess.run(
                [str(args.blender), '--background', '--factory-startup',
                 '--python-exit-code', '1', '--python', str(ROOT / 'tests' / name)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', timeout=180, env=env,
            )
        output = result.stdout
        success = result.returncode == 0 and 'Traceback (most recent call last)' not in output
    except subprocess.TimeoutExpired as exc:
        output = str(exc)
        success = False
    (ROOT / f'refactor_{Path(name).stem}.log').write_text(output, encoding='utf-8')
    print(f'{"PASS" if success else "FAIL"} {name} ({time.monotonic()-started:.1f}s)', flush=True)
    if not success:
        failed.append(name)
        print(output[-6000:], flush=True)
print(f'Result: {len(args.tests)-len(failed)}/{len(args.tests)} passed', flush=True)
raise SystemExit(bool(failed))
