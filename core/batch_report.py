"""Incremental, Blender-independent batch audit files.

One run directory (``batch_reports/<time>_<id>`` for Phase 1, ``..._phase2`` for Phase 2)::

    summary.json       totals, failed / skipped collections and links to their logs
    files.json         compact index with one row per file / Generated.N collection
    files/<name>.json  the complete record (stages, traceback, ...) of one file / collection
    events.jsonl       chronological event stream
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

FOLDER = 'batch_reports'
FILES_FOLDER = 'files'
# Heavy detail that only the per-file log keeps.
DETAIL_KEYS = ('stages', 'traceback', 'finalization', 'remesher')
FAILURE_STATUSES = ('failed', 'interrupted', 'cancelled')


def safe_name(text):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(text)).strip(' .') or 'file'


def write_json(path, payload):
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def record_label(record):
    """Generated.N when known, otherwise the file name."""
    return record.get('collection') or os.path.basename(str(record.get('file', ''))) or '?'


class BatchReport:
    def __init__(self, directory, files, phase=1):
        self.phase = phase
        self.directory = Path(directory) / FOLDER / (
            datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8] + ('_phase2' if phase == 2 else ''))
        self.directory.mkdir(parents=True)
        (self.directory / FILES_FOLDER).mkdir()
        self.files = list(files)
        self.records = []
        self.index = []
        self.status = 'RUNNING'
        self.event('begin', {'files': self.files, 'phase': phase})

    def log_name(self, record):
        base = safe_name(record.get('collection') or Path(str(record.get('file', 'file'))).stem)
        if not record.get('collection'):
            base = f'file_{len(self.records):03d}_{base}'
        name, number = base, 1
        while (self.directory / FILES_FOLDER / (name + '.json')).exists():
            number += 1
            name = f'{base}_{number}'
        return name + '.json'

    def add_record(self, record):
        record = dict(record)
        name = self.log_name(record)
        record['log'] = f'{FILES_FOLDER}/{name}'
        write_json(self.directory / FILES_FOLDER / name, record)
        self.records.append(record)
        self.index.append({key: value for key, value in record.items() if key not in DETAIL_KEYS})

    def problems(self, statuses):
        return [{'collection': record.get('collection'), 'file': record.get('file'),
                 'status': record['status'], 'error': record.get('error') or record.get('reason', ''),
                 'failed_stage': record.get('failed_stage'), 'failed_pass': record.get('failed_pass'),
                 'log': record['log']}
                for record in self.records if record['status'] in statuses]

    def summary(self):
        records = self.records
        count = lambda *statuses: sum(r['status'] in statuses for r in records)
        return {
            'phase': self.phase, 'status': self.status, 'total_files': len(self.files),
            'successful_files': count('success'), 'failed_files': count('failed'),
            'interrupted_files': count('interrupted', 'cancelled'), 'skipped_files': count('skipped'),
            'unprocessed_files': len(self.files) - len(records),
            'input_tris': sum(r.get('input_tris') or 0 for r in records),
            'successful_input_tris': sum(r.get('input_tris') or 0 for r in records if r['status'] == 'success'),
            'output_tris': sum(r.get('output_tris') or 0 for r in records if r['status'] == 'success'),
            'successful_collections': [record_label(r) for r in records if r['status'] == 'success'],
            'failed_collections': self.problems(FAILURE_STATUSES),
            'skipped_collections': self.problems(('skipped',)),
            'files_index': 'files.json', 'events': 'events.jsonl',
        }

    def event(self, event, data):
        with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': datetime.now().isoformat(), 'event': event,
                                     'data': data}, ensure_ascii=False) + '\n')
        if event == 'file_complete':
            self.add_record(data)
        elif event == 'finish':
            self.status = data['status']
        write_json(self.directory / 'summary.json', self.summary())
        write_json(self.directory / 'files.json', self.index)
