"""Runs inside ZBrush 2027+: build one ZTL with subdivision levels for every asset of job.json.

Started by the Blender addon as ``ZBrush.exe -script zbrush_job.py job.json`` (ZBrush exits when finished), or
loaded by hand through ZScript > Python Scripting > Load (job.json beside this file, ZBrush stays open).
Progress is written to job_result.json; it contains ``"finished": true`` once the whole job is over.
"""
import json
import os
import sys
import time
import traceback

RESULT_NAME = 'job_result.json'
LOG_NAME = 'job_log.txt'
NEUTRAL_TOOL = 'Tool:SimpleBrush'
OPEN_LEVEL = 1  # subdivision index the ZTL is saved at (0 = lowest); clipped to the available levels


class JobError(RuntimeError):
    pass


class Job:
    def __init__(self, zbc, root, manifest):
        self.zbc = zbc
        self.root = root
        self.manifest = manifest
        self.results = []
        self.warnings = []
        self.started = time.time()

    # -- bookkeeping -------------------------------------------------------------------------------------------
    def log(self, text):
        line = f'[{time.time() - self.started:7.1f}s] {text}'
        print(line)
        with open(os.path.join(self.root, LOG_NAME), 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    def write_result(self, finished=False):
        data = {'job_id': self.manifest.get('job_id'), 'finished': finished, 'build': self.manifest.get('build'), 'assets': self.results,
                'seconds': round(time.time() - self.started, 1)}
        temp = os.path.join(self.root, RESULT_NAME + '.tmp')
        with open(temp, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=1, ensure_ascii=False)
        os.replace(temp, os.path.join(self.root, RESULT_NAME))

    # -- ZBrush helpers ----------------------------------------------------------------------------------------
    def path(self, relative):
        return os.path.normpath(os.path.join(self.root, relative))

    def counts(self):
        """(points, faces) of the active tool at its current subdivision level."""
        return int(self.zbc.query_mesh3d(0)[0]), int(self.zbc.query_mesh3d(1)[0])

    def sdiv(self):
        return int(round(self.zbc.get('Tool:Geometry:SDiv')))

    def tool_name(self):
        return os.path.basename(self.zbc.get_active_tool_path().replace('\\', '/'))

    def import_obj(self, relative):
        """Import into a fresh tool (importing over an active mesh would replace it)."""
        source = self.path(relative)
        if not os.path.isfile(source):
            raise JobError(f'missing OBJ: {source}')
        self.zbc.press(NEUTRAL_TOOL)
        self.zbc.set_next_filename(source)
        self.zbc.press('Tool:Import')
        return self.tool_name()

    def expect(self, level, what):
        """Faces must match the Blender level; points may differ (ZBrush welds coincident vertices on import)."""
        points, faces = self.counts()
        if faces != level['faces']:
            raise JobError(f"{what}: expected {level['faces']} faces, got {faces}")
        if points != level['verts']:
            self.warnings.append(f"{what}: {points} points instead of {level['verts']}")

    # -- level builders ----------------------------------------------------------------------------------------
    def build_reconstruct(self, asset):
        levels = asset['levels']
        self.import_obj(levels[-1]['obj'])
        self.expect(levels[-1], 'import of the top level')
        for level in reversed(levels[:-1]):
            self.zbc.press('Tool:Geometry:Reconstruct Subdiv')
            self.expect(level, f"Reconstruct Subdiv to level {level['level']}")

    def build_project(self, asset):
        """Divide the base mesh and project each Blender level onto it (works for any base topology)."""
        zbc = self.zbc
        levels = asset['levels']
        self.import_obj(levels[0]['obj'])
        self.expect(levels[0], 'import of the base level')
        for level in levels[1:]:
            # Importing over an active mesh replaces it, so a duplicated subtool receives the detail mesh.
            zbc.press('Tool:SubTool:Duplicate')
            if zbc.get_subtool_count() != 2:
                raise JobError(f'expected 2 subtools after Duplicate, got {zbc.get_subtool_count()}')
            zbc.set_next_filename(self.path(level['obj']))
            zbc.press('Tool:Import')
            self.expect(level, f"import of level {level['level']} as detail subtool")
            zbc.select_subtool(0)
            zbc.press('Tool:Geometry:Divide')
            self.expect(level, f"Divide to level {level['level']}")
            zbc.press('Tool:SubTool:Project All')
            zbc.select_subtool(1)
            zbc.press('Tool:SubTool:Delete')
            zbc.select_subtool(0)
            if zbc.get_subtool_count() != 1:
                raise JobError('detail subtool was not deleted')
            self.expect(level, f"Project All at level {level['level']}")

    def build(self, asset, mode):
        modes = ['RECONSTRUCT', 'PROJECT'] if mode == 'AUTO' else [mode]
        errors = []
        for method in modes:
            try:
                (self.build_reconstruct if method == 'RECONSTRUCT' else self.build_project)(asset)
                return method
            except JobError as error:
                errors.append(f'{method}: {error}')
                self.log(f'{asset["name"]}: {errors[-1]}')
        raise JobError('; '.join(errors))

    # -- one asset ---------------------------------------------------------------------------------------------
    def process(self, asset):
        started = time.time()
        record = {'name': asset['name'], 'ztl': asset['ztl'], 'ok': False}
        self.results.append(record)
        self.warnings = []
        try:
            record['method'] = self.build(asset, self.manifest.get('build', 'AUTO'))
            levels = asset['levels']
            wanted = min(OPEN_LEVEL, len(levels) - 1)
            self.zbc.set('Tool:Geometry:SDiv', wanted + 1)
            self.expect(levels[wanted], f'switch to level {wanted}')
            target = self.path(asset['ztl'])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            self.zbc.set_next_filename(target)
            self.zbc.press('Tool:Save As')
            if not os.path.isfile(target) or os.path.getsize(target) == 0:
                raise JobError(f'ZTL was not written: {target}')
            record['bytes'] = os.path.getsize(target)
            record['sdiv_levels'] = len(levels)
            record['ok'] = True
            if self.warnings:
                record['warnings'] = sorted(set(self.warnings))
            self.log(f"{asset['name']}: {record['method']} OK, {len(levels)} levels, {record['bytes'] // 1024} KB")
        except JobError as error:
            record['error'] = str(error)
            self.log(f"{asset['name']}: FAILED {error}")
        except Exception:
            record['error'] = traceback.format_exc()
            self.log(f"{asset['name']}: ERROR {record['error']}")
        record['seconds'] = round(time.time() - started, 1)
        self.write_result()

    def run(self):
        for number, asset in enumerate(self.manifest['assets'], 1):
            self.log(f"[{number}/{len(self.manifest['assets'])}] {asset['name']}")
            self.process(asset)
        self.write_result(finished=True)


POINTER_NAME = 'manifest_path.txt'


def manifest_path():
    """job.json location: a command-line argument, else the path stored in manifest_path.txt beside this script
    (ZBrush cannot read non-ASCII paths from its command line, so the launcher keeps the script in an ASCII
    folder and the real path in that file), else job.json beside this script."""
    if '-script' in sys.argv:
        for argument in sys.argv[sys.argv.index('-script') + 2:]:
            if os.path.isfile(argument) and argument.lower().endswith('.json'):
                return argument
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        raise JobError('job.json not found: pass it after the script path or keep it beside zbrush_job.py')
    pointer = os.path.join(here, POINTER_NAME)
    if os.path.isfile(pointer):
        with open(pointer, encoding='utf-8-sig') as handle:
            return handle.read().strip()
    return os.path.join(here, 'job.json')


def main():
    import zbrush.commands as zbc
    root = None
    try:
        path = manifest_path()
        root = os.path.dirname(os.path.abspath(path))
        with open(path, encoding='utf-8-sig') as handle:
            manifest = json.load(handle)
        Job(zbc, root, manifest).run()
    except Exception:
        error = traceback.format_exc()
        print(error)
        if root:
            with open(os.path.join(root, RESULT_NAME), 'w', encoding='utf-8') as handle:
                json.dump({'job_id': manifest.get('job_id') if 'manifest' in locals() else None,
                           'finished': True, 'assets': [{'name': '(job)', 'ok': False, 'error': error}]}, handle, indent=1)
    # A command-line start exits ZBrush cleanly (a kill would show the abnormal-termination note next time).
    if '-script' in sys.argv:
        sys.exit(0)


if __name__ == '__main__':
    main()
