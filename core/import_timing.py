"""Active queue time and estimates based on successfully completed files."""

import time


class ImportTiming:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.paused_at = None
        self.paused_seconds = 0.0
        self.stopped_at = None
        self.file_started = None
        self.last_file_seconds = 0.0
        self.completed_seconds = 0.0
        self.completed_count = 0

    def elapsed(self):
        now = self.stopped_at if self.stopped_at is not None else self.clock()
        if self.paused_at is not None:
            now = self.paused_at
        return max(0.0, now - self.started - self.paused_seconds)

    def pause(self):
        if self.paused_at is None:
            self.paused_at = self.clock()

    def resume(self):
        if self.paused_at is not None:
            self.paused_seconds += self.clock() - self.paused_at
            self.paused_at = None

    def start_file(self):
        self.resume()
        self.file_started = self.elapsed()
        self.last_file_seconds = 0.0

    def current_elapsed(self):
        if self.file_started is None:
            return self.last_file_seconds
        return max(0.0, self.elapsed() - self.file_started)

    def complete_file(self, success):
        self.last_file_seconds = self.current_elapsed()
        self.file_started = None
        if success:
            self.completed_seconds += self.last_file_seconds
            self.completed_count += 1

    def average(self):
        return self.completed_seconds / self.completed_count if self.completed_count else 0.0

    def remaining(self, files_left):
        if files_left <= 0:
            return 0.0
        if not self.completed_count:
            return -1.0
        average = self.average()
        if self.file_started is not None:
            return average * (files_left - 1) + max(0.0, average - self.current_elapsed())
        return average * files_left

    def stop(self):
        if self.stopped_at is None:
            self.stopped_at = self.clock()


def format_duration(seconds):
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
