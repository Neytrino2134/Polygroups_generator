"""Pure helpers for the Blender -> ZBrush multires export (no bpy, importable from tests and subprocesses)."""
import glob
import json
import os
import re
import subprocess
from pathlib import Path

ZBRUSH_FOLDER = '!ZBrush'
BLEND_FOLDER = '!Blend'
MANIFEST_NAME = 'job.json'
JOB_SCRIPT_NAME = 'zbrush_job.py'
RESULT_NAME = 'job_result.json'
LOG_NAME = 'job_log.txt'
GENERATED_BLEND = re.compile(r'^Generated\.\d+\.blend$', re.IGNORECASE)
MANIFEST_VERSION = 1
BUILD_MODES = ('AUTO', 'RECONSTRUCT', 'PROJECT')


def safe_name(text, fallback='Asset'):
    """File-system safe ASCII-friendly stem; ZBrush tool and file names dislike odd characters."""
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f\s]+', '_', str(text)).strip(' ._')
    return stem or fallback


def output_root(blend_filepath, custom_directory=''):
    """Folder that receives Mesh/, ZTL/, job.json and the ZBrush job script."""
    if custom_directory:
        return Path(custom_directory)
    base = Path(blend_filepath).parent
    # Working files live inside !Blend, the pack root is its parent.
    if base.name.casefold() == BLEND_FOLDER.casefold():
        base = base.parent
    return base / ZBRUSH_FOLDER


def unique_stems(names):
    """Make stems unique case-insensitively (Windows file system) by numbering repeats."""
    seen, result = {}, []
    for name in names:
        key = name.casefold()
        seen[key] = seen.get(key, 0) + 1
        result.append(name if seen[key] == 1 else f'{name}_{seen[key]:02d}')
    return result


def find_zbrush_exe(custom_path=''):
    """Newest installed ZBrush.exe, or the custom path when it exists."""
    if custom_path and os.path.isfile(custom_path):
        return custom_path
    roots = [os.environ.get('ProgramFiles', r'C:\Program Files')]
    roots += [os.environ.get('ProgramW6432', '')]
    found = []
    for root in filter(None, roots):
        for pattern in ('Maxon ZBrush*', 'Pixologic', 'Pixologic\\ZBrush*', 'ZBrush*'):
            found += glob.glob(os.path.join(root, pattern, 'ZBrush.exe'))
    return sorted(set(found), key=lambda path: path.casefold())[-1] if found else ''


def zbrush_running():
    """True when a ZBrush process exists; a second instance exits at once without running the script."""
    if os.name != 'nt':
        return False
    try:
        output = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ZBrush.exe', '/NH'], capture_output=True,
                                text=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return 'zbrush.exe' in output.casefold()


def level_file(stem, level):
    return f'Mesh/{stem}/{stem}_L{level}.obj'


def asset_record(stem, object_name, levels, groups, bounds=None):
    """Manifest entry; ``levels`` is a list of {level, faces, verts} sorted by level."""
    return {
        'name': stem,
        'object': object_name,
        'ztl': f'ZTL/{stem}.ztl',
        'levels': [{**item, 'obj': level_file(stem, item['level'])} for item in levels],
        'polygroups': groups,
        'bounds': bounds or {},
    }


def write_manifest(root, assets, build='AUTO', source_blend=''):
    manifest = {
        'version': MANIFEST_VERSION,
        'build': build if build in BUILD_MODES else 'AUTO',
        'source_blend': str(source_blend),
        'assets': assets,
    }
    path = Path(root) / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
    return path


def launch_command(exe, job_script, manifest):
    return [exe, '-script', str(job_script), str(manifest)]
