"""Standalone queue and resume support. No Blender or ZBrush imports required."""
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location('_mesh_to_ztl_engine', Path(__file__).with_name('zbrush_job.py'))
_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engine)
_trace_spec = importlib.util.spec_from_file_location('_mesh_to_ztl_diagnostics', Path(__file__).with_name('diagnostics.py'))
_diagnostics = importlib.util.module_from_spec(_trace_spec)
_trace_spec.loader.exec_module(_diagnostics)


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path outside export folder: ' + str(relative))
    return path


def load_export(folder):
    root = Path(folder).expanduser().resolve()
    if root.is_file() and root.name == 'job.json':
        root = root.parent
    if root.name.lower() == 'mesh':
        root = root.parent
    manifest_path = root / 'job.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        if manifest.get('version') != 1:
            raise ValueError('Unsupported job.json version')
    else:
        groups = {}
        for obj in sorted((root / 'Mesh').rglob('*.obj')):
            match = re.fullmatch(r'(.+)_L(\d+)', obj.stem, re.I)
            if not match:
                continue
            name, level = match.group(1), int(match.group(2))
            verts = faces = 0
            with obj.open(encoding='utf-8-sig', errors='replace') as handle:
                for line in handle:
                    fields = line.split(None, 1)
                    if fields:
                        verts += fields[0] == 'v'
                        faces += fields[0] == 'f'
            groups.setdefault(name, []).append(dict(level=level, verts=verts, faces=faces,
                                                     obj=obj.relative_to(root).as_posix()))
        manifest = dict(version=1, build='AUTO', assets=[
            dict(name=name, ztl=f'ZTL/{name}.ztl', levels=sorted(levels, key=lambda x: x['level']))
            for name, levels in groups.items()])
    if not manifest.get('assets'):
        raise ValueError('No exported assets found (expected Mesh/<name>/<name>_L0.obj etc.)')
    targets = set()
    names = set()
    for asset in manifest['assets']:
        target = contained(root, asset['ztl'])
        if target.suffix.lower() != '.ztl' or str(target).casefold() in targets or asset['name'] in names:
            raise ValueError('Invalid or duplicate ZTL target/name')
        targets.add(str(target).casefold())
        names.add(asset['name'])
        levels = asset['levels']
        if not levels or [x['level'] for x in levels] != list(range(len(levels))):
            raise ValueError('Missing or duplicate subdivision levels: ' + asset['name'])
        for level in levels:
            source = contained(root, level['obj'])
            if source.suffix.lower() != '.obj' or not source.is_file():
                raise ValueError('Missing OBJ: ' + str(source))
            if level['faces'] < 1 or level['verts'] < 1:
                raise ValueError('Empty mesh: ' + str(source))
    return root, manifest


def save_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class ConversionJob(_engine.Job):
    """Use separate state files; never signal Blender's automatic cleanup watcher."""
    def write_result(self, finished=False):
        save_json(Path(self.root) / 'standalone_last_run.json',
                  dict(finished=finished, assets=self.results))

    def log(self, text):
        print(text)
        with (Path(self.root) / 'standalone_log.txt').open('a', encoding='utf-8') as handle:
            handle.write(text + '\n')


class Queue:
    def __init__(self, folder, mode='AUTO'):
        if mode not in ('AUTO', 'RECONSTRUCT', 'PROJECT'):
            raise ValueError('Unknown build mode')
        self.root, self.manifest = load_export(folder)
        self.manifest = copy.deepcopy(self.manifest)
        self.manifest['build'] = mode
        self.state_path = self.root / 'standalone_state.json'
        self.state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {}

    def fingerprint(self, asset):
        sources = []
        for level in asset['levels']:
            stat = contained(self.root, level['obj']).stat()
            sources.append((level['obj'], stat.st_size, stat.st_mtime_ns))
        data = [asset, self.manifest['build'], sources]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def status(self, asset):
        target = contained(self.root, asset['ztl'])
        record = self.state.get(asset['name'], {})
        if target.is_file() and target.stat().st_size:
            stat = target.stat()
            if (record.get('ok') and record.get('fingerprint') == self.fingerprint(asset)
                    and record.get('target') == [stat.st_size, stat.st_mtime_ns]):
                return 'done'
            return 'existing'
        return 'pending'

    def run(self, zbc, overwrite=False, limit=None, progress=None, should_stop=None):
        with _diagnostics.Trace(self.root) as trace:
            trace.progress = progress
            trace.write(f'QUEUE mode={self.manifest["build"]} assets={len(self.manifest["assets"])} overwrite={overwrite}')
            return self._run(trace.proxy(zbc), overwrite, limit, progress, should_stop, trace)

    def _run(self, zbc, overwrite, limit, progress, should_stop, trace):
        job = ConversionJob(zbc, str(self.root), self.manifest)
        if progress:
            original_log = job.log
            def log(message):
                original_log(message)
                progress(message)
            job.log = log
        done = skipped = failed = 0
        stopped = False
        for number, asset in enumerate(self.manifest['assets'], 1):
            if should_stop and should_stop():
                stopped = True
                break
            status = self.status(asset)
            trace.write(f'ASSET {number}/{len(self.manifest["assets"])} {asset["name"]} status={status}')
            if status == 'done' or (status == 'existing' and not overwrite):
                skipped += 1
                continue
            fingerprint = self.fingerprint(asset)
            if progress:
                progress(f"[{number}/{len(self.manifest['assets'])}] {asset['name']} - converting")
            target = contained(self.root, asset['ztl'])
            # A stale preexisting file must never be mistaken for a successful save.
            backup = target.with_suffix('.ztl.standalone-backup')
            if backup.exists():
                raise ValueError('Recover/remove previous backup before retrying: ' + str(backup))
            if target.exists():
                target.replace(backup)
            committed = False
            try:
                job.process(asset)
                record = dict(job.results[-1], fingerprint=fingerprint)
                if record['ok']:
                    stat = target.stat()
                    record['target'] = [stat.st_size, stat.st_mtime_ns]
                    done += 1
                else:
                    failed += 1
                self.state[asset['name']] = record
                trace.write('RESULT ' + json.dumps(record, ensure_ascii=False))
                save_json(self.state_path, self.state)
                committed = record['ok']
            finally:
                if backup.exists():
                    if not committed:
                        target.unlink(missing_ok=True)
                        backup.replace(target)
                    else:
                        backup.unlink()
                elif not committed:
                    target.unlink(missing_ok=True)
            if limit and done + failed >= limit:
                break
        job.write_result(finished=limit is None and not stopped)
        return dict(converted=done, skipped=skipped, failed=failed)
