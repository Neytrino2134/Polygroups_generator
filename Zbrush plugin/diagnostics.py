"""Durable command tracing and a Python watchdog; never calls ZBrush from a worker."""
import datetime
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback


class Trace:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.active = None
        self.thread = None
        self.progress = None

    def write(self, message):
        line = f'{datetime.datetime.now().astimezone().isoformat(timespec="seconds")} pid={os.getpid()} tid={threading.get_ident()} {message}\n'
        with self.lock:
            with (self.root / 'standalone_commands.log').open('a', encoding='utf-8') as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    def __enter__(self):
        self.write('SESSION BEGIN')
        self.thread = threading.Thread(target=self.watch, name='MeshToZTL-watchdog', daemon=True)
        self.thread.start()
        return self

    def __exit__(self, kind, value, tb):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
        if kind:
            self.write('SESSION ERROR ' + ''.join(traceback.format_exception(kind, value, tb)))
        self.write('SESSION END')

    def watch(self):
        while not self.stop.wait(15):
            with self.lock:
                active = self.active
            if active:
                elapsed = time.monotonic() - active[1]
                self.write(f'WAIT {elapsed:.1f}s {active[0]}')
                if self.progress:
                    self.progress(f'Waiting {elapsed:.0f}s: {active[0]}\nZBrush command is still running. See standalone_commands.log.')
                if elapsed >= 60:
                    with self.lock, (self.root / 'standalone_stacks.log').open('a', encoding='utf-8') as handle:
                        handle.write(f'\nWAIT {elapsed:.1f}s {active[0]}\n')
                        for ident, frame in sys._current_frames().items():
                            handle.write(f'\nThread {ident}\n' + ''.join(traceback.format_stack(frame)))
                        handle.flush()

    def proxy(self, commands):
        trace = self
        class Commands:
            def __getattr__(self, name):
                method = getattr(commands, name)
                if not callable(method):
                    return method
                def call(*args, **kwargs):
                    label = f'{name}({args!r}, {kwargs!r})'
                    started = time.monotonic()
                    with trace.lock:
                        trace.active = (label, started)
                    trace.write('BEGIN ' + label)
                    if trace.progress:
                        trace.progress('Running: ' + label)
                    try:
                        result = method(*args, **kwargs)
                        trace.write(f'END {time.monotonic()-started:.3f}s {label} => {result!r}')
                        return result
                    except BaseException:
                        trace.write('ERROR ' + label + '\n' + traceback.format_exc())
                        raise
                    finally:
                        with trace.lock:
                            trace.active = None
                return call
        return Commands()
