"""Run disposable interactive Blender regressions with marker verification."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
cases = [
    ('test_cutter_progress_ui.py', 'airetopo_cutter_progress_ui.log', 'CUTTER_PROGRESS_UI_TESTS_PASSED'),
    ('test_cutter_grid_ui.py', 'airetopo_cutter_grid_ui.log', 'CUTTER_GRID_UI_TESTS_PASSED'),
]
for test, log_name, marker in cases:
    started = time.time()
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    result = subprocess.run([
        sys.argv[1], '--factory-startup', '--enable-event-simulate',
        '--python-exit-code', '1', '--python', str(ROOT / 'tests' / test),
    ], cwd=ROOT, startupinfo=startup, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=60)
    log = Path(tempfile.gettempdir()) / log_name
    content = log.read_text(encoding='utf-8') if log.exists() else ''
    (ROOT / f'refactor_gui_{Path(test).stem}.log').write_text(result.stdout+'\n'+content, encoding='utf-8')
    assert result.returncode == 0 and log.stat().st_mtime >= started and marker in content, result.stdout[-2000:]+'\n'+content
    print(f'PASS {test} (interactive Blender, {time.time()-started:.1f}s)', flush=True)
