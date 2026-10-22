"""Compare all workflow captures against the pre-UI-refactor checkout."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '6c502bf'
archive = subprocess.check_output(['git', 'archive', BASE], cwd=ROOT)
with tempfile.TemporaryDirectory(prefix='polygroups_capture_') as directory:
    temporary = Path(directory)
    baseline = temporary / ROOT.name
    baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(baseline, filter='data')
    captures = []
    for name, checkout in [('baseline', baseline), ('current', ROOT)]:
        output = temporary / name
        output.mkdir()
        result = subprocess.run([
            sys.argv[1], '--background', '--factory-startup', '--python-exit-code', '1',
            '--python', str(checkout / 'tests/test_custom_ui_blender.py'),
        ], cwd=checkout, env=dict(os.environ, AIRETOPO_UI_VALIDATION_OUTPUT=str(output)),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding='utf-8', errors='replace', timeout=180)
        (ROOT / f'refactor_ui_capture_{name}.log').write_text(result.stdout, encoding='utf-8')
        assert result.returncode == 0, result.stdout[-6000:]
        captures.append(json.loads((output / 'control_inventory.json').read_text(encoding='utf-8')))
    old, new = captures
    def differences(first, second, path='runtime'):
        if type(first) is not type(second):
            yield path, first, second
        elif isinstance(first, dict):
            for key in first.keys() | second.keys():
                yield from differences(first.get(key), second.get(key), f'{path}.{key}')
        elif isinstance(first, list):
            if len(first) != len(second):
                yield path+'.length', len(first), len(second)
            for index, (a, b) in enumerate(zip(first, second)):
                yield from differences(a, b, f'{path}[{index}]')
        elif first != second:
            yield path, first, second
    changes = list(differences(old['runtime'], new['runtime']))
    assert not changes, repr(changes[:12])
    # File locations and normalized state expressions are expected to differ.
    old_calls = sorted((item['scope'], item['kind'], item['call']) for item in old['static_calls'])
    new_calls = sorted((item['scope'], item['kind'], item['call']) for item in new['static_calls'])
    assert old_calls == new_calls, 'Static UI calls changed or were lost'
    report = dict(baseline=BASE, identical_runtime_captures=len(new['runtime']),
                  identical_static_calls=len(new_calls),
                  modes=sorted({item['mode'] for item in new['runtime']}))
    (ROOT / 'docs/refactor_ui_equivalence.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))
