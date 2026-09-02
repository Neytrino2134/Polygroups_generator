"""Run with python tests/test_import_timing.py (Blender is not required)."""

import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "import_timing", Path(__file__).resolve().parents[1] / "core" / "import_timing.py",
)
timing_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing_module)


class ImportTimingTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.timing = timing_module.ImportTiming(clock=lambda: self.now)

    def test_average_and_remaining_current_file(self):
        self.assertEqual(self.timing.remaining(22), -1)
        for duration in (20, 40):
            self.timing.start_file()
            self.now += duration
            self.timing.complete_file(True)
        self.assertEqual(self.timing.average(), 30)
        self.assertEqual(self.timing.remaining(20), 600)
        self.timing.start_file()
        self.now += 10
        self.assertEqual(self.timing.current_elapsed(), 10)
        self.assertEqual(self.timing.remaining(20), 590)
        self.now += 60
        self.assertEqual(self.timing.remaining(20), 570)
        self.assertEqual(self.timing.remaining(1), 0)

    def test_pause_resume_and_stop_freeze_timers(self):
        self.timing.start_file()
        self.now += 30
        self.timing.complete_file(True)
        self.timing.pause()
        self.now += 120
        self.assertEqual(self.timing.elapsed(), 30)
        self.assertEqual(self.timing.current_elapsed(), 30)
        self.timing.start_file()
        self.now += 20
        self.assertEqual(self.timing.elapsed(), 50)
        self.assertEqual(self.timing.current_elapsed(), 20)
        self.timing.stop()
        self.now += 100
        self.assertEqual(self.timing.elapsed(), 50)
        self.assertEqual(self.timing.current_elapsed(), 20)

    def test_errors_do_not_bias_average(self):
        self.timing.start_file()
        self.now += 2
        self.timing.complete_file(False)
        self.assertEqual(self.timing.remaining(20), -1)
        self.timing.start_file()
        self.now += 30
        self.timing.complete_file(True)
        self.assertEqual(self.timing.average(), 30)
        self.assertEqual(self.timing.elapsed(), 32)
        self.assertEqual(self.timing.remaining(0), 0)

    def test_display_format(self):
        self.assertEqual(timing_module.format_duration(600), "00:10:00")
        self.assertEqual(timing_module.format_duration(3661.9), "01:01:01")


if __name__ == "__main__":
    unittest.main()
