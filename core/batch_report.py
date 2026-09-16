"""Incremental, Blender-independent batch audit files."""
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4


class BatchReport:
    def __init__(self, directory, files):
        self.directory = Path(directory) / 'batch_reports' / (
            datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8])
        self.directory.mkdir(parents=True)
        self.files = list(files)
        self.records = []
        self.status = 'RUNNING'
        self.event('begin', {'files': self.files})

    def event(self, event, data):
        with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': datetime.now().isoformat(), 'event': event,
                                     'data': data}, ensure_ascii=False) + '\n')
        if event == 'file_complete':
            self.records.append(dict(data))
        elif event == 'finish':
            self.status = data['status']
        summary = {
            'status': self.status, 'total_files': len(self.files),
            'successful_files': sum(r['status'] == 'success' for r in self.records),
            'failed_files': sum(r['status'] == 'failed' for r in self.records),
            'interrupted_files': sum(r['status'] in ('interrupted', 'cancelled') for r in self.records),
            'unprocessed_files': len(self.files) - len(self.records),
            'input_tris': sum(r.get('input_tris') or 0 for r in self.records),
            'successful_input_tris': sum(r.get('input_tris') or 0 for r in self.records if r['status'] == 'success'),
            'output_tris': sum(r.get('output_tris') or 0 for r in self.records if r['status'] == 'success'),
        }
        for name, payload in (('summary.json', summary), ('files.json', self.records)):
            temporary = self.directory / (name + '.tmp')
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, self.directory / name)
