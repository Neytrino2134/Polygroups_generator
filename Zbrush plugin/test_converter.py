import importlib.util
import json
from pathlib import Path
import tempfile
import runpy
import sys
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('converter', Path(__file__).with_name('converter.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mesh = self.root / 'Mesh' / 'Generated.001'
        mesh.mkdir(parents=True)
        self.obj = mesh / 'Generated.001_L0.obj'
        self.obj.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        self.target = self.root / 'ZTL' / 'Generated.001.ztl'

    def process(self, job, asset):
        self.target.parent.mkdir(exist_ok=True)
        self.target.write_bytes(b'new-tool')
        job.results.append(dict(name=asset['name'], ztl=asset['ztl'], ok=True))

    def test_resume_and_stale_input(self):
        queue = c.Queue(self.root / 'Mesh')
        with patch.object(c.ConversionJob, 'process', autospec=True, side_effect=self.process) as process:
            self.assertEqual(queue.run(None)['converted'], 1)
            self.assertEqual(c.Queue(self.root).run(None)['skipped'], 1)
            self.assertEqual(process.call_count, 1)
            self.obj.write_text(self.obj.read_text() + '# changed\n')
            self.assertEqual(c.Queue(self.root).status(queue.manifest['assets'][0]), 'existing')
            self.assertEqual(c.Queue(self.root).run(None, overwrite=True)['converted'], 1)
        self.assertFalse((self.root / 'job_result.json').exists())
        self.assertFalse((self.root / 'job_control.json').exists())

    def test_existing_is_preserved_and_failed_overwrite_restores(self):
        self.target.parent.mkdir()
        self.target.write_bytes(b'original')
        queue = c.Queue(self.root)
        self.assertEqual(queue.run(None)['skipped'], 1)
        def fail(job, asset):
            self.target.write_bytes(b'partial')
            job.results.append(dict(name=asset['name'], ok=False))
        with patch.object(c.ConversionJob, 'process', autospec=True, side_effect=fail):
            self.assertEqual(queue.run(None, overwrite=True)['failed'], 1)
        self.assertEqual(self.target.read_bytes(), b'original')

    def test_manifest_escape_and_level_gap_rejected(self):
        _, manifest = c.load_export(self.root)
        manifest['assets'][0]['ztl'] = '../escape.ztl'
        path = self.root / 'job.json'
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            c.load_export(self.root)
        path.unlink()
        self.obj.rename(self.obj.with_name('Generated.001_L2.obj'))
        with self.assertRaises(ValueError):
            c.load_export(self.root)

    def test_next_only_processes_one_asset(self):
        other = self.obj.parent / 'Other_L0.obj'
        other.write_text(self.obj.read_text())
        queue = c.Queue(self.root)
        with patch.object(c.ConversionJob, 'process', autospec=True, side_effect=self.process) as process:
            self.assertEqual(queue.run(None, limit=1)['converted'], 1)
            self.assertEqual(process.call_count, 1)

    def test_failed_new_save_removes_partial_output(self):
        def fail(job, asset):
            self.target.parent.mkdir(exist_ok=True)
            self.target.write_bytes(b'partial')
            job.results.append(dict(name=asset['name'], ok=False))
        with patch.object(c.ConversionJob, 'process', autospec=True, side_effect=fail):
            self.assertEqual(c.Queue(self.root).run(None)['failed'], 1)
        self.assertFalse(self.target.exists())

    def test_plugin_registration_matches_installed_api(self):
        api_path = Path(r'C:\Program Files\Maxon ZBrush 2027\Documentation\python-api\api\zbrush\commands.py')
        if not api_path.exists():
            self.skipTest('Installed ZBrush API stubs unavailable')
        import ast
        import inspect
        source = ast.parse(api_path.read_text(encoding='utf-8-sig'))
        definitions = {node.name: node for node in source.body if isinstance(node, ast.FunctionDef)}
        fake = types.ModuleType('zbrush.commands')
        buttons = []
        for name in ('exists', 'delete_interface_item', 'add_subpalette', 'add_button', 'add_switch'):
            node = definitions[name]
            namespace = {'Callable': object}
            # Only use the signature, not stub bodies/docstrings or the proprietary runtime.
            node.body = [ast.Pass()]
            node.decorator_list = []
            exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<api>', 'exec'), namespace)
            signature = inspect.signature(namespace[name])
            def callback(*args, _signature=signature, _name=name, **kwargs):
                _signature.bind(*args, **kwargs)
                if _name == 'add_button':
                    buttons.append(args[0])
                return False
            setattr(fake, name, callback)
        package = types.ModuleType('zbrush')
        package.commands = fake
        with patch.dict(sys.modules, {'zbrush': package, 'zbrush.commands': fake}):
            runpy.run_path(str(Path(__file__).with_name('MeshToZTL.py')), run_name='__main__')
        self.assertEqual(len(buttons), 5)

    def test_native_folder_window_actions(self):
        window_spec = importlib.util.spec_from_file_location('folder_window', Path(__file__).with_name('folder_window.py'))
        win = importlib.util.module_from_spec(window_spec)
        window_spec.loader.exec_module(win)
        settings = dict(folder=str(self.root), mode='AUTO')
        saves = []
        dialog = win.FolderWindow(c, None, settings, lambda: saves.append(dict(settings)))
        try:
            dialog.command(13)
            self.assertEqual(dialog.text(10), '')
            with patch.object(win, 'clipboard_text', return_value=str(self.root / 'Mesh')):
                dialog.command(12)
            self.assertEqual(dialog.text(10), str(self.root / 'Mesh'))
            dialog.command(14)
            self.assertIn('Ready: 1 meshes', dialog.text(17))
            self.assertTrue(saves)
            with patch.object(win, 'browse_folder', return_value=str(self.root)):
                dialog.command(11)
            self.assertEqual(dialog.text(10), str(self.root))
            with patch.object(c.ConversionJob, 'process', autospec=True, side_effect=self.process):
                dialog.command(18)
            self.assertIn('Converted: 1', dialog.text(17))
            self.assertFalse(dialog.busy)
            dialog.command(20)
            self.assertFalse(win.is_window(dialog.hwnd))
        finally:
            if win.is_window(dialog.hwnd):
                win.destroy(dialog.hwnd)
            win.bind(win.U, 'UnregisterClassW', win.W.BOOL, win.W.LPCWSTR, win.W.HINSTANCE)(dialog.class_name, win.instance)

    def test_choose_folder_does_not_query_broken_zbrush_get(self):
        from unittest.mock import Mock
        fake = types.ModuleType('zbrush.commands')
        for name in ('exists', 'delete_interface_item', 'add_subpalette', 'add_button', 'add_switch'):
            setattr(fake, name, Mock(return_value=False))
        fake.get = Mock(side_effect=SystemError('PyCapsule get returned a result with an exception set'))
        fake.message_ok = Mock()
        package = types.ModuleType('zbrush')
        package.commands = fake
        with patch.dict(sys.modules, {'zbrush': package, 'zbrush.commands': fake}):
            env = runpy.run_path(str(Path(__file__).with_name('MeshToZTL.py')), run_name='__main__')
        factory = Mock()
        factory.return_value.thread.is_alive.return_value = False
        class Loader:
            def create_module(self, spec):
                return None
            def exec_module(self, module):
                module.ModelessController = factory
        window_spec = importlib.machinery.ModuleSpec('fake_window', Loader())
        with patch.object(importlib.util, 'spec_from_file_location', return_value=window_spec):
            env['choose_folder']('Choose Folder')
            self.assertFalse(factory.call_args.args[-1])
            env['toggle_overwrite']('Overwrite existing')
            env['choose_folder']('Choose Folder')
            self.assertTrue(factory.call_args.args[-1])
        self.assertEqual(factory.return_value.run.call_count, 2)
        fake.get.assert_not_called()
        fake.message_ok.assert_not_called()

    def test_command_trace_records_failing_command(self):
        from unittest.mock import Mock
        api = Mock()
        api.press.side_effect = RuntimeError('injected import failure')
        with c._diagnostics.Trace(self.root) as trace:
            with self.assertRaises(RuntimeError):
                trace.proxy(api).press('Tool:Import')
        log = (self.root / 'standalone_commands.log').read_text()
        self.assertIn("BEGIN press(('Tool:Import',)", log)
        self.assertIn('ERROR press', log)
        self.assertIn('injected import failure', log)

    def test_modeless_dispatch_returns_and_keeps_commands_on_main_thread(self):
        import threading
        import time
        window_spec = importlib.util.spec_from_file_location('folder_window_modeless', Path(__file__).with_name('folder_window.py'))
        win = importlib.util.module_from_spec(window_spec)
        window_spec.loader.exec_module(win)
        controller = win.ModelessController(c, None, dict(folder=str(self.root), mode='AUTO'), lambda: None, False)
        called = []
        try:
            controller.run()
            deadline = time.monotonic() + 3
            while controller.window is None and controller.error is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertIsNone(controller.error)
            self.assertTrue(controller.thread.is_alive())
            controller.submit(lambda: called.append(threading.get_ident()))
            message = win.W.MSG()
            while win.peek(win.C.byref(message), controller.hwnd, 0, 0, 1):
                win.dispatch(win.C.byref(message))
            self.assertEqual(called, [threading.get_ident()])
        finally:
            if controller.window:
                win.bind(win.U, 'PostMessageW', win.W.BOOL, win.W.HWND, win.W.UINT, win.W.WPARAM, win.W.LPARAM)(controller.window.hwnd, 0x10, 0, 0)
            controller.thread.join(timeout=3)
            if win.is_window(controller.hwnd):
                win.destroy(controller.hwnd)
            win.bind(win.U, 'UnregisterClassW', win.W.BOOL, win.W.LPCWSTR, win.W.HINSTANCE)(controller.class_name, win.instance)

    def test_stop_after_current_mesh_keeps_progress(self):
        (self.obj.parent / 'Other_L0.obj').write_text(self.obj.read_text())
        stop = []
        with patch.object(c.ConversionJob, 'process', autospec=True, side_effect=self.process) as process:
            result = c.Queue(self.root).run(None, progress=lambda message: stop.append(True),
                                            should_stop=lambda: bool(stop))
        self.assertEqual(result['converted'], 1)
        self.assertEqual(process.call_count, 1)
        self.assertFalse(json.loads((self.root / 'standalone_last_run.json').read_text())['finished'])


if __name__ == '__main__':
    unittest.main()
