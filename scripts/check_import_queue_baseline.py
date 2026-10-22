"""Reproduce the import queue test against the unmodified Git baseline."""
from pathlib import Path
import io
import subprocess
import sys
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
archive = subprocess.check_output(['git', 'archive', '140a104'], cwd=root)
with tempfile.TemporaryDirectory(prefix='polygroups_baseline_') as folder:
    checkout = Path(folder) / root.name
    checkout.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(checkout, filter='data')
    result = subprocess.run([
        sys.argv[1], '--background', '--factory-startup', '--python-exit-code', '1',
        '--python', str(checkout / 'tests/test_import_queue.py'),
    ], cwd=checkout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace', timeout=180)
    (root / 'refactor_import_queue_baseline.log').write_text(result.stdout, encoding='utf-8')
    print(result.stdout[-4000:])
    assert result.returncode != 0 and 'assert settings.batch_stage_4_remesh_preset == "LOW"' in result.stdout
    assert str(checkout / 'tests/test_import_queue.py') in result.stdout
    print('BASELINE_FAILURE_CONFIRMED: unchanged import queue test fails at the same assertion')
